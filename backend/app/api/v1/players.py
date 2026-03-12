"""Players API endpoints."""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.db.models import Player, PlayerStats
from app.schemas.player import PlayerOut, PlayerStatsOut, PlayerSearchOut
import structlog

router = APIRouter()
logger = structlog.get_logger()


@router.get("/", response_model=List[PlayerOut])
async def list_players(
    league: Optional[str] = Query(None, description="Filter by league"),
    team: Optional[str] = Query(None, description="Filter by team"),
    limit: int = Query(50, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """List all Polish players with optional filters."""
    query = select(Player)

    if league:
        query = query.where(Player.league.ilike(f"%{league}%"))
    if team:
        query = query.where(Player.team.ilike(f"%{team}%"))

    query = query.order_by(Player.name).limit(limit)

    result = await db.execute(query)
    players = result.scalars().all()

    return players


@router.get("/search", response_model=List[PlayerSearchOut])
async def search_players(
    name: Optional[str] = Query(None, min_length=2, description="Player name search"),
    team: Optional[str] = Query(None, description="Filter by team"),
    league: Optional[str] = Query(None, description="Filter by league"),
    limit: int = Query(20, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for Polish players abroad.

    All filters are independent (OR logic between them).
    At least one filter must be provided.
    """
    if not any([name, team, league]):
        raise HTTPException(
            status_code=400,
            detail="At least one filter (name, team, or league) is required",
        )

    # Build query with OR conditions
    conditions = []
    if name:
        conditions.append(Player.name.ilike(f"%{name}%"))
    if team:
        conditions.append(Player.team.ilike(f"%{team}%"))
    if league:
        conditions.append(Player.league.ilike(f"%{league}%"))

    query = select(Player).where(or_(*conditions)).limit(limit)
    result = await db.execute(query)
    players = result.scalars().all()

    return players


@router.get("/{player_id}", response_model=PlayerOut)
async def get_player(
    player_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get player basic info by ID."""
    result = await db.execute(
        select(Player).where(Player.id == player_id)
    )
    player = result.scalar_one_or_none()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    return player


@router.get("/{player_id}/stats", response_model=PlayerStatsOut, response_model_exclude_none=True)
async def get_player_stats(
    player_id: int,
    season: Optional[str] = Query(None, description="Season filter (default: current)"),
    db: AsyncSession = Depends(get_db),
):
    """Get player statistics for a season."""
    if not season:
        season = "2025/26"  # Default current season

    # Get player first
    result = await db.execute(
        select(Player).where(Player.id == player_id)
    )
    player = result.scalar_one_or_none()

    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Get stats from DB
    result = await db.execute(
        select(PlayerStats).where(
            PlayerStats.player_id == player_id,
            PlayerStats.season == season,
        )
    )
    stats = result.scalar_one_or_none()

    if not stats:
        raise HTTPException(
            status_code=404,
            detail=f"Player stats not found for season {season}",
        )

    # Goalkeeper stats only for GK position
    is_goalkeeper = player.position == "GK"

    result = {
        "id": stats.id,
        "player_id": stats.player_id,
        "season": stats.season,
        "matches_total": stats.matches_total,
        "matches_started": stats.matches_started,
        "matches_subbed": stats.matches_subbed,
        "minutes_played": stats.minutes_played,
        "goals": stats.goals,
        "assists": stats.assists,
        "yellow_cards": stats.yellow_cards,
        "red_cards": stats.red_cards,
        "rating": float(stats.rating) if stats.rating else 0.0,
        "player_name": player.name,
        "player_position": player.position,
        "player_team": player.team,
        "updated_at": stats.updated_at,
        # Field player stats (None for GK)
        "penalties_scored": None if is_goalkeeper else stats.penalties_scored,
        "penalties_missed": None if is_goalkeeper else stats.penalties_missed,
        "g_per90": None if is_goalkeeper else (float(stats.g_per90) if stats.g_per90 else 0.0),
        "a_per90": None if is_goalkeeper else (float(stats.a_per90) if stats.a_per90 else 0.0),
        # Goalkeeper stats (None for field players)
        "clean_sheets": stats.clean_sheets if is_goalkeeper else None,
        "clean_sheets_percentage": float(stats.clean_sheets_percentage) if (is_goalkeeper and stats.clean_sheets_percentage is not None) else None,
        "saves": stats.saves if is_goalkeeper else None,
        "save_percentage": float(stats.save_percentage) if (is_goalkeeper and stats.save_percentage is not None) else None,
        "goals_against": stats.goals_against if is_goalkeeper else None,
        "goals_against_per90": float(stats.goals_against_per90) if (is_goalkeeper and stats.goals_against_per90 is not None) else None,
        "penalties_saved": stats.penalties_saved if is_goalkeeper else None,
        "penalties_conceded": stats.penalties_conceded if is_goalkeeper else None,
    }

    return result
