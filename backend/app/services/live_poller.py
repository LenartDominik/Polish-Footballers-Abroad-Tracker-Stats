"""Background poller for live match tracking of Polish players."""

import asyncio
import json
import os
import tempfile
from datetime import datetime, date, timedelta
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LiveMatchEvent, Player
from app.db.session import AsyncSessionLocal
from app.services.rapidapi import rapidapi_client

logger = structlog.get_logger()

# File-based cache — survives server sleep/wake cycles on Render
_FIXTURE_CACHE_FILE = os.path.join(tempfile.gettempdir(), "poller_fixture_cache.json")

# Tracked players: rapidapi_id -> info
LIVE_TRACKED_PLAYERS = {
    93447: {
        "name": "Robert Lewandowski",
        "team_name": "Barcelona",
    },
    169718: {
        "name": "Wojciech Szczęsny",
        "team_name": "Barcelona",
    },
    362212: {
        "name": "Piotr Zieliński",
        "team_name": "Inter",
    },
    490868: {
        "name": "Jan Bednarek",
        "team_name": "FC Porto",
    },
    1021834: {
        "name": "Jakub Kiwior",
        "team_name": "FC Porto",
    },
    1647807: {
        "name": "Oskar Pietuszewski",
        "team_name": "FC Porto",
    },
    954190: {
        "name": "Michał Skóraś",
        "team_name": "Gent",
    },
    729731: {
        "name": "Matty Cash",
        "team_name": "Aston Villa",
    },
    1053714: {
        "name": "Nicola Zalewski",
        "team_name": "Atalanta",
    },
}

# Polling intervals (seconds)
INTERVAL_SLEEPING = 21600  # 6h - no match, recheck fixtures
INTERVAL_PREMATCH = 1800   # 30 min - match day but not near kickoff
INTERVAL_PREMATCH_LINEUP = 120    # 2 min - prematch near kickoff, fast transition to live
INTERVAL_PREMATCH_KICKOFF = 60    # 1 min - kickoff passed, aggressively check if started
INTERVAL_TRACKING = 120    # 2 min - live match, player playing
INTERVAL_BENCH = 120       # 2 min - live match, player on bench
PREMATCH_WINDOW_HOURS = 0.75  # 45 min - check lineups when kickoff within this many hours
PREMATCH_WAKEUP_BUFFER_HOURS = 0.5  # 30 min - wake up this long before kickoff

# Team -> league IDs mapping (only check leagues where tracked teams actually play)
TEAM_LEAGUES: dict[str, list[int]] = {
    "Barcelona": [87, 138, 42],       # La Liga, Copa del Rey, Champions League
    "Inter": [55, 141, 222, 42],      # Serie A, Coppa Italia, Supercoppa, Champions League
    "FC Porto": [61, 186],            # Primeira Liga, Taça de Portugal
    "Gent": [40, 149],                # First Division A, Belgian Cup
    "Aston Villa": [47, 132, 133, 73],  # Premier League, FA Cup, EFL Cup, Europa League
    "Atalanta": [55, 141, 42],        # Serie A, Coppa Italia, Champions League
}

# Auto-derived: unique league IDs for all tracked teams
TRACKED_LEAGUE_IDS = list({
    league_id
    for team_name in {info["team_name"] for info in LIVE_TRACKED_PLAYERS.values()}
    for league_id in TEAM_LEAGUES.get(team_name, [])
})

# Primary domestic leagues — checked first (5 instead of 13 on most days)
PRIMARY_LEAGUE_IDS = [87, 55, 61, 40, 47]  # La Liga, Serie A, Primeira Liga, Belgian, Premier League
CUP_LEAGUE_IDS = [lid for lid in TRACKED_LEAGUE_IDS if lid not in PRIMARY_LEAGUE_IDS]

LEAGUE_NAMES: dict[int, str] = {
    87: "La Liga",
    55: "Serie A",
    61: "Primeira Liga",
    40: "First Division A",
    138: "Copa del Rey",
    141: "Coppa Italia",
    186: "Taça de Portugal",
    97: "Taça da Liga",
    222: "Supercoppa Italiana",
    149: "Belgian Cup",
    42: "Champions League",
    73: "Europa League",
    47: "Premier League",
    132: "FA Cup",
    133: "EFL Cup",
}


def _find_player_in_lineup(lineup_data: dict, rapidapi_id: int, player_name: str) -> str:
    """Check if a player is in the lineup response.

    Matches by ID first, then by name as fallback.
    Returns: 'starting', 'bench', or 'absent'
    """
    if not lineup_data:
        return "absent"

    response = lineup_data.get("response", lineup_data)

    # Try both possible API response keys: "list" and "lineup"
    for key in ("list", "lineup"):
        lineup = response.get(key, None)
        if lineup is None:
            continue

        if isinstance(lineup, dict):
            starters = lineup.get("starters", [])
            subs = lineup.get("subs", [])

            for p in starters:
                if isinstance(p, dict):
                    if p.get("id") == rapidapi_id or _name_matches(p, player_name):
                        return "starting"

            for p in subs:
                if isinstance(p, dict):
                    if p.get("id") == rapidapi_id or _name_matches(p, player_name):
                        return "bench"

    # Fallback: flat list — treat as unknown rather than assuming starting
    if isinstance(response, list):
        for p in response:
            if isinstance(p, dict):
                if p.get("id") == rapidapi_id or _name_matches(p, player_name):
                    return "bench" if p.get("type", "").lower() in ("sub", "substitute") else "starting"

    return "absent"


def _name_matches(player_dict: dict, target_name: str) -> bool:
    """Check if a player dict's name matches the target name."""
    name = player_dict.get("name", player_dict.get("playerName", ""))
    return _name_match_str(name, target_name)


def _name_match_str(name: str, target: str) -> bool:
    """Fuzzy name match — handles accents, case, partial matches."""
    if not name or not target:
        return False
    name_lower = name.lower().replace("ł", "l").replace("ś", "s").replace("ń", "n").replace("ź", "z").replace("ż", "z").replace("ć", "c").replace("ą", "a").replace("ę", "e")
    target_lower = target.lower().replace("ł", "l").replace("ś", "s").replace("ń", "n").replace("ź", "z").replace("ż", "z").replace("ć", "c").replace("ą", "a").replace("ę", "e")
    return target_lower in name_lower or name_lower in target_lower


def _collect_all_dicts(data, depth=0):
    """Collect all dicts from nested structure for deep search."""
    if depth > 5:
        return []
    result = []
    if isinstance(data, dict):
        result.append(data)
        for v in data.values():
            result.extend(_collect_all_dicts(v, depth + 1))
    elif isinstance(data, list):
        for item in data:
            result.extend(_collect_all_dicts(item, depth + 1))
    return result


def _parse_live_match(match_data: dict) -> Optional[dict]:
    """Parse a live match from API response into standard format.

    Handles multiple formats:
    - Fixture: {home: {name, score}, away: {name, score}, status: {scoreStr, liveTime}}
    - Match score: {scores: [{name, score}, {name, score}]}
    """
    if not match_data or not isinstance(match_data, dict):
        return None

    match_id = match_data.get("id") or match_data.get("eventId") or match_data.get("match_id")
    if not match_id:
        return None

    # Home/away names and scores
    home_name = ""
    away_name = ""
    home_score = 0
    away_score = 0

    # Format 1: scores array from get_match_score: {scores: [{name, score}, {name, score}]}
    scores_arr = match_data.get("scores", [])
    if isinstance(scores_arr, list) and len(scores_arr) >= 2:
        home_name = scores_arr[0].get("name", "") if isinstance(scores_arr[0], dict) else ""
        away_name = scores_arr[1].get("name", "") if isinstance(scores_arr[1], dict) else ""
        home_score = scores_arr[0].get("score", 0) if isinstance(scores_arr[0], dict) else 0
        away_score = scores_arr[1].get("score", 0) if isinstance(scores_arr[1], dict) else 0

    # Format 2: home/away objects from fixture: {home: {name, score}, away: {name, score}}
    if not home_name and not away_name:
        home = match_data.get("home", match_data.get("homeTeam", {}))
        away = match_data.get("away", match_data.get("awayTeam", {}))
        home_name = home.get("name", "") if isinstance(home, dict) else str(home) if home else ""
        away_name = away.get("name", "") if isinstance(away, dict) else str(away) if away else ""
        home_score = home.get("score", 0) if isinstance(home, dict) else 0
        away_score = away.get("score", 0) if isinstance(away, dict) else 0

    # Score fallback: scoreStr "0 - 1" from status
    status_data = match_data.get("status", {})
    if not home_score and not away_score and isinstance(status_data, dict):
        score_str = status_data.get("scoreStr", "")
        if score_str and " - " in score_str:
            parts = score_str.split(" - ")
            try:
                home_score = int(parts[0])
                away_score = int(parts[1])
            except ValueError:
                pass

    # Minute: try multiple sources
    minute = match_data.get("minute")
    if not minute and isinstance(status_data, dict):
        live_time = status_data.get("liveTime", {})
        if isinstance(live_time, dict):
            minute = live_time.get("short", "")
        if not minute:
            minute = status_data.get("liveTimeShort", status_data.get("minute"))
    if not minute:
        minute = match_data.get("liveTime", match_data.get("liveTimeShort"))

    # Competition
    competition = ""
    tournament = match_data.get("tournament", {})
    if isinstance(tournament, dict):
        competition = tournament.get("name", match_data.get("competition", ""))
    elif isinstance(match_data.get("competition"), dict):
        competition = match_data["competition"].get("name", "")
    else:
        competition = match_data.get("competition", "")

    # Status
    is_live = False
    if isinstance(status_data, dict):
        is_live = status_data.get("ongoing") or status_data.get("started", False)
    status = "live" if is_live else match_data.get("status", "unknown")

    return {
        "match_id": match_id,
        "home_team": home_name,
        "away_team": away_name,
        "home_score": home_score,
        "away_score": away_score,
        "status": status,
        "minute": minute,
        "competition": competition,
    }


def _parse_match_status(status_data: dict) -> Optional[dict]:
    """Parse match status endpoint response for minute and score."""
    if not status_data or not isinstance(status_data, dict):
        return None

    status = status_data.get("status", {})
    if not isinstance(status, dict):
        return None

    # Score from scoreStr
    home_score = 0
    away_score = 0
    score_str = status.get("scoreStr", "")
    if score_str and " - " in score_str:
        parts = score_str.split(" - ")
        try:
            home_score = int(parts[0])
            away_score = int(parts[1])
        except ValueError:
            pass

    # Minute from liveTime — strip Unicode chars and apostrophes
    minute = ""
    live_time = status.get("liveTime", {})
    if isinstance(live_time, dict):
        raw = live_time.get("short", "")
        # Remove invisible chars (U+200E etc.) and apostrophes, keep just the number
        minute = raw.replace("‎", "").replace("'", "").replace("’", "").strip()

    return {
        "home_score": home_score,
        "away_score": away_score,
        "minute": minute,
        "ongoing": status.get("ongoing", False),
        "finished": status.get("finished", False),
        "started": status.get("started", False),
    }


def _extract_events_from_match(match_data: dict, tracked_player_name: str) -> list[dict]:
    """Extract goal/assist events for a tracked player from match data."""
    events = match_data.get("events", match_data.get("incidents", []))
    if not isinstance(events, list):
        return []

    tracked_events = []
    name_lower = tracked_player_name.lower()

    for event in events:
        if not isinstance(event, dict):
            continue

        event_type_raw = event.get("type", "").lower()
        player_name = event.get("playerName", event.get("player", ""))
        if isinstance(player_name, dict):
            player_name = player_name.get("name", "")

        if name_lower not in player_name.lower():
            continue

        mapped_type = None
        if event_type_raw in ("goal", "penalty"):
            mapped_type = "goal"
        elif event_type_raw in ("assist",):
            mapped_type = "assist"
        elif event_type_raw in ("yellowcard", "yellow_card", "yellow card"):
            mapped_type = "yellow_card"
        elif event_type_raw in ("redcard", "red_card", "red card"):
            mapped_type = "red_card"

        if mapped_type:
            tracked_events.append({
                "event_type": mapped_type,
                "minute": event.get("minute", event.get("time")),
                "player_name": player_name,
                "match_score": event.get("score", ""),
            })

    return tracked_events


def _extract_events_from_lineup(lineup_data: dict, tracked_player_name: str) -> list[dict]:
    """Extract events (goal, assist, card, substitution) for tracked player from lineup data.

    RapidAPI format: response.lineup.starters[].events[].type = "goal", "assist", etc.
    Also checks subs array for substitution events.
    """
    if not lineup_data:
        return []

    response = lineup_data.get("response", lineup_data)

    # Try response.lineup.starters (actual API format)
    lineup = response.get("lineup", response)
    print(f"=== EXTRACT: response keys={list(response.keys()) if isinstance(response, dict) else type(response)} ===")
    print(f"=== EXTRACT: lineup type={type(lineup).__name__}, keys={list(lineup.keys()) if isinstance(lineup, dict) else 'N/A'} ===")

    if isinstance(lineup, list) and len(lineup) > 0 and isinstance(lineup[0], dict):
        lineup = lineup[0]  # first team's lineup

    # Collect all player entries from starters and subs
    all_players = []
    if isinstance(lineup, dict):
        all_players.extend(lineup.get("starters", []))
        all_players.extend(lineup.get("subs", []))
    print(f"=== EXTRACT: all_players count={len(all_players)} ===")
    # Fallback to other formats
    data = response.get("list", response)
    if isinstance(data, dict):
        all_players.extend(data.get("starters", []))
        all_players.extend(data.get("subs", []))
        all_players.extend(data.get("players", []))
    elif isinstance(data, list) and not all_players:
        all_players = data

    tracked_events = []
    name_lower = tracked_player_name.lower()
    name_normalized = name_lower.replace("ł", "l").replace("ś", "s").replace("ń", "n").replace("ź", "z").replace("ż", "z").replace("ć", "c").replace("ą", "a").replace("ę", "e")

    for player in all_players:
        if not isinstance(player, dict):
            continue

        # Check if this player is the tracked one
        pname = player.get("name", player.get("playerName", ""))
        if isinstance(pname, dict):
            pname = pname.get("name", "")
        if not pname:
            continue

        pname_lower = pname.lower()
        pname_normalized = pname_lower.replace("ł", "l").replace("ś", "s").replace("ń", "n").replace("ź", "z").replace("ż", "z").replace("ć", "c").replace("ą", "a").replace("ę", "e")

        if name_lower not in pname_lower and name_normalized not in pname_normalized:
            continue

        print(f"=== EXTRACT: MATCHED player '{pname}' for tracked '{tracked_player_name}' ===")

        # Events are inside performance.events and performance.substitutionEvents
        performance = player.get("performance", {})
        perf_events = performance.get("events", []) if isinstance(performance, dict) else []
        sub_events = performance.get("substitutionEvents", []) if isinstance(performance, dict) else []

        print(f"=== EXTRACT: perf_events={perf_events}, sub_events={sub_events} ===")

        for evt in perf_events:
            if not isinstance(evt, dict):
                continue
            event_type = evt.get("type", "").lower()
            event_time = evt.get("time", evt.get("minute", evt.get("matchTime")))
            if not event_time:
                logger.warning("Event has no time field", raw_event=evt, player=pname)
            mapped = _map_event_type(event_type)
            if mapped:
                tracked_events.append({
                    "event_type": mapped,
                    "minute": int(event_time) if event_time else 0,
                    "player_name": pname,
                    "match_score": "",
                })

        for evt in sub_events:
            if not isinstance(evt, dict):
                continue
            event_type = evt.get("type", "").lower()
            event_time = evt.get("time")
            mapped = _map_event_type(event_type)
            if mapped:
                tracked_events.append({
                    "event_type": mapped,
                    "minute": event_time,
                    "player_name": pname,
                    "match_score": "",
                })

        # Also check player.type for substitution events (some formats)
        player_type = player.get("type", "").lower()
        if player_type in ("subin", "subout"):
            mapped = _map_event_type(player_type)
            if mapped:
                tracked_events.append({
                    "event_type": mapped,
                    "minute": player.get("time", player.get("minute")),
                    "player_name": pname,
                    "match_score": "",
                })

    return tracked_events


def _map_event_type(raw_type: str) -> str | None:
    """Map raw event type from API to normalized type."""
    if raw_type in ("goal",):
        return "goal"
    elif raw_type in ("assist",):
        return "assist"
    elif raw_type in ("subin",):
        return "subin"
    elif raw_type in ("subout",):
        return "subout"
    elif raw_type in ("yellowcard", "yellow_card", "yellow card"):
        return "yellow_card"
    elif raw_type in ("redcard", "red_card", "red card"):
        return "red_card"
    return None


def _is_team_in_match(match: dict, team_name: str) -> bool:
    """Check if a team is playing in this match (case-insensitive)."""
    home = match.get("home_team", "").lower()
    away = match.get("away_team", "").lower()
    team_lower = team_name.lower()
    return team_lower in home or team_lower in away


def _match_is_today(match: dict, today: date) -> bool:
    """Check if a fixture match is scheduled for today."""
    # Try status.utcTime first (actual API format)
    status = match.get("status", {})
    if isinstance(status, dict):
        date_str = status.get("utcTime", "")
        if date_str:
            try:
                match_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
                return match_date == today
            except (ValueError, OSError):
                pass

    # Fallback to other date fields
    date_str = match.get("matchDate", match.get("date", match.get("start_time", "")))
    if not date_str:
        return False
    try:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
            try:
                match_date = datetime.strptime(date_str[:19], fmt).date()
                return match_date == today
            except ValueError:
                continue
    except Exception:
        pass
    return False


class LivePoller:
    """Background service that polls for live matches and saves events."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._current_matches: dict[int, dict] = {}  # match_id -> match info
        self._player_db_ids: dict[int, int] = {}  # rapidapi_id -> players.id
        self._fixture_check_date: Optional[date] = None  # last date we checked fixtures
        self._has_match_today: bool = False  # do any tracked teams play today?
        self._cycle_count: int = 0  # track cycles for lineup check throttling
        self._upcoming_cache: list[dict] = []  # cached upcoming matches
        self._upcoming_cache_time: Optional[datetime] = None  # when cache was set
        self._upcoming_cache_ttl: int = 3600  # 1 hour — upcoming matches rarely change
        self._match_added_times: dict[tuple, datetime] = {}  # (match_id, rapidapi_id) -> when added
        self._status_failures: dict[tuple, int] = {}  # (match_id, rapidapi_id) -> consecutive API failures
        self._given_up_match_ids: set[int] = set()  # match_ids removed due to API failures — don't re-add
        self._today_matches_cache: Optional[dict] = None  # cached today's matches (fixture API), None = never cached
        self._today_matches_cache_date: Optional[date] = None  # date of cached fixtures
        self._today_matches_cache_time: Optional[datetime] = None  # when today_matches were cached

    async def start(self):
        """Start the background poller."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Live poller started")

    async def stop(self):
        """Stop the background poller."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Live poller stopped")

    async def _resolve_player_ids(self):
        """Resolve rapidapi_ids to internal player DB IDs."""
        print("=== POLLER: Resolving player IDs ===")
        async with AsyncSessionLocal() as session:
            for rapidapi_id in LIVE_TRACKED_PLAYERS:
                result = await session.execute(
                    select(Player).where(Player.rapidapi_id == rapidapi_id)
                )
                player = result.scalar_one_or_none()
                if player:
                    self._player_db_ids[rapidapi_id] = player.id
                    print(f"=== POLLER: Resolved player rapidapi_id={rapidapi_id} db_id={player.id} ===")
                else:
                    print(f"=== POLLER: Player NOT FOUND rapidapi_id={rapidapi_id} ===")

    async def _run_loop(self):
        """Main poller loop."""
        await self._resolve_player_ids()
        print("=== POLLER: Entering main loop ===")

        while self._running:
            interval = INTERVAL_SLEEPING
            try:
                interval = await self._poll_cycle()
                print(f"=== POLLER: Next cycle in {interval}s ===")
            except Exception as e:
                print(f"=== POLLER: Cycle error: {e} ===")
                logger.error("Poller cycle error", error=str(e), exc_info=True)

            sleep_remaining = interval
            while sleep_remaining > 0 and self._running:
                sleep_chunk = min(10, sleep_remaining)
                await asyncio.sleep(sleep_chunk)
                sleep_remaining -= sleep_chunk

    def _earliest_kickoff_today(self, today_matches: dict) -> Optional[datetime]:
        """Find earliest future kickoff from today's matches."""
        earliest = None
        now = datetime.utcnow()
        for match_info in today_matches.values():
            kickoff_str = match_info.get("kickoff_time", "")
            if not kickoff_str:
                continue
            try:
                kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")).replace(tzinfo=None)
                if kickoff > now and (earliest is None or kickoff < earliest):
                    earliest = kickoff
            except (ValueError, OSError):
                continue
        return earliest

    async def _read_fixture_db_cache(self) -> Optional[dict]:
        """Read fixture check result from Supabase (survives container restarts)."""
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import text
                result = await session.execute(
                    text("SELECT cache_date, has_match FROM poller_cache WHERE cache_key = 'fixture_check'")
                )
                row = result.fetchone()
                if row:
                    return {"date": str(row[0]), "has_match": row[1]}
        except Exception:
            pass
        return None

    async def _write_fixture_db_cache(self, today: date, has_match: bool):
        """Save fixture check result to Supabase."""
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import text
                # Upsert: delete old, insert new
                await session.execute(text("DELETE FROM poller_cache WHERE cache_key = 'fixture_check'"))
                await session.execute(
                    text("INSERT INTO poller_cache (cache_key, cache_date, has_match, updated_at) VALUES ('fixture_check', :d, :h, NOW())"),
                    {"d": today, "h": has_match},
                )
                await session.commit()
        except Exception as e:
            print(f"=== POLLER: DB cache write failed: {e} ===")

    def _read_fixture_file_cache(self) -> Optional[dict]:
        """Read fixture check result from file cache (fallback)."""
        try:
            with open(_FIXTURE_CACHE_FILE, "r") as f:
                data = json.load(f)
            return data
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    def _write_fixture_file_cache(self, today: date, has_match: bool):
        """Save fixture check result to file cache (fallback)."""
        try:
            with open(_FIXTURE_CACHE_FILE, "w") as f:
                json.dump({
                    "date": today.isoformat(),
                    "has_match": has_match,
                }, f)
        except OSError:
            pass

    async def _load_cache_json(self, cache_key: str, max_age_seconds: int = 10800, for_date: Optional[date] = None):
        """Load cached JSON data from poller_cache.cache_data column."""
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import text
                query = "SELECT cache_data, updated_at FROM poller_cache WHERE cache_key = :key"
                params: dict = {"key": cache_key}
                if for_date:
                    query += " AND cache_date = :d"
                    params["d"] = for_date
                result = await session.execute(text(query), params)
                row = result.fetchone()
                if row and row[0]:
                    updated_at = row[1].replace(tzinfo=None) if row[1] else None
                    if updated_at and (datetime.utcnow() - updated_at).total_seconds() < max_age_seconds:
                        data = row[0]
                        if isinstance(data, str):
                            data = json.loads(data)
                        return data
        except Exception:
            pass
        return None

    async def _save_cache_json(self, cache_key: str, data) -> None:
        """Save JSON data to poller_cache.cache_data column."""
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import text
                json_str = json.dumps(data, default=str)
                await session.execute(
                    text("DELETE FROM poller_cache WHERE cache_key = :key"),
                    {"key": cache_key},
                )
                await session.execute(
                    text("INSERT INTO poller_cache (cache_key, cache_date, has_match, cache_data, updated_at) VALUES (:key, CURRENT_DATE, false, CAST(:data AS jsonb), NOW())"),
                    {"key": cache_key, "data": json_str},
                )
                await session.commit()
        except Exception as e:
            print(f"=== POLLER: DB cache JSON save failed for {cache_key}: {e} ===")

    async def _check_fixtures_today(self) -> bool:
        """Check if any tracked team has a match today.

        Uses 3-level cache:
        1. In-memory (fastest, lost on restart)
        2. File cache (survives restart, lost on redeploy)
        3. API call (primary leagues first, then cups)
        """
        today = date.today()

        # Level 1: in-memory cache
        if self._fixture_check_date == today:
            print(f"=== POLLER: Using memory cache: has_match={self._has_match_today} ===")
            return self._has_match_today

        # Level 2: database cache (survives container restarts on Render)
        db_cache = await self._read_fixture_db_cache()
        if db_cache and db_cache.get("date") == today.isoformat():
            has_match = db_cache["has_match"]
            self._fixture_check_date = today
            self._has_match_today = has_match
            print(f"=== POLLER: Using DB cache: has_match={has_match} ===")
            return has_match

        # Level 3: file cache (fallback)
        file_cache = self._read_fixture_file_cache()
        if file_cache and file_cache.get("date") == today.isoformat():
            has_match = file_cache["has_match"]
            self._fixture_check_date = today
            self._has_match_today = has_match
            print(f"=== POLLER: Using FILE cache: has_match={has_match} ===")
            # Backfill DB cache
            await self._write_fixture_db_cache(today, has_match)
            return has_match

        # Level 4: API calls — primary leagues first (5 calls), then cups (8 calls)
        print(f"=== POLLER: Checking fixtures for {today.isoformat()} (no cache) ===")

        tracked_team_names = {
            info["team_name"].lower() for info in LIVE_TRACKED_PLAYERS.values()
        }

        has_match = False
        # Phase 1: primary domestic leagues (5 calls) — most matches are here
        has_match = await self._check_leagues_for_today(PRIMARY_LEAGUE_IDS, tracked_team_names, today)

        # Phase 2: cup/European leagues only if primary found nothing
        if not has_match and CUP_LEAGUE_IDS:
            has_match = await self._check_leagues_for_today(CUP_LEAGUE_IDS, tracked_team_names, today)

        # Cache results (memory + DB + file)
        self._fixture_check_date = today
        self._has_match_today = has_match
        await self._write_fixture_db_cache(today, has_match)
        self._write_fixture_file_cache(today, has_match)

        if not has_match:
            print("=== POLLER: No matches for tracked teams today — sleeping ===")
        else:
            print("=== POLLER: MATCH DAY DETECTED — switching to livescores polling ===")

        return has_match

    async def _check_leagues_for_today(self, league_ids: list, tracked_team_names: set, today: date) -> bool:
        """Check a list of leagues for today's matches. Returns True if found."""
        has_match = False
        for league_id in league_ids:
            try:
                fixtures = await rapidapi_client.get_matches_by_league(league_id)
                if not isinstance(fixtures, list):
                    continue

                for match in fixtures:
                    if not isinstance(match, dict):
                        continue

                    home = match.get("home", match.get("homeTeam", {}))
                    away = match.get("away", match.get("awayTeam", {}))

                    home_name = home.get("name", "").lower() if isinstance(home, dict) else ""
                    away_name = away.get("name", "").lower() if isinstance(away, dict) else ""

                    for team_name in tracked_team_names:
                        if team_name in home_name or team_name in away_name:
                            if _match_is_today(match, today):
                                has_match = True
                                print(f"=== POLLER: MATCH TODAY FOUND: {home_name} vs {away_name} (league {league_id}) ===")
                                break
                    if has_match:
                        break
            except Exception as e:
                print(f"=== POLLER: Fixture check FAILED for league {league_id}: {e} ===")
                logger.warning("Failed to check fixtures", league_id=league_id, error=str(e))

            if has_match:
                break

        return has_match

    async def _poll_cycle(self) -> int:
        """One polling cycle. Returns seconds until next poll."""
        # 1. Check if any tracked team plays today
        has_match = await self._check_fixtures_today()

        if not has_match:
            return INTERVAL_SLEEPING  # 6 hours

        # 2. Find today's matches with tracked teams from fixtures
        today_matches = await self._find_today_tracked_matches()

        if not today_matches:
            self._current_matches = {}
            if self._has_match_today:
                # All matches for tracked teams ended — return to deep sleep
                print("=== POLLER: All today's matches ended — returning to deep sleep ===")
                self._fixture_check_date = None
                self._has_match_today = False
                self._today_matches_cache = None
                await self._write_fixture_db_cache(date.today(), False)
                return INTERVAL_SLEEPING  # 6h — no more matches today
            print("=== POLLER: No live matches with tracked teams yet ===")
            return INTERVAL_PREMATCH  # 30 min — match day but not live yet

        # 3. Separate matches into prematch (not started) and live (started)
        now = datetime.utcnow()

        # Remove stale matches (added >3h ago — API probably stopped responding)
        stale_threshold = 2 * 3600  # 2 hours — no football match lasts longer
        for match_key, info in list(self._current_matches.items()):
            added_time = self._match_added_times.get(match_key)
            if added_time:
                age = (now - added_time).total_seconds()
                if age > stale_threshold:
                    print(f"=== POLLER: STALE match removed match_id={match_key[0]} player={info.get('player_name')} age={age/3600:.1f}h ===")
                    self._current_matches.pop(match_key, None)
                    self._match_added_times.pop(match_key, None)

        prematch_matches = {}
        live_matches = {}

        for rapidapi_id, match_info in today_matches.items():
            match_id = match_info["match_id"]
            # Skip matches we already gave up on (finished, API failures)
            if match_id in self._given_up_match_ids:
                print(f"=== POLLER: Skipping given-up match_id={match_id} ===")
                continue

            match_status = match_info.get("status", "scheduled")
            if match_status == "live":
                live_matches[rapidapi_id] = match_info
            else:
                # Check if kickoff within prematch window
                kickoff_str = match_info.get("kickoff_time", "")
                if kickoff_str:
                    try:
                        kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        hours_until = (kickoff - now).total_seconds() / 3600
                        if hours_until <= PREMATCH_WINDOW_HOURS:
                            prematch_matches[rapidapi_id] = match_info
                            print(f"=== POLLER: PREMATCH match_id={match_info['match_id']} kickoff in {hours_until:.1f}h ===")
                    except (ValueError, OSError):
                        pass

        # 4. Smart sleep: matches known but far from kickoff — sleep to save API credits
        if not live_matches and not prematch_matches:
            earliest = self._earliest_kickoff_today(today_matches)
            if earliest:
                wake_at = earliest - timedelta(hours=PREMATCH_WAKEUP_BUFFER_HOURS)
                sleep_seconds = int((wake_at - datetime.utcnow()).total_seconds())
                if sleep_seconds > 300:  # more than 5 min — worth sleeping
                    print(f"=== POLLER: Smart sleep — next kickoff at {earliest}, waking at {wake_at} ({sleep_seconds/3600:.1f}h) ===")
                    return sleep_seconds
            return INTERVAL_PREMATCH  # fallback: no kickoff time known

        # 5. Handle prematch matches — check lineups (always, not only when no live)
        if prematch_matches:
            await self._handle_prematch(prematch_matches)

        # 6. Handle live matches — only actual live matches
        if not live_matches:
            # Use faster interval if kickoff has passed (waiting for live transition)
            any_kickoff_passed = False
            for match_info in prematch_matches.values():
                kickoff_str = match_info.get("kickoff_time", "")
                if kickoff_str:
                    try:
                        kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        if (datetime.utcnow() - kickoff).total_seconds() > 0:
                            any_kickoff_passed = True
                            break
                    except (ValueError, OSError):
                        pass
            if any_kickoff_passed:
                return INTERVAL_PREMATCH_KICKOFF  # 1 min — kickoff passed, aggressively check
            return INTERVAL_PREMATCH_LINEUP  # 2 min — prematch, waiting for kickoff

        next_interval = INTERVAL_PREMATCH

        # Fetch per-match data ONCE, share across all players in that match
        match_data_cache: dict[int, dict] = {}  # match_id -> {status_raw, lineup_data}
        checked_match_ids = set()
        for rapidapi_id, match_info in live_matches.items():
            match_id = match_info["match_id"]
            if match_id in checked_match_ids:
                continue
            checked_match_ids.add(match_id)

            # Get match status (minute, score, ongoing/finished) — single call per match
            try:
                status_raw = await rapidapi_client.get_match_status(match_id)
                match_data_cache[match_id] = {"status_raw": status_raw}
            except Exception as e:
                print(f"=== POLLER: Failed to get match status for {match_id}: {e} ===")
                match_data_cache[match_id] = {"status_raw": None}

            # Get lineup data ONCE per match (not per player)
            home_name = match_info.get("home_team", "")
            try:
                first_player_info = LIVE_TRACKED_PLAYERS.get(rapidapi_id, {})
                is_home = first_player_info.get("team_name", "").lower() in home_name.lower()
                if is_home:
                    lineup_data = await rapidapi_client.get_lineup_home(match_id)
                else:
                    lineup_data = await rapidapi_client.get_lineup_away(match_id)
                match_data_cache[match_id]["lineup_data"] = lineup_data
            except Exception as e:
                print(f"=== POLLER: Failed to get lineup for {match_id}: {e} ===")
                match_data_cache[match_id]["lineup_data"] = None

        # Process each tracked player using cached match data
        for rapidapi_id, match_info in live_matches.items():
            info = LIVE_TRACKED_PLAYERS[rapidapi_id]
            match_id = match_info["match_id"]
            home_name = match_info.get("home_team", "")
            away_name = match_info.get("away_team", "")
            match_key = (match_id, rapidapi_id)
            cached = match_data_cache.get(match_id, {})
            match_status_raw = cached.get("status_raw")
            lineup_data = cached.get("lineup_data")

            # Check lineup on first detection, or retry if previous check failed
            if match_key not in self._current_matches:
                if lineup_data:
                    lineup_status = _find_player_in_lineup(lineup_data, rapidapi_id, info["name"])
                else:
                    lineup_status = await self._check_lineup(match_id, rapidapi_id, match_info)
                print(f"=== POLLER: Match detected match_id={match_id} {home_name} vs {away_name} player={info['name']} lineup={lineup_status} ===")
                self._current_matches[match_key] = {
                    "rapidapi_id": rapidapi_id,
                    "lineup_status": lineup_status,
                    "home_team": home_name,
                    "away_team": away_name,
                    "home_score": match_info.get("home_score", 0),
                    "away_score": match_info.get("away_score", 0),
                    "status": "live",
                    "minute": "",
                    "competition": match_info.get("competition", ""),
                    "kickoff_time": match_info.get("kickoff_time", ""),
                }
                self._match_added_times[match_key] = datetime.utcnow()
            elif self._current_matches[match_key].get("lineup_status") == "unknown":
                if lineup_data:
                    lineup_status = _find_player_in_lineup(lineup_data, rapidapi_id, info["name"])
                else:
                    lineup_status = await self._check_lineup(match_id, rapidapi_id, match_info)
                print(f"=== POLLER: Retrying lineup for match_id={match_id} player={info['name']} result={lineup_status} ===")
                self._current_matches[match_key]["lineup_status"] = lineup_status

            # Parse match status — try get_match_status first, fallback to fixture data
            match_status = _parse_match_status(match_status_raw) if match_status_raw else None

            # If get_match_status failed, try fixture data as fallback
            if match_status is None:
                self._status_failures[match_key] = self._status_failures.get(match_key, 0) + 1
                if self._status_failures[match_key] >= 10:
                    print(f"=== POLLER: Giving up on match_id={match_id} after {self._status_failures[match_key]} consecutive status API failures ===")
                    self._current_matches.pop(match_key, None)
                    self._match_added_times.pop(match_key, None)
                    self._status_failures.pop(match_key, None)
                    self._given_up_match_ids.add(match_id)
                    continue
                # Keep match as live (fixture API said it was live) — just can't get score details
                self._current_matches[match_key]["status"] = "live"
            else:
                self._status_failures.pop(match_key, None)

            # Check if match ended
            if match_status and match_status.get("finished"):
                print(f"=== POLLER: Match ended match_id={match_id} ===")
                self._current_matches.pop(match_key, None)
                self._today_matches_cache = None  # Invalidate so next cycle gets fresh data
                continue

            # Update scores and minute from match_status (single source of truth)
            if match_status:
                if match_status.get("minute"):
                    self._current_matches[match_key]["minute"] = match_status["minute"]
                if match_status.get("home_score") is not None:
                    self._current_matches[match_key]["home_score"] = match_status["home_score"]
                if match_status.get("away_score") is not None:
                    self._current_matches[match_key]["away_score"] = match_status["away_score"]
                self._current_matches[match_key]["status"] = "live" if match_status.get("ongoing") else self._current_matches[match_key].get("status", "unknown")

                # Match not ongoing, not finished, and no live data — false positive, remove it
                has_live_data = (
                    self._current_matches[match_key].get("home_score")
                    or self._current_matches[match_key].get("away_score")
                    or self._current_matches[match_key].get("minute")
                )
                if not match_status.get("ongoing") and not match_status.get("finished") and not has_live_data:
                    print(f"=== POLLER: match_id={match_id} not live (no score/minute) — removing false positive ===")
                    self._current_matches.pop(match_key, None)
                    continue

            # Extract events from cached lineup data (goals, assists, subIn, subOut, cards)
            tracked_events = []
            if lineup_data:
                try:
                    tracked_events = _extract_events_from_lineup(lineup_data, info["name"])
                    print(f"=== POLLER: EVENTS FOUND for {info['name']}: {len(tracked_events)} events ===")
                    if tracked_events:
                        for evt in tracked_events:
                            print(f"=== POLLER: EVENT: {evt} ===")
                    # Update lineup status from fresh data
                    # But NEVER override initial status once the match has started
                    # (player who started on bench and came on as sub should stay "bench")
                    current_lineup = self._current_matches[match_key].get("lineup_status")
                    if current_lineup not in ("starting", "bench"):
                        new_status = _find_player_in_lineup(lineup_data, rapidapi_id, info["name"])
                        if new_status != "absent" or current_lineup == "unknown":
                            self._current_matches[match_key]["lineup_status"] = new_status
                except Exception as e:
                    print(f"=== POLLER: Failed to extract events for match_id={match_id}: {e} ===")

            if tracked_events:
                await self._save_events(match_id, rapidapi_id, tracked_events, match_info)

            # Determine next interval
            match_state = self._current_matches.get(match_key, {})
            lineup = match_state.get("lineup_status", "absent")

            if lineup == "starting" or lineup == "absent":
                next_interval = min(next_interval, INTERVAL_TRACKING)
            elif lineup == "bench":
                next_interval = min(next_interval, INTERVAL_BENCH)

        return next_interval if self._current_matches else INTERVAL_PREMATCH

    async def _find_today_tracked_matches(self) -> dict:
        """Find today's matches involving tracked teams from fixtures.
        Results are cached with 10min TTL to avoid hammering fixture API."""
        today = date.today()

        # Return cached results if fresh (within 30 minutes)
        cache_ttl = 1800  # 30 minutes
        if (
            self._today_matches_cache is not None
            and self._today_matches_cache_date == today
            and self._today_matches_cache_time
            and (datetime.utcnow() - self._today_matches_cache_time).total_seconds() < cache_ttl
        ):
            print(f"=== POLLER: Using cached today_matches ({len(self._today_matches_cache)} players) ===")
            return self._today_matches_cache

        # DB cache (survives container restarts and long smart sleep)
        db_cached = await self._load_cache_json("today_matches", max_age_seconds=10800, for_date=today)
        if db_cached is not None:
            cached_matches = {}
            now = datetime.utcnow()
            for k, v in db_cached.items():
                match_info = v if isinstance(v, dict) else {}
                kickoff_str = match_info.get("kickoff_time", "")
                if kickoff_str:
                    try:
                        kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        if (now - kickoff).total_seconds() > 4 * 3600:
                            continue
                    except (ValueError, OSError):
                        pass
                cached_matches[int(k)] = match_info
            if cached_matches:
                self._today_matches_cache = cached_matches
                self._today_matches_cache_date = today
                self._today_matches_cache_time = datetime.utcnow()
                print(f"=== POLLER: Using DB-cached today_matches ({len(cached_matches)} players) ===")
                return cached_matches

        tracked_team_names = {
            info["team_name"].lower() for info in LIVE_TRACKED_PLAYERS.values()
        }

        today_matches = {}

        # Phase 1: primary domestic leagues (5 calls) — most matches found here
        for league_id in PRIMARY_LEAGUE_IDS:
            try:
                fixtures = await rapidapi_client.get_matches_by_league(league_id)
                if not isinstance(fixtures, list):
                    continue

                for match in fixtures:
                    if not isinstance(match, dict):
                        continue

                    home = match.get("home", match.get("homeTeam", {}))
                    away = match.get("away", match.get("awayTeam", {}))

                    home_name = home.get("name", "") if isinstance(home, dict) else ""
                    away_name = away.get("name", "") if isinstance(away, dict) else ""

                    home_score = home.get("score", 0) if isinstance(home, dict) else 0
                    away_score = away.get("score", 0) if isinstance(away, dict) else 0

                    for rapidapi_id, info in LIVE_TRACKED_PLAYERS.items():
                        team_lower = info["team_name"].lower()
                        if team_lower in home_name.lower() or team_lower in away_name.lower():
                            if _match_is_today(match, today):
                                # Check if match is live or upcoming
                                status = match.get("status", {})
                                is_started = status.get("started", False) if isinstance(status, dict) else False
                                is_finished = status.get("finished", True) if isinstance(status, dict) else True

                                match_id = match.get("id")
                                try:
                                    match_id = int(match_id)
                                except (ValueError, TypeError):
                                    continue

                                # Skip finished matches — no point tracking them
                                if is_finished or match_id in self._given_up_match_ids:
                                    continue

                                # Store match info
                                today_matches[rapidapi_id] = {
                                    "match_id": match_id,
                                    "home_team": home_name,
                                    "away_team": away_name,
                                    "home_score": home_score,
                                    "away_score": away_score,
                                    "status": "live" if is_started and not is_finished else "scheduled",
                                    "competition": match.get("tournament", {}).get("name", "") if isinstance(match.get("tournament"), dict) else "",
                                    "kickoff_time": match.get("status", {}).get("utcTime", "") if isinstance(match.get("status"), dict) else "",
                                }

            except Exception as e:
                print(f"=== POLLER: Fixture lookup failed for league {league_id}: {e} ===")

        # Phase 2: cup/European leagues (up to 8 calls) — only if primary found nothing
        if not today_matches and CUP_LEAGUE_IDS:
            for league_id in CUP_LEAGUE_IDS:
                try:
                    fixtures = await rapidapi_client.get_matches_by_league(league_id)
                    if not isinstance(fixtures, list):
                        continue

                    for match in fixtures:
                        if not isinstance(match, dict):
                            continue

                        home = match.get("home", match.get("homeTeam", {}))
                        away = match.get("away", match.get("awayTeam", {}))

                        home_name = home.get("name", "") if isinstance(home, dict) else ""
                        away_name = away.get("name", "") if isinstance(away, dict) else ""

                        home_score = home.get("score", 0) if isinstance(home, dict) else 0
                        away_score = away.get("score", 0) if isinstance(away, dict) else 0

                        for rapidapi_id, info in LIVE_TRACKED_PLAYERS.items():
                            team_lower = info["team_name"].lower()
                            if team_lower in home_name.lower() or team_lower in away_name.lower():
                                if _match_is_today(match, today):
                                    status = match.get("status", {})
                                    is_started = status.get("started", False) if isinstance(status, dict) else False
                                    is_finished = status.get("finished", True) if isinstance(status, dict) else True

                                    match_id = match.get("id")
                                    try:
                                        match_id = int(match_id)
                                    except (ValueError, TypeError):
                                        continue

                                    if is_finished or match_id in self._given_up_match_ids:
                                        continue

                                    today_matches[rapidapi_id] = {
                                        "match_id": match_id,
                                        "home_team": home_name,
                                        "away_team": away_name,
                                        "home_score": home_score,
                                        "away_score": away_score,
                                        "status": "live" if is_started and not is_finished else "scheduled",
                                        "competition": match.get("tournament", {}).get("name", "") if isinstance(match.get("tournament"), dict) else "",
                                        "kickoff_time": match.get("status", {}).get("utcTime", "") if isinstance(match.get("status"), dict) else "",
                                    }

                except Exception as e:
                    print(f"=== POLLER: Fixture lookup failed for league {league_id}: {e} ===")

        # Cache results with timestamp
        self._today_matches_cache = today_matches
        self._today_matches_cache_date = today
        self._today_matches_cache_time = datetime.utcnow()
        await self._save_cache_json("today_matches", {str(k): v for k, v in today_matches.items()})
        return today_matches

    async def _check_lineup(self, match_id: int, rapidapi_id: int, match: dict) -> str:
        """Check if tracked player is in the lineup."""
        home_team = match.get("home_team", "")
        info = LIVE_TRACKED_PLAYERS[rapidapi_id]
        team_name = info["team_name"]

        is_home = team_name.lower() in home_team.lower()

        try:
            if is_home:
                lineup_data = await rapidapi_client.get_lineup_home(match_id)
            else:
                lineup_data = await rapidapi_client.get_lineup_away(match_id)
            print(f"=== POLLER: RAW LINEUP for match {match_id}: {str(lineup_data)[:1000]} ===")
            result = _find_player_in_lineup(lineup_data, rapidapi_id, info["name"])
            print(f"=== POLLER: Lineup check result for {info['name']}: {result} ===")
            return result
        except Exception as e:
            logger.warning("Lineup check failed, returning unknown", error=str(e))
            return "unknown"

    def _check_sub_in(self, match_detail: dict, rapidapi_id: int) -> bool:
        """Check if player came on as substitute in match events."""
        events = match_detail.get("events", match_detail.get("incidents", []))
        if not isinstance(events, list):
            return False

        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("type", "").lower() in ("substitution", "subin"):
                player_name = event.get("playerName", event.get("player", ""))
                if isinstance(player_name, dict):
                    player_name = player_name.get("name", "")
                tracked_name = LIVE_TRACKED_PLAYERS[rapidapi_id]["name"]
                if tracked_name.lower() in player_name.lower():
                    return True
        return False

    async def _save_events(
        self,
        match_id: int,
        rapidapi_id: int,
        events: list[dict],
        match_info: dict,
    ):
        """Save new events to database (deduplication via UNIQUE constraint)."""
        db_player_id = self._player_db_ids.get(rapidapi_id)
        player_name = LIVE_TRACKED_PLAYERS[rapidapi_id]["name"]

        async with AsyncSessionLocal() as session:
            for event in events:
                try:
                    db_event = LiveMatchEvent(
                        match_id=match_id,
                        player_id=db_player_id,
                        player_name=player_name,
                        event_type=event["event_type"],
                        minute=event.get("minute"),
                        match_score=event.get("match_score", match_info.get("match_score", "")),
                        home_team=match_info.get("home_team"),
                        away_team=match_info.get("away_team"),
                        competition=match_info.get("competition"),
                        season="2025/26",
                    )
                    session.add(db_event)
                    await session.commit()
                    logger.info(
                        "Event saved",
                        match_id=match_id,
                        player=player_name,
                        event_type=event["event_type"],
                        minute=event.get("minute"),
                    )
                except Exception as e:
                    await session.rollback()
                    if "uq_live_event_dedup" not in str(e).lower() and "unique" not in str(e).lower():
                        logger.warning("Failed to save event", error=str(e))

    def get_current_matches(self) -> list[dict]:
        """Get current live matches (for API endpoint)."""
        result = []
        for (mid, rid), info in self._current_matches.items():
            rapidapi_id = info.get("rapidapi_id")
            player_name = LIVE_TRACKED_PLAYERS.get(rapidapi_id, {}).get("name", "") if rapidapi_id else ""
            result.append({
                "match_id": mid,
                "rapidapi_id": rapidapi_id,
                "lineup_status": info.get("lineup_status"),
                "player_name": player_name,
                "home_team": info.get("home_team", ""),
                "away_team": info.get("away_team", ""),
                "home_score": info.get("home_score", 0),
                "away_score": info.get("away_score", 0),
                "minute": info.get("minute"),
                "status": info.get("status", "unknown"),
                "competition": info.get("competition", ""),
                "kickoff_time": info.get("kickoff_time", ""),
            })
        return result

    def get_prematch_matches(self) -> list[dict]:
        """Get prematch matches (not yet started, lineups known)."""
        result = []
        for (mid, rid), info in self._current_matches.items():
            if info.get("status") != "prematch":
                continue
            rapidapi_id = info.get("rapidapi_id")
            player_name = LIVE_TRACKED_PLAYERS.get(rapidapi_id, {}).get("name", "") if rapidapi_id else ""
            result.append({
                "match_id": mid,
                "rapidapi_id": rapidapi_id,
                "lineup_status": info.get("lineup_status"),
                "player_name": player_name,
                "home_team": info.get("home_team", ""),
                "away_team": info.get("away_team", ""),
                "status": "prematch",
                "competition": info.get("competition", ""),
                "kickoff_time": info.get("kickoff_time", ""),
            })
        return result

    async def _handle_prematch(self, prematch_matches: dict):
        """Check lineups for matches about to start.

        When kickoff has passed >5 min, verifies via match_status endpoint
        whether the match actually started (handles API delays + match delays).
        """
        now = datetime.utcnow()
        for rapidapi_id, match_info in prematch_matches.items():
            info = LIVE_TRACKED_PLAYERS[rapidapi_id]
            match_id = match_info["match_id"]
            match_key = (match_id, rapidapi_id)

            # Check if kickoff time has passed (>5 min ago)
            kickoff_str = match_info.get("kickoff_time", "")
            kickoff_passed = False
            if kickoff_str:
                try:
                    kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    if (now - kickoff).total_seconds() > 300:
                        kickoff_passed = True
                except (ValueError, OSError):
                    pass

            # Check if already transitioned to live in a previous cycle
            existing = self._current_matches.get(match_key)
            already_live = existing and existing.get("status") == "live"

            if already_live:
                # Already live — don't overwrite back to prematch
                continue

            # Verify if match has started when kickoff passed
            if kickoff_passed:
                match_started, match_status = await self._check_match_started(match_id, kickoff_str, now)

                if match_started is False:
                    # Match confirmed NOT started (API returned valid data)
                    pass
                elif match_started is True:
                    print(f"=== POLLER: Match started — transitioning match_id={match_id} {info['name']} to live ===")
                    self._current_matches[match_key] = {
                        "rapidapi_id": rapidapi_id,
                        "lineup_status": existing.get("lineup_status", "unknown") if existing else "unknown",
                        "home_team": match_info.get("home_team", ""),
                        "away_team": match_info.get("away_team", ""),
                        "home_score": match_status.get("home_score", 0) if match_status else 0,
                        "away_score": match_status.get("away_score", 0) if match_status else 0,
                        "status": "live",
                        "minute": match_status.get("minute", "") if match_status else "",
                        "competition": match_info.get("competition", ""),
                        "kickoff_time": kickoff_str,
                    }
                    self._match_added_times[match_key] = datetime.utcnow()
                    continue
                elif match_started == "finished":
                    print(f"=== POLLER: match already finished for match_id={match_id} {info['name']} — skipping ===")
                    self._given_up_match_ids.add(match_id)
                    continue

            # Still prematch — cache lineup, retry if previous check failed
            if existing and existing.get("status") == "prematch" and existing.get("lineup_status") != "unknown":
                lineup_status = existing.get("lineup_status", "absent")
            else:
                lineup_status = await self._check_lineup(match_id, rapidapi_id, match_info)
                print(f"=== POLLER: PREMATCH lineup for {info['name']}: {lineup_status} ===")

            self._current_matches[match_key] = {
                "rapidapi_id": rapidapi_id,
                "lineup_status": lineup_status,
                "home_team": match_info.get("home_team", ""),
                "away_team": match_info.get("away_team", ""),
                "home_score": 0,
                "away_score": 0,
                "status": "prematch",
                "competition": match_info.get("competition", ""),
                "kickoff_time": kickoff_str,
            }

    async def _check_match_started(self, match_id: int, kickoff_str: str, now: datetime) -> tuple:
        """Check if a match has started, with fallback strategies.

        Returns: (started, match_status_or_None)
        - (True, {...}) — match is live
        - ("finished", {...}) — match is finished
        - (False, {...}) — match confirmed not started
        - (None, None) — couldn't determine
        """
        # Strategy 1: match_status endpoint
        try:
            match_status_raw = await rapidapi_client.get_match_status(match_id)
            match_status = _parse_match_status(match_status_raw)
            if match_status:
                if match_status.get("finished"):
                    return ("finished", match_status)
                elif match_status.get("started") or match_status.get("ongoing"):
                    return (True, match_status)
                else:
                    return (False, match_status)
        except Exception as e:
            print(f"=== POLLER: get_match_status failed for match_id={match_id}: {e} ===")

        # No further strategies — never assume live based on time alone.
        # Wait for get_match_status confirmation regardless of delay duration.
        # Poller retries every 2 min after kickoff, so it will detect
        # the start whenever the API reports it.
        return (None, None)

    async def get_upcoming_matches(self, limit: int = 5) -> list[dict]:
        """Get upcoming matches (next 7 days) with tracked Polish players.
        Results are cached for 5 minutes. Matches currently live are excluded."""
        now = datetime.utcnow()
        # Collect match_ids that are currently live/prematch in _current_matches
        live_match_ids = {mk[0] for mk, info in self._current_matches.items() if info.get("status") == "live"}
        if self._upcoming_cache and self._upcoming_cache_time:
            if (now - self._upcoming_cache_time).total_seconds() < self._upcoming_cache_ttl:
                filtered = [m for m in self._upcoming_cache if m.get("match_id") not in live_match_ids]
                return filtered[:limit]

        # DB cache (survives restarts)
        db_cached = await self._load_cache_json("upcoming_matches", max_age_seconds=10800)
        if db_cached and isinstance(db_cached, list):
            self._upcoming_cache = db_cached
            self._upcoming_cache_time = datetime.utcnow()
            filtered = [m for m in db_cached if m.get("match_id") not in live_match_ids]
            return filtered[:limit]

        now = datetime.utcnow()
        upcoming = []

        for league_id in TRACKED_LEAGUE_IDS:
            try:
                fixtures = await rapidapi_client.get_matches_by_league(league_id)
                if not isinstance(fixtures, list):
                    continue

                for match in fixtures:
                    if not isinstance(match, dict):
                        continue

                    status_data = match.get("status", {})
                    if not isinstance(status_data, dict):
                        continue

                    # Skip finished, live, or currently-tracked matches
                    event_id = match.get("id", match.get("eventId"))
                    if status_data.get("finished") or status_data.get("started") or event_id in live_match_ids:
                        continue

                    utc_time = status_data.get("utcTime", "")
                    if not utc_time:
                        continue

                    try:
                        kickoff = datetime.fromisoformat(utc_time.replace("Z", "+00:00")).replace(tzinfo=None)
                    except (ValueError, OSError):
                        continue

                    # Only future matches within 7 days
                    hours_until = (kickoff - now).total_seconds() / 3600
                    if hours_until < 0 or hours_until > 168:
                        continue

                    home = match.get("home", match.get("homeTeam", {}))
                    away = match.get("away", match.get("awayTeam", {}))
                    home_name = home.get("name", "") if isinstance(home, dict) else ""
                    away_name = away.get("name", "") if isinstance(away, dict) else ""

                    for rapidapi_id, info in LIVE_TRACKED_PLAYERS.items():
                        team_lower = info["team_name"].lower()
                        if team_lower in home_name.lower() or team_lower in away_name.lower():
                            match_id = match.get("id")
                            try:
                                match_id = int(match_id)
                            except (ValueError, TypeError):
                                continue

                            competition = LEAGUE_NAMES.get(league_id, "")
                            stage = ""
                            tournament = match.get("tournament", {})
                            if isinstance(tournament, dict):
                                stage = tournament.get("stage", "")

                            upcoming.append({
                                "match_id": match_id,
                                "home_team": home_name,
                                "away_team": away_name,
                                "kickoff_time": utc_time,
                                "competition": competition,
                                "stage": stage,
                                "player_name": info["name"],
                                "player_team": info["team_name"],
                                "_hours_until": hours_until,
                            })
            except Exception as e:
                logger.warning("Failed to get upcoming matches", league_id=league_id, error=str(e))

        # Sort by kickoff time, closest first
        upcoming.sort(key=lambda x: x["_hours_until"])
        self._upcoming_cache = upcoming
        self._upcoming_cache_time = datetime.utcnow()

        # Smart cache: expire right before the next match (min 1h)
        if upcoming:
            hours_to_next = upcoming[0]["_hours_until"]
            self._upcoming_cache_ttl = max(3600, int((hours_to_next - 0.5) * 3600))
        else:
            self._upcoming_cache_ttl = 6 * 3600  # no matches at all — recheck in 6h

        await self._save_cache_json("upcoming_matches", upcoming)
        return upcoming[:limit]

    def is_live(self) -> bool:
        """Check if any tracked match is currently live."""
        return any(
            info.get("status") not in ("prematch",)
            for info in self._current_matches.values()
        )


# Singleton
live_poller = LivePoller()
