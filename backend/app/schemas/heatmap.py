"""Heatmap schemas for API request/response."""

from typing import List, Optional

from pydantic import BaseModel


class HeatmapPositionOut(BaseModel):
    """Single heatmap position data per match."""

    match_id: int
    competition_name: Optional[str] = None
    competition_type: Optional[str] = None  # league, european, domestic
    formation: Optional[str] = None
    pos_x: float
    pos_y: float
    zone_width: float
    zone_height: float
    minutes_played: int = 0
    is_starter: bool = False

    model_config = {"from_attributes": True}


class AvgPosition(BaseModel):
    """Average position across matches."""

    x: float
    y: float


class PlayerSeasonHeatmapOut(BaseModel):
    """Aggregated heatmap data for a player across a season."""

    player_id: int
    player_name: str
    player_position: Optional[str] = None
    player_team: Optional[str] = None
    season: str
    total_matches: int
    positions: List[HeatmapPositionOut]
    avg_position: Optional[AvgPosition] = None

    model_config = {"from_attributes": True}
