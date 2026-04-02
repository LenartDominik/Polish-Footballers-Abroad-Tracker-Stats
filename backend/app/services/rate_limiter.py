# -*- coding: utf-8 -*-
"""Rate limiter for RapidAPI requests with database tracking."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Rate limits (safe values for RapidAPI Basic plan)
# Can be overridden via environment variables
MAX_REQUESTS_PER_MINUTE = 30
MAX_REQUESTS_PER_HOUR = 500
MIN_REQUEST_INTERVAL = 2.0  # Minimum seconds between requests


class RateLimiter:
    """Token bucket rate limiter with database tracking.

    Ensures we don't exceed RapidAPI rate limits:
    - Max 30 requests per minute
    - Max 500 requests per hour
    - Minimum 2 seconds between requests
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self._last_request_time: datetime | None = None
        self._request_count = 0  # Local counter for logging

    async def acquire(self) -> None:
        """Wait for available token before making a request.

        This should be called before every API request.
        """
        now = datetime.utcnow()

        # Minimum interval between requests
        if self._last_request_time is not None:
            elapsed = (now - self._last_request_time).total_seconds()
            if elapsed < MIN_REQUEST_INTERVAL:
                sleep_time = MIN_REQUEST_INTERVAL - elapsed
                await asyncio.sleep(sleep_time)

        # Check per-minute limit
        minute_ago = datetime.utcnow() - timedelta(minutes=1)
        count = await self._count_requests_since(minute_ago)
        if count >= MAX_REQUESTS_PER_MINUTE:
            wait_time = 60 - (datetime.utcnow() - minute_ago).seconds
            print(f"  ⏳ Rate limit: waiting {wait_time}s (minute limit: {count}/{MAX_REQUESTS_PER_MINUTE})")
            await asyncio.sleep(wait_time)

        # Check per-hour limit
        hour_ago = datetime.utcnow() - timedelta(hours=1)
        count = await self._count_requests_since(hour_ago)
        if count >= MAX_REQUESTS_PER_HOUR:
            # Wait until oldest request falls out of 1-hour window
            oldest = await self._get_oldest_request_since(hour_ago)
            if oldest:
                wait_time = 3600 - (datetime.utcnow() - oldest).total_seconds()
                wait_time = max(1, int(wait_time))  # at least 1 second
            else:
                wait_time = 60  # fallback: wait 1 minute
            print(f"  ⏳ Rate limit: waiting {wait_time}s (hour limit: {count}/{MAX_REQUESTS_PER_HOUR})")
            # Commit przed długim czekaniem - zapobiega idle connection disconnect
            await self.session.commit()
            await asyncio.sleep(wait_time)

        # Log request to database
        await self._log_request()
        self._last_request_time = datetime.utcnow()
        self._request_count += 1

    async def _count_requests_since(self, since: datetime) -> int:
        """Count requests made since a given timestamp."""
        from app.db.models import ApiRateLimit

        try:
            result = await self.session.execute(
                select(func.count(ApiRateLimit.id)).where(
                    ApiRateLimit.timestamp >= since
                )
            )
            return result.scalar() or 0
        except Exception:
            # If table doesn't exist yet, return 0
            return 0

    async def _get_oldest_request_since(self, since: datetime) -> datetime | None:
        """Get the oldest request timestamp since a given time."""
        from app.db.models import ApiRateLimit

        try:
            result = await self.session.execute(
                select(ApiRateLimit.timestamp)
                .where(ApiRateLimit.timestamp >= since)
                .order_by(ApiRateLimit.timestamp.asc())
                .limit(1)
            )
            return result.scalar_one_or_none()
        except Exception:
            return None

    async def _log_request(self) -> None:
        """Log request to database for tracking."""
        from app.db.models import ApiRateLimit

        try:
            log = ApiRateLimit(timestamp=datetime.utcnow())
            self.session.add(log)
            await self.session.commit()
        except Exception as e:
            # If table doesn't exist, just skip logging
            print(f"  ⚠️ Could not log request: {e}")
            await self.session.rollback()

    async def cleanup_old_logs(self, hours: int = 2) -> int:
        """Remove old log entries (older than specified hours).

        Returns number of deleted entries.
        """
        from app.db.models import ApiRateLimit

        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            result = await self.session.execute(
                ApiRateLimit.__table__.delete().where(
                    ApiRateLimit.timestamp < cutoff
                )
            )
            await self.session.commit()
            return result.rowcount
        except Exception:
            return 0

    @property
    def request_count(self) -> int:
        """Number of requests made in this session."""
        return self._request_count


class InMemoryRateLimiter:
    """Simple in-memory rate limiter for when database is not available.

    Uses sliding window algorithm.
    """

    def __init__(self):
        self._request_times: list[datetime] = []
        self._last_request_time: datetime | None = None
        self._request_count = 0

    async def acquire(self) -> None:
        """Wait for available token before making a request."""
        now = datetime.utcnow()

        # Clean old entries
        self._request_times = [
            t for t in self._request_times
            if (now - t).total_seconds() < 3600
        ]

        # Minimum interval between requests
        if self._last_request_time is not None:
            elapsed = (now - self._last_request_time).total_seconds()
            if elapsed < MIN_REQUEST_INTERVAL:
                await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)

        # Check per-minute limit
        minute_ago = now - timedelta(minutes=1)
        minute_count = sum(1 for t in self._request_times if t > minute_ago)
        if minute_count >= MAX_REQUESTS_PER_MINUTE:
            wait_time = 60 - (now - minute_ago).seconds
            print(f"  ⏳ Rate limit: waiting {wait_time}s (minute limit)")
            await asyncio.sleep(wait_time)

        # Check per-hour limit
        hour_ago = now - timedelta(hours=1)
        hour_requests = [t for t in self._request_times if t > hour_ago]
        if len(hour_requests) >= MAX_REQUESTS_PER_HOUR:
            # Wait until oldest request in window expires
            oldest = min(hour_requests)
            wait_time = 3600 - (now - oldest).total_seconds()
            wait_time = max(1, int(wait_time))
            print(f"  ⏳ Rate limit: waiting {wait_time}s (hour limit)")
            await asyncio.sleep(wait_time)

        # Log request
        self._request_times.append(datetime.utcnow())
        self._last_request_time = datetime.utcnow()
        self._request_count += 1

    @property
    def request_count(self) -> int:
        """Number of requests made in this session."""
        return self._request_count
