"""Rankings API endpoints (media-first MVP)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.players import _validate_form_matches
from app.core.config import settings
from app.db.models import Player, PlayerMatchLog
from app.db.session import get_db
from app.schemas.match import FormRankingEntryOut
from app.services.form import calculate_form_score, form_sort_key

router = APIRouter()


@router.get("/form", response_model=list[FormRankingEntryOut])
async def get_form_ranking(
    season: str | None = Query(None, description="Season filter (default: current)"),
    matches: int = Query(5, description="Form window size (3, 5 or 10)"),
    position: str = Query("field", pattern="^(field|GK)$", description="Rank field players or GKs"),
    limit: int = Query(20, ge=1, le=50, description="Max results"),
    db: AsyncSession = Depends(get_db),
):
    """Form ranking: every player with match logs in the season, scored per position."""
    if not season:
        season = settings.current_season

    _validate_form_matches(matches)

    result = await db.execute(
        select(PlayerMatchLog, Player)
        .join(Player, PlayerMatchLog.player_id == Player.id)
        .where(PlayerMatchLog.season == season)
    )
    rows = result.all()

    # Group logs per player (small dataset — MVP scale, in-memory is enough)
    logs_by_player: dict[int, list[PlayerMatchLog]] = {}
    players_by_id: dict[int, Player] = {}
    for log, player in rows:
        logs_by_player.setdefault(player.id, []).append(log)
        players_by_id[player.id] = player

    scored = []
    for player_id, logs in logs_by_player.items():
        player = players_by_id[player_id]
        is_gk = player.position == "GK"
        if position == "GK" and not is_gk:
            continue
        if position == "field" and is_gk:
            continue

        form = calculate_form_score(logs, position=player.position or "field", matches=matches)
        if form is None:
            continue

        entry = FormRankingEntryOut(
            rank=0,  # assigned after sorting
            player_id=player_id,
            player_name=player.name,
            position=player.position,
            team=player.team,
            score=form.score,
            matches_count=form.matches_count,
            goals=form.goals,
            assists=form.assists,
            minutes=form.minutes,
            avg_rating=round(form.avg_rating, 2) if form.avg_rating is not None else None,
            clean_sheets=form.clean_sheets,
        )
        scored.append((form, entry))

    scored.sort(key=lambda pair: form_sort_key(pair[0]), reverse=True)

    entries = [entry for _, entry in scored[:limit]]
    for i, entry in enumerate(entries, start=1):
        entry.rank = i

    return entries
