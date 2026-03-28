"""Heatmap API endpoints."""

from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import Player, PlayerHeatmapPosition
from app.schemas.heatmap import (
    HeatmapPositionOut,
    PlayerSeasonHeatmapOut,
    AvgPosition,
)

import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.get("/{player_id}/heatmap", response_model=PlayerSeasonHeatmapOut)
async def get_player_heatmap(
    player_id: int,
    season: str = Query("2025/26", description="Season filter"),
    competition_type: Optional[str] = Query(
        None, description="Filter by competition type (league, european, domestic)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated heatmap data for a player across a season.

    Returns all position data from matches, plus average position weighted by minutes.
    """
    # Verify player exists
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Skip goalkeepers (not useful for heatmaps)
    if player.position == "GK":
        return PlayerSeasonHeatmapOut(
            player_id=player_id,
            player_name=player.name,
            player_position=player.position,
            player_team=player.team,
            season=season,
            total_matches=0,
            positions=[],
            avg_position=None,
        )

    # Build query for heatmap positions
    query = select(PlayerHeatmapPosition).where(
        PlayerHeatmapPosition.player_id == player_id,
        PlayerHeatmapPosition.season == season,
    )

    if competition_type:
        query = query.where(PlayerHeatmapPosition.competition_type == competition_type)

    query = query.order_by(PlayerHeatmapPosition.created_at.desc())

    result = await db.execute(query)
    positions = result.scalars().all()

    if not positions:
        return PlayerSeasonHeatmapOut(
            player_id=player_id,
            player_name=player.name,
            player_position=player.position,
            player_team=player.team,
            season=season,
            total_matches=0,
            positions=[],
            avg_position=None,
        )

    # Calculate weighted average position (by minutes played)
    total_minutes = sum(p.minutes_played for p in positions)
    if total_minutes > 0:
        avg_x = sum(float(p.pos_x) * p.minutes_played for p in positions) / total_minutes
        avg_y = sum(float(p.pos_y) * p.minutes_played for p in positions) / total_minutes
        avg_position = AvgPosition(x=round(avg_x, 4), y=round(avg_y, 4))
    else:
        avg_position = None

    # Convert to response schema
    position_outs = [
        HeatmapPositionOut(
            match_id=p.match_id,
            competition_name=p.competition_name,
            competition_type=p.competition_type,
            formation=p.formation,
            pos_x=float(p.pos_x),
            pos_y=float(p.pos_y),
            zone_width=float(p.zone_width),
            zone_height=float(p.zone_height),
            minutes_played=p.minutes_played,
            is_starter=p.is_starter,
        )
        for p in positions
    ]

    return PlayerSeasonHeatmapOut(
        player_id=player_id,
        player_name=player.name,
        player_position=player.position,
        player_team=player.team,
        season=season,
        total_matches=len(positions),
        positions=position_outs,
        avg_position=avg_position,
    )
