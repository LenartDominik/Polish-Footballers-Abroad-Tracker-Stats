"""Player schemas for API request/response."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PlayerBase(BaseModel):
    """Base player schema."""

    name: str
    position: Optional[str] = None
    team: Optional[str] = None
    league: Optional[str] = None


class PlayerOut(PlayerBase):
    """Player response schema."""

    id: int
    rapidapi_id: Optional[int] = None
    nationality: str = "Poland"

    model_config = {"from_attributes": True}


class PlayerSearchOut(PlayerBase):
    """Player search result schema (lighter response)."""

    id: int
    position: Optional[str] = None

    model_config = {"from_attributes": True}


class PlayerStatsBase(BaseModel):
    """Base player statistics schema."""

    season: str

    # Match stats
    matches_total: int = 0
    matches_started: int = 0
    matches_subbed: int = 0
    minutes_played: int = 0

    # Attacking stats
    goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0

    # Rating
    rating: float = Field(default=0.0, ge=0, le=10)


class PlayerStatsOut(PlayerStatsBase):
    """Player statistics response schema - position-specific fields excluded when None."""

    id: int
    player_id: int
    player_name: Optional[str] = None
    player_position: Optional[str] = None
    player_team: Optional[str] = None
    updated_at: Optional[datetime] = None

    # Field player stats (NOT for GK) - None when not applicable
    penalties_scored: Optional[int] = None
    penalties_missed: Optional[int] = None
    g_per90: Optional[float] = None
    a_per90: Optional[float] = None

    # Goalkeeper stats (only for GK) - None when not applicable
    clean_sheets: Optional[int] = None
    clean_sheets_percentage: Optional[float] = None
    saves: Optional[int] = None
    save_percentage: Optional[float] = None
    goals_against: Optional[int] = None
    goals_against_per90: Optional[float] = None
    penalties_saved: Optional[int] = None
    penalties_conceded: Optional[int] = None

    model_config = {"from_attributes": True}


class PlayerStatsCreate(PlayerStatsBase):
    """Schema for creating player statistics."""

    player_id: int
