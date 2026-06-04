"""Shared API dependencies."""

from fastapi import Header, HTTPException

from app.core.config import settings


async def verify_admin_key(x_secret_key: str = Header(...)):
    """Verify admin secret key from header.

    Used to protect admin and debug endpoints.
    Header name: x-secret-key
    """
    if not settings.secret_key or x_secret_key != settings.secret_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
