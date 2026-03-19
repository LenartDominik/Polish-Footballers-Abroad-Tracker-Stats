# -*- coding: utf-8 -*-
"""Sync: Polish players with minutes from lineups. Supports incremental and full sync."""

import argparse
import asyncio
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

# Fix Windows encoding issues
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ['PYTHONIOENCODING'] = 'utf-8'

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
import httpx

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Player, PlayerStats, PlayerStatsByCompetition, SyncState, SyncedMatch
from app.services.rapidapi import calculate_per_90

load_dotenv()

# Configuration
API_HOST = "free-api-live-football-data.p.rapidapi.com"
API_KEY = settings.rapidapi_key

# Polish player IDs to track: {rapidapi_id: {"name": str, "position": str}}
# Positions: GK (bramkarz), DF (obrońca), MF (pomocnik), FW (napastnik)
POLISH_PLAYERS = {
    93447: {"name": "Robert Lewandowski", "position": "FW"},
    169718: {"name": "Wojciech Szczęsny", "position": "GK"},
    543298: {"name": "Krzysztof Piątek", "position": "FW"},
    362212: {"name": "Piotr Zieliński", "position": "MF"},
    1647807: {"name": "Oskar Pietuszewski", "position": "FW"},
    490868: {"name": "Jan Bednarek", "position": "DF"},
    1021834: {"name": "Jakub Kiwior", "position": "DF"},
    760722: {"name": "Kamil Grabara", "position": "GK"},
    908847: {"name": "Mateusz Żukowski", "position": "FW"},
    630036: {"name": "Mateusz Lis", "position": "GK"},
    954194: {"name": "Mateusz Bogusz", "position": "MF"},
    742332: {"name": "Bartosz Slisz", "position": "MF"},
    1051411: {"name": "Kacper Kozłowski", "position": "MF"},
}

# Teams to sync with multiple competitions
TEAMS = {
    8634: {
        "name": "FC Barcelona",
        "competitions": [
            {"name": "La Liga", "league_id": 87},
            {"name": "Copa del Rey", "league_id": 138},
            {"name": "Supercopa", "league_id": 139},
            {"name": "Champions League", "league_id": 42},
        ],
    },
    203826: {
        "name": "Al-Duhail SC",
        "competitions": [
            {"name": "Qatar Stars League", "league_id": 535},
            {"name": "QSL Cup", "league_id": 11017},
            {"name": "AFC Champions League Elite", "league_id": 525},
            {"name": "Amir of Qatar Cup", "league_id": 11018},
            {"name": "Qatar Cup", "league_id": 11016},
        ],
    },
    8636: {
        "name": "Inter",
        "competitions": [
            {"name": "Serie A", "league_id": 55},
            {"name": "Coppa Italia", "league_id": 141},
            {"name": "Champions League", "league_id": 42},
            {"name": "Supercoppa", "league_id": 222},
        ],
    },
    9773: {
        "name": "FC Porto",
        "competitions": [
            {"name": "Primeira Liga", "league_id": 61},
            {"name": "Taça de Portugal", "league_id": 186},
            {"name": "Taça da Liga", "league_id": 97},
            {"name": "Supertaça", "league_id": 532},
            {"name": "Champions League", "league_id": 42},
            {"name": "Europa League", "league_id": 73},
            {"name": "Europa League Qualification", "league_id": 10613},
        ],
    },
    8721: {
        "name": "VfL Wolfsburg",
        "competitions": [
            {"name": "2. Bundesliga", "league_id": 54},
            {"name": "DFB-Pokal", "league_id": 209},
        ],
    },
    8188: {
        "name": "1. FC Magdeburg",
        "competitions": [
            {"name": "2. Bundesliga", "league_id": 146},
            {"name": "DFB-Pokal", "league_id": 209},
        ],
    },
    1925:{
        "name": "Göztepe",
        "competitions": [
            {"name": "Super Lig", "league_id": 71},
            {"name": "Turkish Cup", "league_id": 151},
        ],
    },
    8259: {
        "name": "Houston Dynamo FC",
        "competitions": [
            {"name": "MLS", "league_id": 130},
            {"name": "US Open Cup", "league_id": 9441},
        ],
},
    8595: {
        "name": "Brøndby IF",
        "competitions": [
            {"name": "Superligaen", "league_id": 46},
            {"name": "DBU Pokalen", "league_id": 10046},
        ],
},  
    4081: {
        "name": "Gaziantep FK",
        "competitions": [
            {"name": "Süper Lig", "league_id": 71},
            {"name": "Turkish Cup", "league_id": 151},
        ],
}
}

CURRENT_SEASON = "2025/26"
CACHE_TTL_HOURS = 24
SYNC_INTERVAL_HOURS = 12  # Minimum time between syncs


# Competition type mapping
def map_competition_type(competition_name: str) -> str:
    """Map competition name to type (league, european, domestic)."""
    name_lower = competition_name.lower()

    # International/continental competitions (Champions League, etc.)
    if any(x in name_lower for x in ["champions league", "europa league", "conference league", "afc champions"]):
        return "european"

    # Domestic cups (national cups, supercups)
    # Note: "cup" is a common suffix for domestic cups
    if any(x in name_lower for x in ["copa del rey", "supercopa", "copa", "taça", "taca", "qsl", "amir", "dfb-pokal", "pokal"]):
        return "domestic"
    # Also match "cup" but NOT "league cup" variations that are actually leagues
    if "cup" in name_lower and "league" not in name_lower and "stars" not in name_lower:
        return "domestic"

    # Default: league (national league competitions)
    return "league"


# CLI Arguments
def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Sync Polish players stats")
    parser.add_argument("--full", action="store_true", help="Full sync (all matches, ignore cache)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving to database")
    parser.add_argument("--player", type=int, help="Sync only specific player by rapidapi_id (e.g., 1647807 for Pietuszewski)")
    parser.add_argument("--force", action="store_true", help="Force sync, ignore cache timing")
    parser.add_argument("--gk-only", action="store_true", help="Sync only goalkeepers")
    return parser.parse_args()


# Map player_id to team_id for --player option
PLAYER_TEAMS = {
    93447: 8634,    # Lewandowski -> Barcelona
    169718: 8634,   # Szczęsny -> Barcelona
    543298: 203826, # Piątek -> Al-Duhail
    362212: 8636,   # Zieliński -> Inter
    1647807: 9773,  # Pietuszewski -> Porto
    490868: 9773,   # Bednarek -> Porto
    1021834: 9773,  # Kiwior -> Porto
    760722: 8721,   # Grabara -> Wolfsburg
    908847: 8188,   # Żukowski -> Magdeburg
    630036: 1925,   # Lis -> Göztepe
    954194: 8259,   #Bogusz - Houston Dynamo FC
    742332: 8595,   #Slisz - Brøndby IF
    1051411: 4081,  # Kacper Kozłowski - Gaziantep FK

}


# Sync state helpers
async def get_sync_state(session, team_id: int, competition_id: int) -> SyncState | None:
    """Get sync state for a team/competition combination."""
    result = await session.execute(
        select(SyncState).where(
            SyncState.team_id == team_id,
            SyncState.competition_id == competition_id,
            SyncState.season == CURRENT_SEASON,
        )
    )
    return result.scalar_one_or_none()


async def update_sync_state(session, team_id: int, team_name: str, competition_id: int,
                            competition_name: str, last_match_id: int, matches_synced: int):
    """Update or create sync state after processing matches."""
    sync_state = await get_sync_state(session, team_id, competition_id)

    if sync_state:
        sync_state.last_sync_at = datetime.utcnow()
        sync_state.last_match_id = last_match_id
        sync_state.matches_synced += matches_synced
        sync_state.next_sync_at = datetime.utcnow() + timedelta(hours=SYNC_INTERVAL_HOURS)
    else:
        sync_state = SyncState(
            team_id=team_id,
            team_name=team_name,
            competition_id=competition_id,
            competition_name=competition_name,
            season=CURRENT_SEASON,
            last_sync_at=datetime.utcnow(),
            last_match_id=last_match_id,
            matches_synced=matches_synced,
            next_sync_at=datetime.utcnow() + timedelta(hours=SYNC_INTERVAL_HOURS),
        )
        session.add(sync_state)


async def is_match_synced(session, match_id: int, team_id: int) -> bool:
    """Check if a match has already been synced (deduplication)."""
    result = await session.execute(
        select(SyncedMatch).where(
            SyncedMatch.match_id == match_id,
            SyncedMatch.team_id == team_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def mark_match_synced(session, match_id: int, team_id: int, competition_id: int):
    """Mark a match as synced to prevent duplicate processing."""
    stmt = insert(SyncedMatch).values(
        match_id=match_id,
        team_id=team_id,
        competition_id=competition_id,
    ).on_conflict_do_nothing(constraint="uq_match_team")
    await session.execute(stmt)


async def sync_team_v2(team_id: int, team_info: dict, session, args, player_filter: list[int] | None = None):
    """Sync Polish players with incremental support and per-competition stats.

    Args:
        player_filter: If set, only sync these specific players (list of rapidapi_id)
    """
    print(f"\n{'='*60}")
    print(f"SYNC: {team_info['name']} - {'FULL' if args.full else 'INCREMENTAL'}")
    if player_filter:
        names = [POLISH_PLAYERS.get(pid, {}).get('name', str(pid)) for pid in player_filter]
        print(f"Player filter: {names}")
    print(f"{'='*60}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Collect stats per competition
        stats_by_competition = defaultdict(lambda: defaultdict(lambda: {
            "minutes": 0, "goals": 0, "assists": 0,
            "yellow_cards": 0, "red_cards": 0,
            "matches_total": 0, "matches_started": 0, "matches_subbed": 0,
            "ratings": [],
            # GK stats
            "clean_sheets": 0, "saves": 0, "goals_against": 0,
            "shots_on_target_against": 0,
        }))

        # Track processed matches for dedup
        matches_processed = 0
        api_calls = 0

        for competition in team_info.get("competitions", []):
            comp_name = competition["name"]
            comp_id = competition["league_id"]
            comp_type = map_competition_type(comp_name)

            print(f"\n📥 {comp_name} ({comp_type})...")

            # Check sync state for incremental
            if not args.full and not args.force:
                sync_state = await get_sync_state(session, team_id, comp_id)
                if sync_state and sync_state.next_sync_at:
                    if datetime.utcnow() < sync_state.next_sync_at:
                        print(f"   ⏭️ Cache valid until {sync_state.next_sync_at}, skipping")
                        continue

            # Fetch matches from API
            try:
                matches = await get_matches_by_league(comp_id, client)
                api_calls += 1

                # Fallback to search for leagues with no matches
                if len(matches) == 0:
                    matches = await get_matches_by_search(
                        team_info["name"].replace("FC ", ""), comp_id, client
                    )
                    api_calls += 1

                print(f"   API returned {len(matches)} total matches")

            except Exception as e:
                print(f"   ❌ API error: {e}")
                continue

            # Filter: team matches + finished
            team_matches = []
            for m in matches:
                if not isinstance(m, dict):
                    continue
                home = m.get("home", {}) or {}
                away = m.get("away", {}) or {}
                try:
                    home_id = int(home.get("id")) if isinstance(home, dict) and home.get("id") else None
                    away_id = int(away.get("id")) if isinstance(away, dict) and away.get("id") else None
                except (ValueError, TypeError):
                    continue

                status = m.get("status", {})
                is_finished = status.get("finished", False) if isinstance(status, dict) else False

                if (home_id == team_id or away_id == team_id) and is_finished:
                    team_matches.append({
                        "event_id": m.get("id"),
                        "is_home": home_id == team_id,
                        "home_name": home.get("name"),
                        "away_name": away.get("name"),
                    })

            print(f"   {team_info['name']} finished matches: {len(team_matches)}")

            if not team_matches:
                continue

            # For incremental: get last synced match_id
            last_match_id = 0
            if not args.full:
                sync_state = await get_sync_state(session, team_id, comp_id)
                if sync_state:
                    last_match_id = sync_state.last_match_id or 0

            # Process each match
            new_matches_synced = 0
            max_match_id = last_match_id

            for match in team_matches:
                event_id = int(match["event_id"]) if match["event_id"] else 0

                # Incremental: skip already processed
                if not args.full and event_id <= last_match_id:
                    continue

                # Dedup: skip if already synced
                if not args.full and await is_match_synced(session, event_id, team_id):
                    continue

                is_home = match["is_home"]
                print(f"   [{event_id}] {match['home_name']} vs {match['away_name']}...", end=" ")

                if args.dry_run:
                    print("DRY RUN")
                    new_matches_synced += 1
                    max_match_id = max(max_match_id, event_id)
                    continue

                try:
                    lineup_data = await get_lineup(event_id, is_home, client)
                    api_calls += 1

                    lineup = lineup_data.get("response", {}).get("lineup", {})
                    if not lineup:
                        print("NO LINEUP")
                        continue

                    starters = lineup.get("starters", [])
                    subs = lineup.get("subs", [])
                    starter_ids = {p.get("id") for p in starters}
                    all_players = starters + subs

                    found_players = []
                    gk_playing = None
                    processed_players = set()  # Dedup: prevent counting same player twice

                    for player in all_players:
                        player_rapid_id = player.get("id")

                        # Dedup: skip if already processed this player in this match
                        if player_rapid_id in processed_players:
                            continue
                        processed_players.add(player_rapid_id)

                        # Filter by POLISH_PLAYERS
                        if player_rapid_id not in POLISH_PLAYERS:
                            continue

                        # Filter by specific players if --player or --gk-only option
                        if player_filter and player_rapid_id not in player_filter:
                            continue

                        is_starter = player_rapid_id in starter_ids
                        parsed = parse_player_performance(player, is_starter)

                        if not parsed or parsed["minutes"] == 0:
                            continue

                        # Get or create player in DB
                        result = await session.execute(
                            select(Player).where(Player.rapidapi_id == player_rapid_id)
                        )
                        player_db = result.scalar_one_or_none()

                        if not player_db:
                            player_db = Player(
                                rapidapi_id=player_rapid_id,
                                name=POLISH_PLAYERS[player_rapid_id]["name"],
                                position=POLISH_PLAYERS[player_rapid_id]["position"],
                                team=team_info["name"],
                                league="Multiple",
                            )
                            session.add(player_db)
                            await session.flush()
                        else:
                            # Update existing player info (position, team)
                            player_db.position = POLISH_PLAYERS[player_rapid_id]["position"]
                            player_db.team = team_info["name"]

                        # Update stats for this competition
                        stats = stats_by_competition[(comp_type, comp_name, comp_id)][player_db.id]
                        stats["minutes"] += parsed["minutes"]
                        stats["goals"] += parsed["goals"]
                        stats["assists"] += parsed["assists"]
                        stats["yellow_cards"] += parsed["yellow_cards"]
                        stats["red_cards"] += parsed["red_cards"]
                        stats["matches_total"] += 1
                        if parsed["started"]:
                            stats["matches_started"] += 1
                        else:
                            stats["matches_subbed"] += 1

                        rating = player.get("performance", {}).get("rating")
                        if rating:
                            stats["ratings"].append(rating)

                        # Check if GK (use position from POLISH_PLAYERS or API fallback)
                        is_gk = (
                            POLISH_PLAYERS.get(player_rapid_id, {}).get("position") == "GK" or
                            player.get("positionId") == 11 or
                            player.get("usualPlayingPositionId") == 0
                        )
                        if is_gk:
                            gk_playing = (player_db.id, player_rapid_id)

                        found_players.append(f"{POLISH_PLAYERS[player_rapid_id]['name']} ({parsed['minutes']}')")

                    # Fetch GK stats if needed
                    if gk_playing:
                        try:
                            match_score = await get_match_score(event_id, client)
                            match_stats = await get_match_all_stats(event_id, client)
                            api_calls += 2
                            gk_stats = extract_gk_match_stats(match_score, match_stats, is_home)
                            print(f"   GK stats: saves={gk_stats['saves']}, GA={gk_stats['goals_against']}, CS={gk_stats['clean_sheet']}")

                            stats = stats_by_competition[(comp_type, comp_name, comp_id)][gk_playing[0]]
                            stats["clean_sheets"] += 1 if gk_stats["clean_sheet"] else 0
                            stats["saves"] += gk_stats["saves"]
                            stats["goals_against"] += gk_stats["goals_against"]
                            stats["shots_on_target_against"] += gk_stats["shots_on_target_against"]
                        except Exception as e:
                            print(f"   GK error: {e}")
                            import traceback
                            traceback.print_exc()

                    # Mark match as synced
                    await mark_match_synced(session, event_id, team_id, comp_id)

                    if found_players:
                        print(f"FOUND: {', '.join(found_players)}")
                    else:
                        print("-")

                    new_matches_synced += 1
                    max_match_id = max(max_match_id, event_id)
                    matches_processed += 1

                    await asyncio.sleep(0.1)

                except Exception as e:
                    print(f"ERROR: {e}")

            # Update sync state
            if not args.dry_run and new_matches_synced > 0:
                await update_sync_state(
                    session, team_id, team_info["name"],
                    comp_id, comp_name, max_match_id, new_matches_synced
                )
                print(f"   ✅ Synced {new_matches_synced} new matches")

        # Save stats to database
        if args.dry_run:
            print(f"\n📊 DRY RUN - {new_matches_synced} matches would be checked for lineups")
            print(f"   Note: Actual synced matches depend on Polish players being in lineups")
            print(f"   API calls so far: {api_calls}")
            return new_matches_synced

        print(f"\n📊 Saving to database...")
        print(f"   API calls used: {api_calls}")

        # Save per-competition stats
        for (comp_type, comp_name, comp_id), player_stats in stats_by_competition.items():
            for player_db_id, stats in player_stats.items():
                if stats["matches_total"] == 0:
                    continue

                # Upsert to player_stats_by_competition
                result = await session.execute(
                    select(PlayerStatsByCompetition).where(
                        PlayerStatsByCompetition.player_id == player_db_id,
                        PlayerStatsByCompetition.season == CURRENT_SEASON,
                        PlayerStatsByCompetition.competition_type == comp_type,
                        PlayerStatsByCompetition.competition_name == comp_name,
                    )
                )
                comp_stats = result.scalar_one_or_none()

                if not comp_stats:
                    comp_stats = PlayerStatsByCompetition(
                        player_id=player_db_id,
                        season=CURRENT_SEASON,
                        competition_type=comp_type,
                        competition_name=comp_name,
                        competition_id=comp_id,
                    )
                    session.add(comp_stats)

                # Update values
                avg_rating = sum(stats["ratings"]) / len(stats["ratings"]) if stats["ratings"] else 0
                comp_stats.matches_total = stats["matches_total"]
                comp_stats.matches_started = stats["matches_started"]
                comp_stats.matches_subbed = stats["matches_subbed"]
                comp_stats.minutes_played = stats["minutes"]
                comp_stats.goals = stats["goals"]
                comp_stats.assists = stats["assists"]
                comp_stats.yellow_cards = stats["yellow_cards"]
                comp_stats.red_cards = stats["red_cards"]
                comp_stats.rating = round(avg_rating, 2)
                comp_stats.g_per90 = calculate_per_90(stats["goals"], stats["minutes"])
                comp_stats.a_per90 = calculate_per_90(stats["assists"], stats["minutes"])
                comp_stats.updated_at = datetime.utcnow()
                comp_stats.expires_at = datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)

                # GK stats
                is_gk = stats["shots_on_target_against"] > 0 or stats["saves"] > 0
                if is_gk:
                    comp_stats.clean_sheets = stats["clean_sheets"]
                    comp_stats.saves = stats["saves"]
                    comp_stats.goals_against = stats["goals_against"]
                    comp_stats.shots_on_target_against = stats["shots_on_target_against"]
                    if stats["shots_on_target_against"] > 0:
                        comp_stats.save_percentage = round(
                            stats["saves"] / stats["shots_on_target_against"] * 100, 1
                        )

        # Aggregate to Season Total (player_stats)
        await aggregate_to_season_total(session, player_filter)

        return matches_processed


async def aggregate_to_season_total(session, player_filter: list[int] | None = None):
    """Aggregate all competition stats to player_stats (Season Total).

    Args:
        player_filter: If set, only aggregate these specific players (list of rapidapi_id)
    """
    print(f"\n📊 Aggregating to Season Total...")

    # Build query based on filter
    if player_filter:
        # Only aggregate specific players
        result = await session.execute(
            select(Player).where(Player.rapidapi_id.in_(player_filter))
        )
        print(f"   Filtering to {len(player_filter)} player(s)")
    else:
        # Aggregate all players
        result = await session.execute(select(Player))

    players = result.scalars().all()

    for player in players:
        # Get all competition stats for this player
        result = await session.execute(
            select(PlayerStatsByCompetition).where(
                PlayerStatsByCompetition.player_id == player.id,
                PlayerStatsByCompetition.season == CURRENT_SEASON,
            )
        )
        comp_stats_list = result.scalars().all()

        # Create empty PlayerStats for new players without matches
        if not comp_stats_list:
            # Check if PlayerStats already exists
            result = await session.execute(
                select(PlayerStats).where(
                    PlayerStats.player_id == player.id,
                    PlayerStats.season == CURRENT_SEASON,
                )
            )
            db_stats = result.scalar_one_or_none()

            if not db_stats:
                # Create empty stats record for new player
                db_stats = PlayerStats(
                    player_id=player.id,
                    season=CURRENT_SEASON,
                    matches_total=0,
                    matches_started=0,
                    matches_subbed=0,
                    minutes_played=0,
                    goals=0,
                    assists=0,
                    yellow_cards=0,
                    red_cards=0,
                    rating=0.0,
                    g_per90=0.0,
                    a_per90=0.0,
                )
                session.add(db_stats)
                print(f"   {player.name}: Created empty stats (no matches yet)")
            continue

        # Aggregate
        total = {
            "matches_total": 0, "matches_started": 0, "matches_subbed": 0,
            "minutes_played": 0, "goals": 0, "assists": 0,
            "yellow_cards": 0, "red_cards": 0, "ratings": [],
            "clean_sheets": 0, "saves": 0, "goals_against": 0,
            "shots_on_target_against": 0,
        }

        for cs in comp_stats_list:
            total["matches_total"] += cs.matches_total
            total["matches_started"] += cs.matches_started
            total["matches_subbed"] += cs.matches_subbed
            total["minutes_played"] += cs.minutes_played
            total["goals"] += cs.goals
            total["assists"] += cs.assists
            total["yellow_cards"] += cs.yellow_cards
            total["red_cards"] += cs.red_cards
            if cs.rating:
                total["ratings"].append(cs.rating)
            if cs.clean_sheets:
                total["clean_sheets"] += cs.clean_sheets
            if cs.saves:
                total["saves"] += cs.saves
            if cs.goals_against:
                total["goals_against"] += cs.goals_against
            if cs.shots_on_target_against:
                total["shots_on_target_against"] += cs.shots_on_target_against

        # Get or create PlayerStats
        result = await session.execute(
            select(PlayerStats).where(
                PlayerStats.player_id == player.id,
                PlayerStats.season == CURRENT_SEASON,
            )
        )
        db_stats = result.scalar_one_or_none()

        if not db_stats:
            db_stats = PlayerStats(player_id=player.id, season=CURRENT_SEASON)
            session.add(db_stats)

        # Update Season Total
        avg_rating = sum(total["ratings"]) / len(total["ratings"]) if total["ratings"] else 0
        db_stats.matches_total = total["matches_total"]
        db_stats.matches_started = total["matches_started"]
        db_stats.matches_subbed = total["matches_subbed"]
        db_stats.minutes_played = total["minutes_played"]
        db_stats.goals = total["goals"]
        db_stats.assists = total["assists"]
        db_stats.yellow_cards = total["yellow_cards"]
        db_stats.red_cards = total["red_cards"]
        db_stats.rating = round(avg_rating, 2)
        db_stats.g_per90 = calculate_per_90(total["goals"], total["minutes_played"])
        db_stats.a_per90 = calculate_per_90(total["assists"], total["minutes_played"])
        db_stats.updated_at = datetime.utcnow()
        db_stats.expires_at = datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)

        # GK totals
        is_gk = total["saves"] > 0 or total["clean_sheets"] > 0
        if is_gk and total["shots_on_target_against"] > 0:
            db_stats.clean_sheets = total["clean_sheets"]
            db_stats.saves = total["saves"]
            db_stats.goals_against = total["goals_against"]
            db_stats.save_percentage = round(
                total["saves"] / total["shots_on_target_against"] * 100, 1
            )
            if total["matches_total"] > 0:
                db_stats.clean_sheets_percentage = round(
                    total["clean_sheets"] / total["matches_total"] * 100, 1
                )
            db_stats.goals_against_per90 = calculate_per_90(
                total["goals_against"], total["minutes_played"]
            )

        print(f"   {player.name}: {total['matches_total']} matches, {total['goals']}G, {total['assists']}A")


async def get_matches_by_league(league_id: int, client: httpx.AsyncClient) -> list:
    """Get all matches from a league."""
    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
    }

    response = await client.get(
        f"https://{API_HOST}/football-get-all-matches-by-league",
        headers=headers,
        params={"leagueid": league_id},
    )
    response.raise_for_status()
    data = response.json()

    # Parse nested structure: response.matches
    response_data = data.get("response", {})
    if isinstance(response_data, dict):
        matches = response_data.get("matches", [])
    else:
        matches = response_data if isinstance(response_data, list) else []

    return matches if isinstance(matches, list) else []


async def get_matches_by_search(team_name: str, league_id: int, client: httpx.AsyncClient) -> list:
    """Get matches from a league using search endpoint (for leagues like Supercopa)."""
    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
    }

    response = await client.get(
        f"https://{API_HOST}/football-matches-search",
        headers=headers,
        params={"search": team_name},
    )
    response.raise_for_status()
    data = response.json()

    # Parse search results
    suggestions = data.get("response", {}).get("suggestions", [])

    # Filter to only match type and specific league_id
    matches = []
    for s in suggestions:
        if s.get("type") == "match" and s.get("leagueId") == league_id:
            # Convert to same format as get_matches_by_league
            match_data = {
                "id": s.get("id"),
                "home": {
                    "id": s.get("homeTeamId"),
                    "name": s.get("homeTeamName"),
                },
                "away": {
                    "id": s.get("awayTeamId"),
                    "name": s.get("awayTeamName"),
                },
                "status": s.get("status", {}),
            }
            matches.append(match_data)

    return matches


async def get_lineup(event_id: int, is_home: bool, client: httpx.AsyncClient) -> dict:
    """Get lineup for a match."""
    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
    }

    endpoint = "football-get-hometeam-lineup" if is_home else "football-get-awayteam-lineup"

    response = await client.get(
        f"https://{API_HOST}/{endpoint}",
        headers=headers,
        params={"eventid": event_id},
    )
    response.raise_for_status()
    return response.json()


async def get_match_score(event_id: int, client: httpx.AsyncClient) -> dict:
    """Get match score for GK stats (goals conceded, clean sheets)."""
    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
    }

    response = await client.get(
        f"https://{API_HOST}/football-get-match-score",
        headers=headers,
        params={"eventid": event_id},
    )
    response.raise_for_status()
    return response.json()


async def get_match_all_stats(event_id: int, client: httpx.AsyncClient) -> dict:
    """Get all match stats for GK stats (shots on target, saves)."""
    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST,
    }

    response = await client.get(
        f"https://{API_HOST}/football-get-match-all-stats",
        headers=headers,
        params={"eventid": event_id},
    )
    response.raise_for_status()
    return response.json()


def extract_gk_match_stats(match_score_data: dict, match_stats_data: dict, is_home: bool) -> dict:
    """
    Extract goalkeeper stats from match data.

    Stats arrays are [home_value, away_value].

    Returns:
        {
            "goals_against": int,
            "saves": int,
            "shots_on_target_against": int,
            "clean_sheet": bool
        }
    """
    result = {
        "goals_against": 0,
        "saves": 0,
        "shots_on_target_against": 0,
        "clean_sheet": False,
    }

    try:
        # Get scores - extract goals conceded
        scores = match_score_data.get("response", {}).get("scores", [])
        if len(scores) >= 2:
            if is_home:
                result["goals_against"] = scores[1].get("score", 0) if len(scores) > 1 else 0
            else:
                result["goals_against"] = scores[0].get("score", 0)
            result["clean_sheet"] = result["goals_against"] == 0

        # Get match stats - shots on target and keeper saves
        all_stats = match_stats_data.get("response", {}).get("stats", [])

        for category in all_stats:
            for stat in category.get("stats", []):
                stats_values = stat.get("stats", [])
                if len(stats_values) < 2:
                    continue

                # ShotsOnTarget - shots faced by GK
                if stat.get("key") == "ShotsOnTarget":
                    result["shots_on_target_against"] = stats_values[1] if is_home else stats_values[0]

                # keeper_saves - saves made by GK
                if stat.get("key") == "keeper_saves":
                    result["saves"] = stats_values[0] if is_home else stats_values[1]

    except Exception as e:
        print(f"Error extracting GK stats: {e}")

    return result


def parse_player_performance(player: dict, is_starter: bool) -> dict:
    """
    Parse player performance from lineup data.

    Args:
        player: Player data dict
        is_starter: True if player is in starters list, False if in subs

    Returns: {minutes, goals, assists, started, yellow_cards, red_cards} or None if didn't play
    """
    performance = player.get("performance", {})

    result = {
        "minutes": 0,  # Default: didn't play
        "goals": 0,
        "assists": 0,
        "yellow_cards": 0,
        "red_cards": 0,
        "started": False,
    }

    # Check for substitution events first
    sub_events = performance.get("substitutionEvents", [])

    if is_starter:
        # Starter: default 90 minutes unless subbed out
        result["minutes"] = 90
        result["started"] = True

        for sub in sub_events:
            sub_type = sub.get("type", "").lower()
            sub_time = sub.get("time", 0)

            if sub_type == "subout":
                result["minutes"] = sub_time
    else:
        # Substitute: default 0 minutes unless subbed in
        result["minutes"] = 0
        result["started"] = False

        for sub in sub_events:
            sub_type = sub.get("type", "").lower()
            sub_time = sub.get("time", 0)

            if sub_type == "subin":
                result["minutes"] = 90 - sub_time

    # If still 0 minutes, player didn't play
    if result["minutes"] == 0:
        return None

    # Parse events (goals, assists, cards)
    events = performance.get("events", [])
    for event in events:
        event_type = event.get("type", "").lower()
        if event_type == "goal":
            result["goals"] += 1
        elif event_type == "assist":
            result["assists"] += 1
        elif event_type == "yellowcard":
            result["yellow_cards"] += 1
        elif event_type == "redcard":
            result["red_cards"] += 1

    return result


async def main():
    """Main sync function with CLI support."""
    args = parse_args()

    # Handle --gk-only option: filter to goalkeepers only
    if args.gk_only:
        player_filter = [pid for pid, info in POLISH_PLAYERS.items() if info.get("position") == "GK"]
        gk_names = [POLISH_PLAYERS[pid]["name"] for pid in player_filter]
        print("=" * 60)
        print(f"🔄 SYNC: Goalkeepers Only")
        print("=" * 60)
        print(f"API Host: {API_HOST}")
        print(f"Season: {CURRENT_SEASON}")
        print(f"Goalkeepers: {gk_names}")
        if args.dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
        if args.force:
            print("⚠️ Force mode - ignoring cache")
        print()
    # Handle --player option: find team and filter to single player
    elif args.player:
        if args.player not in POLISH_PLAYERS:
            print(f"❌ Player {args.player} not found in POLISH_PLAYERS")
            print(f"   Available: {list(POLISH_PLAYERS.keys())}")
            return
        if args.player not in PLAYER_TEAMS:
            print(f"❌ Player {args.player} not found in PLAYER_TEAMS mapping")
            print(f"   Add the player's team_id to PLAYER_TEAMS dict")
            return

        player_filter = [args.player]
        player_name = POLISH_PLAYERS[args.player]["name"]
        team_id = PLAYER_TEAMS[args.player]

        # Override args.team to sync only this player's team
        args.team = team_id
        args.full = True  # Force full sync for single player

        print("=" * 60)
        print(f"🔄 SYNC: Single Player ({player_name})")
        print("=" * 60)
        print(f"API Host: {API_HOST}")
        print(f"Season: {CURRENT_SEASON}")
        print(f"Player: {player_name} (id={args.player})")
        print(f"Team: {TEAMS[team_id]['name']} (id={team_id})")
        if args.force:
            print("⚠️ Force mode - ignoring cache")
        print()
    else:
        player_filter = None
        mode = "FULL" if args.full else "INCREMENTAL"
        print("=" * 60)
        print(f"🔄 SYNC: Polish Players ({mode})")
        print("=" * 60)
        print(f"API Host: {API_HOST}")
        print(f"Season: {CURRENT_SEASON}")
        print(f"Players: {[p['name'] for p in POLISH_PLAYERS.values()]}")
        if args.dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
        if args.force:
            print("⚠️ Force mode - ignoring cache")
        print()

    total_matches = 0

    async with AsyncSessionLocal() as session:
        teams_to_sync = {args.team: TEAMS[args.team]} if args.team and args.team in TEAMS else TEAMS

        for team_id, team_info in teams_to_sync.items():
            try:
                matches = await sync_team_v2(team_id, team_info, session, args, player_filter)
                total_matches += matches
            except Exception as e:
                print(f"❌ Error syncing {team_info['name']}: {e}")
                import traceback
                traceback.print_exc()

        if not args.dry_run:
            await session.commit()

    print("\n" + "=" * 60)
    if args.dry_run:
        print(f"🔍 DRY RUN COMPLETE: {total_matches} matches would be checked for lineups")
        print("   Run without --dry-run to see actual sync results")
    else:
        print(f"✅ SYNC COMPLETE: {total_matches} matches processed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
