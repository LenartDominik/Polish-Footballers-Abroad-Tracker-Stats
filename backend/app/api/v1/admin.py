"""Admin endpoints for sync management."""

import subprocess
import asyncio
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import SyncLog
from app.notifications import send_sync_failed_email, send_sync_success_email

router = APIRouter()

# Path to sync_full.py (backend root directory)
BACKEND_DIR = Path(__file__).parent.parent.parent.parent
SYNC_SCRIPT = BACKEND_DIR / "sync_full.py"


@router.post("/admin/sync")
async def trigger_sync(
    player_id: int = None,
    x_secret_key: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """Trigger sync with logging.

    Args:
        player_id: Optional RapidAPI player ID to sync single player
    """
    # Verify API key
    expected = os.environ.get("SECRET_KEY", "")
    if not expected or x_secret_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Create sync log
    sync_log = SyncLog(
        sync_type="single" if player_id else "scheduled",
        started_at=datetime.utcnow(),
        status="running"
    )
    db.add(sync_log)
    await db.commit()
    await db.refresh(sync_log)

    try:
        # Build sync command (use uv run to ensure venv dependencies)
        cmd = ["uv", "run", "python", str(SYNC_SCRIPT)]
        if player_id:
            cmd.extend(["--player", str(player_id)])

        # Run sync via subprocess (isolates from API process)
        result = await run_in_threadpool(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout
            cwd=str(BACKEND_DIR)  # Run from backend directory
        )

        if result.returncode != 0:
            raise Exception(f"Sync failed: {result.stderr or result.stdout}")

        # Parse output to get matches processed
        output = result.stdout
        players_updated = 0
        import re
        match = re.search(r'SYNC COMPLETE:\s*(\d+)\s*matches processed', output)
        if match:
            players_updated = int(match.group(1))

        # Update log on success
        sync_log.status = "success"
        sync_log.finished_at = datetime.utcnow()
        sync_log.players_updated = players_updated
        sync_log.api_calls_used = 1
        await db.commit()

        # Send success email (optional, non-blocking)
        try:
            send_sync_success_email({
                "started_at": sync_log.started_at.isoformat(),
                "players_updated": sync_log.players_updated,
                "api_calls_used": sync_log.api_calls_used,
                "duration_seconds": (sync_log.finished_at - sync_log.started_at).total_seconds()
            })
        except Exception as e:
            print(f"Failed to send success email: {e}")

        return {
            "status": "success",
            "players_updated": players_updated,
            "duration_seconds": (sync_log.finished_at - sync_log.started_at).total_seconds()
        }

    except subprocess.TimeoutExpired:
        # Update log on timeout
        sync_log.status = "failed"
        sync_log.finished_at = datetime.utcnow()
        sync_log.error_message = "Sync timeout (10 min)"
        await db.commit()

        # Send failure email
        try:
            send_sync_failed_email("Sync timeout (10 min)", {
                "started_at": sync_log.started_at.isoformat(),
                "players_updated": sync_log.players_updated,
                "api_calls_used": sync_log.api_calls_used
            })
        except Exception as e:
            print(f"Failed to send failure email: {e}")

        raise HTTPException(status_code=500, detail="Sync timeout")

    except Exception as e:
        # Update log on failure
        sync_log.status = "failed"
        sync_log.finished_at = datetime.utcnow()
        sync_log.error_message = str(e)
        await db.commit()

        # Send failure email
        try:
            send_sync_failed_email(str(e), {
                "started_at": sync_log.started_at.isoformat(),
                "players_updated": sync_log.players_updated,
                "api_calls_used": sync_log.api_calls_used
            })
        except Exception as e:
            print(f"Failed to send failure email: {e}")

        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/sync/logs")
async def get_sync_logs(
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """Get recent sync logs."""
    result = await db.execute(
        select(SyncLog)
        .order_by(SyncLog.started_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "sync_type": log.sync_type,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "finished_at": log.finished_at.isoformat() if log.finished_at else None,
            "status": log.status,
            "players_updated": log.players_updated,
            "api_calls_used": log.api_calls_used,
            "error_message": log.error_message
        }
        for log in logs
    ]
