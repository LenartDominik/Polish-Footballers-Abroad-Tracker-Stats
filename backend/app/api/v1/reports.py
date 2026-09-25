"""Weekly reports API endpoints (media-first MVP).

Workflow: POST /generate builds a draft from match logs (upsert per period),
PATCH saves the editorial comment / publishes, public GETs serve content.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import verify_admin_key
from app.core.config import settings
from app.db.models import Player, PlayerMatchLog, WeeklyReport
from app.db.session import get_db
from app.schemas.report import (
    ReportDetailOut,
    ReportGenerateOut,
    ReportMatchOut,
    ReportOut,
    ReportSummary,
    ReportUpdateIn,
)

router = APIRouter()


async def _get_period_logs(
    db: AsyncSession, start: date, end: date
) -> list[tuple[PlayerMatchLog, Player]]:
    """Match logs in [start, end] joined with players, oldest first."""
    result = await db.execute(
        select(PlayerMatchLog, Player)
        .join(Player, PlayerMatchLog.player_id == Player.id)
        .where(
            PlayerMatchLog.match_date >= start,
            PlayerMatchLog.match_date <= end,
        )
        .order_by(PlayerMatchLog.match_date.asc(), PlayerMatchLog.id.asc())
    )
    return result.all()


@router.post("/generate", response_model=ReportGenerateOut)
async def generate_report(
    start: date = Query(..., description="Period start (ISO date)"),
    end: date = Query(..., description="Period end (ISO date)"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_key),
):
    """Generate (or regenerate) a draft report from match logs.

    Upsert on UNIQUE(period_start, period_end): an existing report keeps its
    id, status and editorial comment — only title/generated_at are refreshed.
    """
    if start > end:
        raise HTTPException(status_code=422, detail="start must be before or equal to end")

    rows = await _get_period_logs(db, start, end)
    if not rows:
        raise HTTPException(status_code=400, detail=f"No match data in period {start} - {end}")

    summary = ReportSummary(
        matches_count=len(rows),
        players_count=len({log.player_id for log, _ in rows}),
        goals=sum(log.goals or 0 for log, _ in rows),
        assists=sum(log.assists or 0 for log, _ in rows),
    )

    # Upsert: find existing report for the period, else insert a new draft
    result = await db.execute(
        select(WeeklyReport).where(
            WeeklyReport.period_start == start,
            WeeklyReport.period_end == end,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        report = WeeklyReport(
            season=settings.current_season,
            period_start=start,
            period_end=end,
            status="draft",
        )
        db.add(report)

    report.title = f"Raport tygodnia {start} - {end}"
    report.generated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(report)

    return ReportGenerateOut.model_validate(
        {**ReportOut.model_validate(report).model_dump(), "summary": summary}
    )


@router.patch("/{report_id}", response_model=ReportOut)
async def update_report(
    report_id: int,
    payload: ReportUpdateIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_admin_key),
):
    """Save the editorial comment and/or publish the report."""
    result = await db.execute(select(WeeklyReport).where(WeeklyReport.id == report_id))
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    if payload.editorial_comment is not None:
        report.editorial_comment = payload.editorial_comment
    if payload.publish and report.status != "published":
        report.status = "published"
        report.published_at = datetime.utcnow()

    await db.commit()
    await db.refresh(report)
    return report


@router.get("/latest", response_model=ReportDetailOut)
async def get_latest_report(db: AsyncSession = Depends(get_db)):
    """Newest published report with its matches (public report content)."""
    result = await db.execute(
        select(WeeklyReport)
        .where(WeeklyReport.status == "published")
        .order_by(WeeklyReport.period_end.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="No published report yet")

    rows = await _get_period_logs(db, report.period_start, report.period_end)
    matches = [
        ReportMatchOut(
            player_id=log.player_id,
            player_name=player.name,
            match_id=log.match_id,
            match_date=log.match_date,
            competition_name=log.competition_name,
            competition_type=log.competition_type,
            opponent=log.opponent,
            is_home=log.is_home,
            score=log.score,
            minutes=log.minutes,
            goals=log.goals,
            assists=log.assists,
            yellow_cards=log.yellow_cards,
            red_cards=log.red_cards,
            appearance=log.appearance,
            rating=float(log.rating) if log.rating is not None else None,
        )
        for log, player in rows
    ]

    return ReportDetailOut(
        **ReportOut.model_validate(report).model_dump(),
        matches=matches,
    )


@router.get("/archive", response_model=list[ReportOut])
async def get_report_archive(
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """Published reports, oldest first (archive / SEO)."""
    result = await db.execute(
        select(WeeklyReport)
        .where(WeeklyReport.status == "published")
        .order_by(WeeklyReport.period_start.asc())
        .limit(limit)
    )
    return result.scalars().all()
