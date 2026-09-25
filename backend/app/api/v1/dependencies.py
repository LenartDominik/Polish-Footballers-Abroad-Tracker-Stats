"""Shared API dependencies."""

import secrets

from fastapi import Header, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


async def verify_admin_key(x_secret_key: str = Header(...)):
    """Verify admin secret key from header.

    Used to protect admin and debug endpoints.
    Header name: x-secret-key
    """
    if not settings.secret_key or not secrets.compare_digest(
        x_secret_key, settings.secret_key
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


# Rate limiter (HTTP endpoint protection)
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
