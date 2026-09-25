"""Schemas for match-log and form endpoints (media-first MVP)."""

from datetime import date

from pydantic import BaseModel, Field


class MatchLogOut(BaseModel):
    """One player appearance (row from player_match_logs)."""

    match_id: int
    match_date: date
    competition_name: str
    competition_type: str  # league / european / domestic
    opponent: str
    is_home: bool
    score: str | None = None  # "2:1"
    minutes: int = 0
    goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    appearance: str  # start / sub / bench
    rating: float | None = None

    model_config = {"from_attributes": True}


class PlayerFormOut(BaseModel):
    """Form of one player over the last N matches."""

    player_id: int
    player_name: str
    player_position: str | None = None
    season: str
    matches: int  # requested window size
    score: float | None = Field(None, ge=0, le=100)
    matches_count: int = 0  # matches actually in the window
    goals: int = 0
    assists: int = 0
    minutes: int = 0
    avg_rating: float | None = None
    clean_sheets: int | None = None  # GK only
    message: str | None = None  # set when no match data for the season


class FormRankingEntryOut(BaseModel):
    """One row of the form ranking."""

    rank: int
    player_id: int
    player_name: str
    position: str | None = None
    team: str | None = None
    score: float = Field(ge=0, le=100)
    matches_count: int
    goals: int = 0
    assists: int = 0
    minutes: int = 0
    avg_rating: float | None = None
    clean_sheets: int | None = None  # GK only
