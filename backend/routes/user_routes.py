"""
User Routes
============
Profile management, session management, login history,
password changes, 2FA setup, and data export.
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.database import get_db
from backend.database.models import User, LoginHistory, ActiveSession, AuditLog
from backend.auth.dependencies import get_current_user, get_client_ip
from backend.auth.password import hash_password, verify_password
from backend.security.totp import (
    generate_totp_secret, get_totp_uri, verify_totp,
    generate_recovery_codes, generate_qr_code_data,
)
from backend.security.encryption import encrypt_string
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/user", tags=["User"])


# ── Request Models ───────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    email: str | None = None
    username: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class Enable2FARequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    secret: str  # The TOTP secret to confirm


# ── Profile ──────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
):
    """Get the current user's profile."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_admin": current_user.is_admin,
        "is_verified": current_user.is_verified,
        "face_registered": current_user.face_registered,
        "is_2fa_enabled": current_user.is_2fa_enabled,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
        "last_password_change": current_user.last_password_change.isoformat() if current_user.last_password_change else None,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    }


@router.put("/profile")
async def update_profile(
    request: Request,
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile."""
    if body.email and body.email != current_user.email:
        existing = await db.execute(
            select(User).where(User.email == body.email.lower(), User.id != current_user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already in use")
        current_user.email = body.email.lower()

    if body.username and body.username != current_user.username:
        existing = await db.execute(
            select(User).where(User.username == body.username.lower(), User.id != current_user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Username already in use")
        current_user.username = body.username.lower()

    current_user.updated_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        user_id=current_user.id,
        action="user.profile_updated",
        ip_address=get_client_ip(request),
    ))

    return {"message": "Profile updated successfully"}


# ── Sessions ─────────────────────────────────────────────────

@router.get("/sessions")
async def get_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active sessions for the current user."""
    result = await db.execute(
        select(ActiveSession)
        .where(ActiveSession.user_id == current_user.id)
        .order_by(ActiveSession.created_at.desc())
    )
    sessions = result.scalars().all()

    return {
        "sessions": [
            {
                "id": s.id,
                "device_info": s.device_info,
                "ip_address": s.ip_address,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_used": s.last_used.isoformat() if s.last_used else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            }
            for s in sessions
        ],
        "total": len(sessions),
        "max_allowed": settings.max_active_sessions,
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific session."""
    result = await db.execute(
        select(ActiveSession).where(
            ActiveSession.id == session_id,
            ActiveSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(session)

    db.add(AuditLog(
        user_id=current_user.id,
        action="session.revoked",
        details=f"Session {session_id} revoked",
        ip_address=get_client_ip(request),
    ))

    return {"message": "Session revoked"}


# ── Login History ────────────────────────────────────────────

@router.get("/login-history")
async def get_login_history(
    page: int = 1,
    per_page: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated login history for the current user."""
    per_page = min(per_page, 100)  # Cap at 100
    offset = (page - 1) * per_page

    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(LoginHistory).where(
            LoginHistory.user_id == current_user.id
        )
    )
    total = count_result.scalar() or 0

    # Fetch page
    result = await db.execute(
        select(LoginHistory)
        .where(LoginHistory.user_id == current_user.id)
        .order_by(LoginHistory.timestamp.desc())
        .offset(offset)
        .limit(per_page)
    )
    history = result.scalars().all()

    return {
        "history": [
            {
                "id": h.id,
                "ip_address": h.ip_address,
                "user_agent": h.user_agent,
                "device_fingerprint": h.device_fingerprint,
                "geo_location": h.geo_location,
                "login_method": h.login_method,
                "success": h.success,
                "failure_reason": h.failure_reason,
                "timestamp": h.timestamp.isoformat() if h.timestamp else None,
            }
            for h in history
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


# ── Password Change ─────────────────────────────────────────

@router.post("/change-password")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    current_user.password_hash = hash_password(body.new_password)
    current_user.last_password_change = datetime.now(timezone.utc)

    db.add(AuditLog(
        user_id=current_user.id,
        action="user.password_changed",
        ip_address=get_client_ip(request),
    ))

    return {"message": "Password changed successfully"}


# ── 2FA Setup ────────────────────────────────────────────────

@router.post("/setup-2fa")
async def setup_2fa(
    current_user: User = Depends(get_current_user),
):
    """Generate a new TOTP secret and QR code for 2FA setup."""
    if current_user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")

    secret = generate_totp_secret()
    uri = get_totp_uri(secret, current_user.username)
    qr_code = generate_qr_code_data(uri)

    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_code}",
        "uri": uri,
        "message": "Scan the QR code with your authenticator app, then verify with a code.",
    }


@router.post("/enable-2fa")
async def enable_2fa(
    request: Request,
    body: Enable2FARequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify TOTP code and enable 2FA."""
    if current_user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")

    if not verify_totp(body.secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid verification code")

    # Encrypt and store the secret
    encrypted, nonce, salt = encrypt_string(body.secret, current_user.encryption_salt)
    current_user.totp_secret_encrypted = encrypted
    current_user.is_2fa_enabled = True

    # Generate recovery codes
    recovery_codes = generate_recovery_codes()
    codes_str = json.dumps(recovery_codes)
    enc_codes, _, _ = encrypt_string(codes_str, current_user.encryption_salt)
    current_user.recovery_codes_encrypted = enc_codes

    db.add(AuditLog(
        user_id=current_user.id,
        action="user.2fa_enabled",
        ip_address=get_client_ip(request),
    ))

    return {
        "message": "2FA enabled successfully",
        "recovery_codes": recovery_codes,
        "warning": "Save these recovery codes in a safe place. They cannot be shown again.",
    }


@router.post("/disable-2fa")
async def disable_2fa(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA for the current user."""
    if not current_user.is_2fa_enabled:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    current_user.is_2fa_enabled = False
    current_user.totp_secret_encrypted = None
    current_user.recovery_codes_encrypted = None

    db.add(AuditLog(
        user_id=current_user.id,
        action="user.2fa_disabled",
        ip_address=get_client_ip(request),
    ))

    return {"message": "2FA disabled"}


# ── Data Export ──────────────────────────────────────────────

@router.get("/export-data")
async def export_data(
    format: str = "json",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export user data as JSON or CSV."""
    # Fetch login history
    result = await db.execute(
        select(LoginHistory)
        .where(LoginHistory.user_id == current_user.id)
        .order_by(LoginHistory.timestamp.desc())
    )
    history = result.scalars().all()

    data = {
        "profile": {
            "username": current_user.username,
            "email": current_user.email,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "face_registered": current_user.face_registered,
            "is_2fa_enabled": current_user.is_2fa_enabled,
        },
        "login_history": [
            {
                "timestamp": h.timestamp.isoformat() if h.timestamp else None,
                "ip_address": h.ip_address,
                "login_method": h.login_method,
                "success": h.success,
                "failure_reason": h.failure_reason,
            }
            for h in history
        ],
    }

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "ip_address", "login_method", "success", "failure_reason"])
        for h in history:
            writer.writerow([
                h.timestamp.isoformat() if h.timestamp else "",
                h.ip_address or "",
                h.login_method or "",
                h.success,
                h.failure_reason or "",
            ])
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=faceauth_data.csv"},
        )

    return data
