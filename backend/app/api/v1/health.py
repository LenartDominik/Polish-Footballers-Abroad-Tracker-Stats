"""Health check endpoints for monitoring and wake-up."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {
        "status": "ok",
        "service": "polish-footballers-tracker",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health/db")
async def health_check_db(db: AsyncSession = Depends(get_db)):
    """
    Health check with database test - USE FOR WAKE-UP.

    This endpoint:
    1. Wakes up backend (Render cold start)
    2. Wakes up database connection (Supabase pool)
    3. Verifies everything works
    """
    try:
        await db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "service": "polish-footballers-tracker",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "database": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, 503
