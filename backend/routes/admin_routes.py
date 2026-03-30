"""
Admin Routes
=============
Administrative endpoints for user management,
audit logs, and backup operations.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.database import get_db
from backend.database.models import User, AuditLog, LoginHistory, ActiveSession, BackupLog
from backend.database.backup import export_backup, list_backups
from backend.auth.dependencies import get_admin_user, get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ── Users ────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    page: int = 1,
    per_page: int = 20,
    search: str = "",
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users with pagination and optional search."""
    per_page = min(per_page, 100)
    offset = (page - 1) * per_page

    query = select(User)
    count_query = select(func.count()).select_from(User)

    if search:
        search_filter = (
            User.username.ilike(f"%{search}%") |
            User.email.ilike(f"%{search}%")
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(per_page)
    )
    users = result.scalars().all()

    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "is_admin": u.is_admin,
                "is_verified": u.is_verified,
                "face_registered": u.face_registered,
                "is_2fa_enabled": u.is_2fa_enabled,
                "failed_login_count": u.failed_login_count,
                "is_locked": u.is_locked,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user account."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    username = user.username
    await db.delete(user)

    db.add(AuditLog(
        user_id=admin.id,
        action="admin.user_deleted",
        details=f"Deleted user: {username} ({user_id})",
        ip_address=get_client_ip(request),
    ))

    return {"message": f"User {username} deleted"}


@router.post("/users/{user_id}/lock")
async def toggle_user_lock(
    user_id: str,
    request: Request,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Lock or unlock a user account."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_locked:
        # Unlock
        user.locked_until = None
        user.failed_login_count = 0
        action = "unlocked"
    else:
        # Lock indefinitely (admin override)
        user.locked_until = datetime(2099, 12, 31, tzinfo=timezone.utc)
        action = "locked"

    db.add(AuditLog(
        user_id=admin.id,
        action=f"admin.user_{action}",
        details=f"User {user.username} {action}",
        ip_address=get_client_ip(request),
    ))

    return {"message": f"User {user.username} has been {action}"}


@router.post("/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: str,
    request: Request,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle admin status for a user."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own admin status")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_admin = not user.is_admin

    db.add(AuditLog(
        user_id=admin.id,
        action="admin.admin_toggled",
        details=f"User {user.username} admin: {user.is_admin}",
        ip_address=get_client_ip(request),
    ))

    return {"message": f"User {user.username} admin status: {user.is_admin}"}


# ── Audit Logs ───────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    page: int = 1,
    per_page: int = 50,
    action: str = "",
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """View system audit logs."""
    per_page = min(per_page, 200)
    offset = (page - 1) * per_page

    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if action:
        query = query.where(AuditLog.action.ilike(f"%{action}%"))
        count_query = count_query.where(AuditLog.action.ilike(f"%{action}%"))

    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(per_page)
    )
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "details": log.details,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ── Backups ──────────────────────────────────────────────────

@router.get("/backups")
async def get_backups(
    admin: User = Depends(get_admin_user),
):
    """List all backup files."""
    backups = await list_backups()
    return {"backups": backups}


@router.post("/backups")
async def trigger_backup(
    request: Request,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a manual backup."""
    result = await export_backup(backup_type="manual", db=db)

    db.add(AuditLog(
        user_id=admin.id,
        action="admin.backup_triggered",
        details=f"Manual backup: {result.get('file_path', 'unknown')}",
        ip_address=get_client_ip(request),
    ))

    return result


# ── Stats ────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get system statistics."""
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    active_users = (await db.execute(
        select(func.count()).select_from(User).where(User.is_active == True)
    )).scalar() or 0
    face_registered = (await db.execute(
        select(func.count()).select_from(User).where(User.face_registered == True)
    )).scalar() or 0
    active_sessions = (await db.execute(
        select(func.count()).select_from(ActiveSession)
    )).scalar() or 0
    total_logins = (await db.execute(
        select(func.count()).select_from(LoginHistory).where(LoginHistory.success == True)
    )).scalar() or 0
    failed_logins = (await db.execute(
        select(func.count()).select_from(LoginHistory).where(LoginHistory.success == False)
    )).scalar() or 0
    locked_accounts = (await db.execute(
        select(func.count()).select_from(User).where(User.locked_until != None)
    )).scalar() or 0

    return {
        "total_users": total_users,
        "active_users": active_users,
        "face_registered": face_registered,
        "active_sessions": active_sessions,
        "total_logins": total_logins,
        "failed_logins": failed_logins,
        "locked_accounts": locked_accounts,
    }
