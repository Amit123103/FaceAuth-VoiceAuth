"""
Rate Limiter & Account Lockout
===============================
In-memory rate limiting with database-backed account lockout.
"""

import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database.models import User

settings = get_settings()


class RateLimiter:
    """
    In-memory sliding window rate limiter.
    Tracks request counts per IP address.
    """

    def __init__(self):
        # {ip: [(timestamp, ...), ...]}
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, ip: str, window_seconds: int = 60):
        """Remove entries older than the window."""
        cutoff = time.time() - window_seconds
        self._requests[ip] = [
            ts for ts in self._requests[ip] if ts > cutoff
        ]

    def is_rate_limited(self, ip: str) -> bool:
        """
        Check if an IP has exceeded the rate limit.
        
        Returns:
            True if rate limited.
        """
        self._cleanup(ip)
        return len(self._requests[ip]) >= settings.rate_limit_per_minute

    def record_request(self, ip: str):
        """Record a request from an IP address."""
        self._requests[ip].append(time.time())

    def get_remaining(self, ip: str) -> int:
        """Get remaining requests in the current window."""
        self._cleanup(ip)
        return max(0, settings.rate_limit_per_minute - len(self._requests[ip]))


# Global rate limiter instance
rate_limiter = RateLimiter()


async def check_rate_limit(request: Request):
    """
    FastAPI dependency to enforce rate limiting.
    
    Raises:
        HTTPException 429: If rate limit exceeded.
    """
    ip = request.client.host if request.client else "unknown"
    
    if rate_limiter.is_rate_limited(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
                "X-RateLimit-Remaining": "0",
            },
        )
    
    rate_limiter.record_request(ip)


async def check_account_lockout(user: User) -> Optional[str]:
    """
    Check if a user account is currently locked.
    
    Returns:
        Lock message if locked, None if not locked.
    """
    if user.locked_until and datetime.now(timezone.utc) < user.locked_until:
        remaining = (user.locked_until - datetime.now(timezone.utc)).total_seconds()
        minutes = int(remaining / 60) + 1
        return f"Account is locked. Try again in {minutes} minute(s)."
    return None


async def record_failed_login(user: User, db: AsyncSession):
    """
    Increment failed login counter and lock account if threshold reached.
    """
    new_count = (user.failed_login_count or 0) + 1
    lock_until = None

    if new_count >= settings.max_login_attempts:
        lock_until = datetime.now(timezone.utc) + timedelta(
            minutes=settings.account_lock_duration_minutes
        )

    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            failed_login_count=new_count,
            locked_until=lock_until,
        )
    )


async def reset_failed_logins(user: User, db: AsyncSession):
    """Reset failed login counter after successful login."""
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            failed_login_count=0,
            locked_until=None,
            last_login=datetime.now(timezone.utc),
        )
    )
