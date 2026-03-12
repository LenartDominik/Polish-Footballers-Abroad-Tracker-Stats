# -*- coding: utf-8 -*-
"""Full sync: Polish players with minutes from lineups."""

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
import httpx

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Player, PlayerStats
from app.services.rapidapi import calculate_per_90

load_dotenv()

# Configuration
API_HOST = "free-api-live-football-data.p.rapidapi.com"
API_KEY = settings.rapidapi_key

# Polish player IDs to track (with correct Polish characters)
POLISH_PLAYERS = {
    93447: "Robert Lewandowski",
    169718: "Wojciech Szczęsny",
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
}

CURRENT_SEASON = "2025/26"
CACHE_TTL_HOURS = 24


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


async def sync_team(team_id: int, team_info: dict, session):
    """Sync Polish players from a team with full match data from all competitions."""
    print(f"\n{'='*60}")
    print(f"SYNC: {team_info['name']} - ALL COMPETITIONS")
    print(f"{'='*60}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Collect matches from all competitions
        all_team_matches = []

        for competition in team_info.get("competitions", []):
            league_name = competition["name"]
            league_id = competition["league_id"]

            print(f"📥 Fetching matches from {league_name}...")
            try:
                # First try standard endpoint
                matches = await get_matches_by_league(league_id, client)
                print(f"   Total matches: {len(matches)}")

                # If no matches from standard endpoint, try search (for Supercopa etc.)
                if len(matches) == 0:
                    print(f"   Trying search endpoint for {league_name}...")
                    matches = await get_matches_by_search(team_info["name"].replace("FC ", ""), league_id, client)
                    print(f"   Found via search: {len(matches)} matches")

                # Filter team matches (finished only)
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

                    # Only include finished matches
                    status = m.get("status", {})
                    is_finished = status.get("finished", False) if isinstance(status, dict) else False

                    if (home_id == team_id or away_id == team_id) and is_finished:
                        all_team_matches.append({
                            "event_id": m.get("id"),
                            "is_home": home_id == team_id,
                            "home_name": home.get("name"),
                            "away_name": away.get("name"),
                            "competition": league_name,
                        })

                print(f"   {team_info['name']} matches in {league_name}: {len([m for m in all_team_matches if m['competition'] == league_name])}")

            except Exception as e:
                print(f"   ❌ Error fetching {league_name}: {e}")

        print(f"\n📊 Total matches across all competitions: {len(all_team_matches)}")

        # Aggregate player stats from all matches
        player_stats = defaultdict(lambda: {
            "minutes": 0,
            "goals": 0,
            "assists": 0,
            "yellow_cards": 0,
            "red_cards": 0,
            "matches_total": 0,
            "matches_started": 0,
            "matches_subbed": 0,
            "ratings": [],
            # Goalkeeper stats
            "clean_sheets": 0,
            "saves": 0,
            "goals_against": 0,
            "shots_on_target_against": 0,
        })

        # Process each match
        for i, match in enumerate(all_team_matches):
            event_id = match["event_id"]
            is_home = match["is_home"]
            competition = match.get("competition", "Unknown")

            print(f"   [{i+1}/{len(all_team_matches)}] [{competition}] {match['home_name']} vs {match['away_name']}...", end=" ")

            try:
                lineup_data = await get_lineup(event_id, is_home, client)

                # Navigate to lineup
                lineup = lineup_data.get("response", {}).get("lineup", {})
                if not lineup:
                    print("NO LINEUP")
                    continue

                # Get starters and subs
                starters = lineup.get("starters", [])
                subs = lineup.get("subs", [])
                starter_ids = {p.get("id") for p in starters}
                all_players = starters + subs

                found_players = []
                gk_playing_in_match = None  # Track GK for match stats fetch

                for player in all_players:
                    player_id = player.get("id")
                    if player_id in POLISH_PLAYERS:
                        is_starter = player_id in starter_ids
                        parsed = parse_player_performance(player, is_starter)
                        if parsed and parsed["minutes"] > 0:
                            stats = player_stats[player_id]
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

                            # Check if player is GK (positionId 11 or usualPlayingPositionId 0)
                            is_gk = (
                                player.get("positionId") == 11 or
                                player.get("usualPlayingPositionId") == 0 or
                                player_id == 169718  # Szczęsny ID
                            )

                            if is_gk:
                                gk_playing_in_match = player_id

                            found_players.append(f"{POLISH_PLAYERS[player_id]} ({parsed['minutes']}')")

                # Fetch GK match stats if goalkeeper played
                if gk_playing_in_match:
                    try:
                        match_score_data = await get_match_score(event_id, client)
                        match_stats_data = await get_match_all_stats(event_id, client)
                        gk_match_stats = extract_gk_match_stats(match_score_data, match_stats_data, is_home)

                        stats = player_stats[gk_playing_in_match]
                        stats["clean_sheets"] += 1 if gk_match_stats["clean_sheet"] else 0
                        stats["saves"] += gk_match_stats["saves"]
                        stats["goals_against"] += gk_match_stats["goals_against"]
                        stats["shots_on_target_against"] += gk_match_stats["shots_on_target_against"]
                    except Exception as e:
                        print(f"GK stats error: {e}")

                if found_players:
                    print(f"FOUND: {', '.join(found_players)}")
                else:
                    print("-")

                # Small delay to not hammer API
                await asyncio.sleep(0.1)

            except Exception as e:
                print(f"ERROR: {e}")

        # Update database
        print(f"\n📊 Updating database...")

        for player_id, stats in player_stats.items():
            if stats["matches_total"] == 0:
                print(f"   ⚠️ {POLISH_PLAYERS[player_id]}: No matches found")
                continue

            # Get or create player
            result = await session.execute(
                select(Player).where(Player.rapidapi_id == player_id)
            )
            player = result.scalar_one_or_none()

            if not player:
                player = Player(
                    rapidapi_id=player_id,
                    name=POLISH_PLAYERS[player_id],
                    position="ST" if player_id == 93447 else "GK",
                    team=team_info["name"],
                    league="Multiple",  # Player stats aggregated from multiple competitions
                )
                session.add(player)
                await session.flush()
                print(f"   ✅ NEW: {player.name}")
            else:
                player.name = POLISH_PLAYERS[player_id]  # Update with correct Polish name
                player.team = team_info["name"]
                player.league = "Multiple"
                print(f"   🔄 UPDATE: {player.name}")

            # Get or create stats
            result = await session.execute(
                select(PlayerStats).where(
                    PlayerStats.player_id == player.id,
                    PlayerStats.season == CURRENT_SEASON,
                )
            )
            db_stats = result.scalar_one_or_none()

            if not db_stats:
                db_stats = PlayerStats(
                    player_id=player.id,
                    season=CURRENT_SEASON,
                )
                session.add(db_stats)

            # Calculate average rating
            avg_rating = sum(stats["ratings"]) / len(stats["ratings"]) if stats["ratings"] else 0

            # Update stats
            db_stats.matches_total = stats["matches_total"]
            db_stats.matches_started = stats["matches_started"]
            db_stats.matches_subbed = stats["matches_subbed"]
            db_stats.minutes_played = stats["minutes"]
            db_stats.goals = stats["goals"]
            db_stats.assists = stats["assists"]
            db_stats.yellow_cards = stats["yellow_cards"]
            db_stats.red_cards = stats["red_cards"]
            db_stats.rating = round(avg_rating, 2)
            db_stats.g_per90 = calculate_per_90(stats["goals"], stats["minutes"])
            db_stats.a_per90 = calculate_per_90(stats["assists"], stats["minutes"])
            db_stats.updated_at = datetime.utcnow()
            db_stats.expires_at = datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)

            # Goalkeeper stats
            is_gk = player_id == 169718  # Szczęsny
            if is_gk and stats["shots_on_target_against"] > 0:
                db_stats.clean_sheets = stats["clean_sheets"]
                db_stats.saves = stats["saves"]
                db_stats.goals_against = stats["goals_against"]
                # Calculate percentages
                db_stats.save_percentage = round(stats["saves"] / stats["shots_on_target_against"] * 100, 1)
                db_stats.goals_against_per90 = calculate_per_90(stats["goals_against"], stats["minutes"])
                # Clean sheets percentage
                if stats["matches_total"] > 0:
                    db_stats.clean_sheets_percentage = round(stats["clean_sheets"] / stats["matches_total"] * 100, 1)

            print(f"      {stats['matches_total']} matches ({stats['matches_started']} started, {stats['matches_subbed']} sub)")
            print(f"      {stats['minutes']} min, {stats['goals']}G, {stats['assists']}A, {stats['yellow_cards']}YC, {stats['red_cards']}RC")
            print(f"      G/90: {db_stats.g_per90:.2f}, A/90: {db_stats.a_per90:.2f}, Rating: {db_stats.rating:.2f}")
            if is_gk and stats["shots_on_target_against"] > 0:
                print(f"      GK: CS={stats['clean_sheets']} ({db_stats.clean_sheets_percentage}%), saves={stats['saves']}, save%={db_stats.save_percentage}%, GA={stats['goals_against']}, GA/90={db_stats.goals_against_per90:.2f}")

        return len([s for s in player_stats.values() if s["matches_total"] > 0])


async def main():
    """Main sync function."""
    print("=" * 60)
    print("🔄 FULL SYNC: Polish Players with Lineup Data")
    print("=" * 60)
    print(f"API Host: {API_HOST}")
    print(f"Season: {CURRENT_SEASON}")
    print(f"Players: {list(POLISH_PLAYERS.values())}")

    total = 0

    async with AsyncSessionLocal() as session:
        for team_id, team_info in TEAMS.items():
            try:
                synced = await sync_team(team_id, team_info, session)
                total += synced
            except Exception as e:
                print(f"❌ Error syncing {team_info['name']}: {e}")
                import traceback
                traceback.print_exc()

        await session.commit()

    print("\n" + "=" * 60)
    print(f"✅ SYNC COMPLETE: {total} players updated")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
