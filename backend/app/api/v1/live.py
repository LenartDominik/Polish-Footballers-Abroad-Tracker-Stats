"""Live match API endpoints."""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.v1.dependencies import verify_admin_key
from app.db.models import LiveMatchEvent
from app.db.session import get_db, AsyncSessionLocal
from app.schemas.live import (
    LiveEventOut,
    LiveMatchOut,
    LiveStatusOut,
    UpcomingMatchOut,
)
from app.services.live_poller import live_poller
from app.services.rapidapi import rapidapi_client

router = APIRouter()
logger = structlog.get_logger()


@router.get("/status", response_model=LiveStatusOut)
async def get_live_status():
    """Check if any tracked match is currently live or prematch."""
    current = live_poller.get_current_matches()
    prematch = live_poller.get_prematch_matches()

    has_live = any(m.get("status") not in ("prematch",) for m in current)

    return LiveStatusOut(
        is_live=has_live,
        matches_count=len([m for m in current if m.get("status") != "prematch"]),
        is_prematch=len(prematch) > 0,
        prematch_count=len(prematch),
    )


@router.get("/matches", response_model=List[LiveMatchOut])
async def get_live_matches():
    """Get current live and prematch matches with tracked Polish players."""
    current = live_poller.get_current_matches()

    if not current:
        return []

    async with AsyncSessionLocal() as session:
        matches = []
        for match_info in current:
            match_id = match_info["match_id"]
            rapidapi_id = match_info.get("rapidapi_id")

            # Get player DB ID for filtering
            db_player_id = live_poller._player_db_ids.get(rapidapi_id) if rapidapi_id else None

            # Get events from DB for this match and player
            query = (
                select(LiveMatchEvent)
                .where(LiveMatchEvent.match_id == match_id)
            )
            if db_player_id:
                query = query.where(LiveMatchEvent.player_id == db_player_id)
            query = query.order_by(LiveMatchEvent.minute)
            result = await session.execute(query)
            events = result.scalars().all()

            matches.append(LiveMatchOut(
                match_id=match_id,
                home_team=match_info.get("home_team", events[0].home_team if events else ""),
                away_team=match_info.get("away_team", events[0].away_team if events else ""),
                home_score=match_info.get("home_score", 0),
                away_score=match_info.get("away_score", 0),
                status=match_info.get("status", "unknown"),
                minute=match_info.get("minute"),
                competition=match_info.get("competition"),
                player_name=match_info.get("player_name"),
                lineup_status=match_info.get("lineup_status"),
                kickoff_time=match_info.get("kickoff_time"),
                events=[LiveEventOut.model_validate(e) for e in events],
            ))

    return matches


@router.get("/upcoming", response_model=List[UpcomingMatchOut])
async def get_upcoming_matches(
    limit: int = Query(default=5, ge=1, le=10),
):
    """Get upcoming matches (next 7 days) with tracked Polish players."""
    matches = await live_poller.get_upcoming_matches(limit=limit)
    return [UpcomingMatchOut(**{k: v for k, v in m.items() if k != "_hours_until"}) for m in matches]


@router.get("/debug/match-status/{match_id}")
async def debug_match_status(
    match_id: int,
    _: None = Depends(verify_admin_key),
):
    """Debug: check raw match status from RapidAPI."""
    try:
        raw = await rapidapi_client.get_match_status(match_id)
        return {"match_id": match_id, "raw": raw}
    except Exception as e:
        return {"match_id": match_id, "error": str(e)}


@router.get("/debug/test-apis/{match_id}")
async def debug_test_apis(
    match_id: int,
    _: None = Depends(verify_admin_key),
):
    """Test all RapidAPI endpoints for a given match."""
    results = {}

    # 1. get_match_status
    try:
        raw = await rapidapi_client.get_match_status(match_id)
        results["get_match_status"] = {"ok": True, "data": raw}
    except Exception as e:
        results["get_match_status"] = {"ok": False, "error": str(e)}

    # 2. get_match_score
    try:
        raw = await rapidapi_client.get_match_score(match_id)
        results["get_match_score"] = {"ok": True, "data": raw}
    except Exception as e:
        results["get_match_score"] = {"ok": False, "error": str(e)}

    # 3. get_lineup_home
    try:
        raw = await rapidapi_client.get_lineup_home(match_id)
        results["get_lineup_home"] = {"ok": True, "summary": _summarize_lineup(raw)}
    except Exception as e:
        results["get_lineup_home"] = {"ok": False, "error": str(e)}

    # 4. get_lineup_away
    try:
        raw = await rapidapi_client.get_lineup_away(match_id)
        results["get_lineup_away"] = {"ok": True, "summary": _summarize_lineup(raw)}
    except Exception as e:
        results["get_lineup_away"] = {"ok": False, "error": str(e)}

    # 5. get_matches_by_league (Primeira Liga = 61)
    try:
        raw = await rapidapi_client.get_matches_by_league(61)
        found = any(m.get("id") == match_id for m in raw if isinstance(m, dict))
        results["get_matches_by_league"] = {"ok": True, "total_matches": len(raw), "match_found": found}
    except Exception as e:
        results["get_matches_by_league"] = {"ok": False, "error": str(e)}

    return results


def _summarize_lineup(data: dict) -> dict:
    """Summarize lineup response without exposing full data."""
    if not data or not isinstance(data, dict):
        return {"raw_type": type(data).__name__}
    resp = data.get("response", data)
    if isinstance(resp, dict):
        lineup = resp.get("lineup", resp)
        if isinstance(lineup, dict):
            return {"keys": list(lineup.keys()), "starters": len(lineup.get("starters", [])), "subs": len(lineup.get("subs", []))}
        elif isinstance(lineup, list):
            return {"format": "list", "count": len(lineup)}
    return {"keys": list(resp.keys()) if isinstance(resp, dict) else "non-dict"}


@router.get("/debug/poller-state")
async def debug_poller_state(
    _: None = Depends(verify_admin_key),
):
    """Debug: show poller internal state."""
    return {
        "running": live_poller._running,
        "current_matches_count": len(live_poller._current_matches),
        "fixture_check_date": str(live_poller._fixture_check_date),
        "has_match_today": live_poller._has_match_today,
        "given_up_match_ids": list(live_poller._given_up_match_ids),
        "status_failures": {f"{k[0]}_{k[1]}": v for k, v in live_poller._status_failures.items()},
        "current_matches": {
            f"{k[0]}_{k[1]}": {
                "status": v.get("status"),
                "home_score": v.get("home_score"),
                "away_score": v.get("away_score"),
                "minute": v.get("minute"),
                "lineup_status": v.get("lineup_status"),
            }
            for k, v in live_poller._current_matches.items()
        },
    }


@router.get("/matches/{match_id}/events", response_model=List[LiveEventOut])
async def get_match_events(
    match_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get all saved events (goals, assists) for a specific match."""
    result = await db.execute(
        select(LiveMatchEvent)
        .where(LiveMatchEvent.match_id == match_id)
        .order_by(LiveMatchEvent.minute)
    )
    events = result.scalars().all()
    return events
