"""Schemas for weekly report endpoints (media-first MVP)."""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.match import MatchLogOut


class ReportOut(BaseModel):
    """Weekly report row."""

    id: int
    season: str
    period_start: date
    period_end: date
    title: str
    editorial_comment: str | None = None
    status: str  # draft / published
    generated_at: datetime | None = None
    published_at: datetime | None = None

    model_config = {"from_attributes": True}


class ReportSummary(BaseModel):
    """Aggregated match data of the period (generate response)."""

    matches_count: int
    players_count: int
    goals: int
    assists: int


class ReportGenerateOut(ReportOut):
    summary: ReportSummary


class ReportMatchOut(MatchLogOut):
    """Match log enriched with the player's name (public report view)."""

    player_id: int
    player_name: str


class ReportDetailOut(ReportOut):
    """Published report with its matches (report content for the frontend)."""

    matches: list[ReportMatchOut] = []


class ReportUpdateIn(BaseModel):
    """PATCH body: editorial comment and/or publish."""

    editorial_comment: str | None = Field(default=None, max_length=10000)
    publish: bool = False
