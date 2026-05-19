"""Pydantic schemas for live match API responses."""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class LiveEventOut(BaseModel):
    """A single live match event (goal, assist, card, substitution)."""

    id: int
    match_id: int
    player_name: str
    event_type: str  # 'goal', 'assist', 'yellow_card', 'red_card', 'subin', 'subout'
    minute: Optional[int] = None
    match_score: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LiveMatchOut(BaseModel):
    """Live match with current score and events."""

    match_id: int
    home_team: str
    away_team: str
    home_score: int = 0
    away_score: int = 0
    status: str = "unknown"  # 'prematch', 'live', 'ht', 'ft', etc.
    minute: Optional[str] = None
    competition: Optional[str] = None
    player_name: Optional[str] = None
    lineup_status: Optional[str] = None  # 'starting', 'bench', 'absent'
    kickoff_time: Optional[str] = None  # ISO datetime, e.g. "2026-05-04T21:00:00Z"
    events: List[LiveEventOut] = []


class LiveStatusOut(BaseModel):
    """Whether any live match with tracked players is active."""

    is_live: bool
    matches_count: int = 0
    is_prematch: bool = False
    prematch_count: int = 0


class UpcomingMatchOut(BaseModel):
    """Upcoming match with a tracked Polish player."""

    match_id: int
    home_team: str
    away_team: str
    kickoff_time: str  # ISO datetime
    competition: Optional[str] = None
    stage: Optional[str] = None
    player_name: str
    player_team: str
