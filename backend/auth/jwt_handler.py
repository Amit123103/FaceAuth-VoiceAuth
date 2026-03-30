"""
JWT Token Handler
=================
Create, validate, and manage JWT access & refresh tokens.
Supports token blacklisting for logout.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database.models import TokenBlacklist

settings = get_settings()


def create_access_token(
    user_id: str,
    username: str,
    is_admin: bool = False,
    extra_claims: dict = None,
) -> str:
    """
    Create a short-lived JWT access token.
    
    Args:
        user_id: The user's UUID.
        username: The user's username.
        is_admin: Whether the user has admin privileges.
        extra_claims: Additional claims to embed in the token.
    
    Returns:
        Encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """
    Create a long-lived JWT refresh token.
    Contains minimal claims for security.
    
    Args:
        user_id: The user's UUID.
    
    Returns:
        Encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: The encoded JWT string.
    
    Returns:
        Decoded payload dict, or None if invalid/expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None


async def blacklist_token(
    token: str,
    db: AsyncSession,
) -> bool:
    """
    Add a token to the blacklist (for logout).
    
    Args:
        token: The JWT token to blacklist.
        db: Async database session.
    
    Returns:
        True if successfully blacklisted, False if decode failed.
    """
    payload = decode_token(token)
    if not payload:
        return False

    jti = payload.get("jti")
    if not jti:
        return False

    # Check if already blacklisted
    result = await db.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == jti)
    )
    if result.scalar_one_or_none():
        return True  # Already blacklisted

    blacklisted = TokenBlacklist(
        jti=jti,
        user_id=payload.get("sub"),
        token_type=payload.get("type", "access"),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )
    db.add(blacklisted)
    return True


async def is_token_blacklisted(jti: str, db: AsyncSession) -> bool:
    """
    Check if a token JTI is in the blacklist.
    
    Args:
        jti: The JWT ID to check.
        db: Async database session.
    
    Returns:
        True if the token is blacklisted.
    """
    result = await db.execute(
        select(TokenBlacklist).where(TokenBlacklist.jti == jti)
    )
    return result.scalar_one_or_none() is not None


async def cleanup_expired_blacklist(db: AsyncSession):
    """Remove expired tokens from the blacklist to keep the table small."""
    from sqlalchemy import delete
    await db.execute(
        delete(TokenBlacklist).where(
            TokenBlacklist.expires_at < datetime.now(timezone.utc)
        )
    )
