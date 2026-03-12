"""Leagues API endpoints."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import League

router = APIRouter()


@router.get("/")
async def get_leagues(db: AsyncSession = Depends(get_db)):
    """Get all leagues with Polish players."""
    result = await db.execute(
        select(League).order_by(League.name)
    )
    leagues = result.scalars().all()

    return [
        {
            "id": league.id,
            "rapidapi_id": league.rapidapi_id,
            "name": league.name,
            "country": league.country,
        }
        for league in leagues
    ]
