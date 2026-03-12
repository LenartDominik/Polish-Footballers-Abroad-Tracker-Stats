"""Sync Polish players from API to Supabase database."""

import asyncio
from datetime import datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import Player, PlayerStats
from app.services.rapidapi import rapidapi_client, calculate_per_90

# Team IDs to sync (expand this list later)
TEAMS = {
    8634: {"name": "FC Barcelona", "league": "La Liga"},
    # Add more teams here:
    # 123: {"name": "Bayern Munich", "league": "Bundesliga"},
    # 456: {"name": "Arsenal", "league": "Premier League"},
}

CURRENT_SEASON = "2025/26"
CACHE_TTL_HOURS = 24


async def sync_team(team_id: int, team_info: dict, session: AsyncSession):
    """Sync Polish players from a single team."""
    print(f"\n📥 Fetching players from {team_info['name']} (ID: {team_id})...")

    try:
        # Get Polish players from API
        polish_players = await rapidapi_client.get_polish_players_from_team(team_id)

        if not polish_players:
            print(f"   ⚠️  No Polish players found")
            return 0

        synced = 0
        for player_data in polish_players:
            # Check if player exists
            result = await session.execute(
                select(Player).where(Player.rapidapi_id == player_data["id"])
            )
            player = result.scalar_one_or_none()

            if not player:
                # Create new player
                player = Player(
                    rapidapi_id=player_data["id"],
                    name=player_data["name"],
                    position=player_data.get("positionIdsDesc", "").split(",")[0],
                    team=team_info["name"],
                    league=team_info["league"],
                    nationality=player_data.get("cname", "Poland"),
                )
                session.add(player)
                await session.flush()
                print(f"   ✅ NEW: {player.name} ({player.position})")
            else:
                # Update existing player
                player.name = player_data["name"]
                player.position = player_data.get("positionIdsDesc", "").split(",")[0]
                player.team = team_info["name"]
                player.league = team_info["league"]
                player.updated_at = datetime.utcnow()
                print(f"   🔄 UPDATE: {player.name}")

            # Check for existing stats
            result = await session.execute(
                select(PlayerStats).where(
                    PlayerStats.player_id == player.id,
                    PlayerStats.season == CURRENT_SEASON,
                )
            )
            stats = result.scalar_one_or_none()

            # Calculate per-90 stats (we don't have minutes yet, so use placeholder)
            # TODO: Get minutes from lineup endpoints
            minutes_played = 900  # Placeholder - need to fetch from lineup data
            goals = player_data.get("goals", 0)
            assists = player_data.get("assists", 0)

            if not stats:
                stats = PlayerStats(
                    player_id=player.id,
                    season=CURRENT_SEASON,
                    goals=goals,
                    assists=assists,
                    yellow_cards=player_data.get("ycards", 0),
                    red_cards=player_data.get("rcards", 0),
                    penalties_scored=player_data.get("penalties", 0),
                    rating=player_data.get("rating") or 0,
                    minutes_played=minutes_played,
                    g_per90=calculate_per_90(goals, minutes_played),
                    a_per90=calculate_per_90(assists, minutes_played),
                    expires_at=datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS),
                )
                session.add(stats)
            else:
                stats.goals = goals
                stats.assists = assists
                stats.yellow_cards = player_data.get("ycards", 0)
                stats.red_cards = player_data.get("rcards", 0)
                stats.penalties_scored = player_data.get("penalties", 0)
                stats.rating = player_data.get("rating") or 0
                stats.minutes_played = minutes_played
                stats.g_per90 = calculate_per_90(goals, minutes_played)
                stats.a_per90 = calculate_per_90(assists, minutes_played)
                stats.updated_at = datetime.utcnow()
                stats.expires_at = datetime.utcnow() + timedelta(hours=CACHE_TTL_HOURS)

            synced += 1

        return synced

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return 0


async def main():
    """Main sync function."""
    print("=" * 60)
    print("🔄 SYNC: Polish Players to Supabase")
    print("=" * 60)
    print(f"Season: {CURRENT_SEASON}")
    print(f"Teams to sync: {len(TEAMS)}")

    total_synced = 0

    async with AsyncSessionLocal() as session:
        for team_id, team_info in TEAMS.items():
            synced = await sync_team(team_id, team_info, session)
            total_synced += synced

        await session.commit()

    print("\n" + "=" * 60)
    print(f"✅ SYNC COMPLETE: {total_synced} players")
    print("=" * 60)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
