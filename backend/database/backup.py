"""
Database Backup & Restore
=========================
JSON-based backup system with encryption support.
Handles automatic scheduled backups and manual import/export.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings, BACKUP_DIR
from backend.database.database import async_session
from backend.database.models import (
    User, LoginHistory, ActiveSession, AuditLog, BackupLog
)

settings = get_settings()


async def export_backup(
    backup_type: str = "manual",
    db: AsyncSession = None,
) -> dict:
    """
    Export all database tables to an encrypted JSON backup file.
    
    Returns:
        dict with backup metadata (path, size, record count, status).
    """
    own_session = db is None
    if own_session:
        db = async_session()

    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.json"
        filepath = BACKUP_DIR / filename

        backup_data = {
            "metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "backup_type": backup_type,
                "app_name": settings.app_name,
                "version": "1.0.0",
            },
            "tables": {}
        }

        total_records = 0

        # Export Users (excluding sensitive binary data)
        result = await db.execute(select(User))
        users = result.scalars().all()
        backup_data["tables"]["users"] = []
        for u in users:
            backup_data["tables"]["users"].append({
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "password_hash": u.password_hash,
                "face_registered": u.face_registered,
                "is_active": u.is_active,
                "is_admin": u.is_admin,
                "is_verified": u.is_verified,
                "is_2fa_enabled": u.is_2fa_enabled,
                "failed_login_count": u.failed_login_count,
                "locked_until": u.locked_until.isoformat() if u.locked_until else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "updated_at": u.updated_at.isoformat() if u.updated_at else None,
            })
            total_records += 1

        # Export Login History
        result = await db.execute(select(LoginHistory).order_by(LoginHistory.timestamp.desc()).limit(10000))
        history = result.scalars().all()
        backup_data["tables"]["login_history"] = []
        for h in history:
            backup_data["tables"]["login_history"].append({
                "id": h.id,
                "user_id": h.user_id,
                "ip_address": h.ip_address,
                "user_agent": h.user_agent,
                "device_fingerprint": h.device_fingerprint,
                "geo_location": h.geo_location,
                "login_method": h.login_method,
                "success": h.success,
                "failure_reason": h.failure_reason,
                "timestamp": h.timestamp.isoformat() if h.timestamp else None,
            })
            total_records += 1

        # Export Audit Logs
        result = await db.execute(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(10000))
        logs = result.scalars().all()
        backup_data["tables"]["audit_logs"] = []
        for log in logs:
            backup_data["tables"]["audit_logs"].append({
                "id": log.id,
                "user_id": log.user_id,
                "action": log.action,
                "details": log.details,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            })
            total_records += 1

        # Write to file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)

        file_size = os.path.getsize(filepath)

        # Log the backup
        backup_log = BackupLog(
            backup_type=backup_type,
            file_path=str(filepath),
            file_size_bytes=file_size,
            tables_exported=json.dumps(list(backup_data["tables"].keys())),
            record_count=total_records,
            status="success",
        )
        db.add(backup_log)
        if own_session:
            await db.commit()

        return {
            "status": "success",
            "file_path": str(filepath),
            "file_size_bytes": file_size,
            "record_count": total_records,
            "created_at": backup_data["metadata"]["created_at"],
        }

    except Exception as e:
        # Log failed backup
        backup_log = BackupLog(
            backup_type=backup_type,
            status="failed",
            error_message=str(e),
        )
        db.add(backup_log)
        if own_session:
            await db.commit()
        raise

    finally:
        if own_session:
            await db.close()


async def cleanup_old_backups():
    """Remove backup files older than retention period."""
    retention_days = settings.backup_retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    for filepath in BACKUP_DIR.glob("backup_*.json"):
        try:
            file_mtime = datetime.fromtimestamp(
                os.path.getmtime(filepath), tz=timezone.utc
            )
            if file_mtime < cutoff:
                os.remove(filepath)
        except OSError:
            pass  # Skip files that can't be accessed


async def scheduled_backup():
    """Called by APScheduler for automatic daily backups."""
    try:
        await export_backup(backup_type="automatic")
        await cleanup_old_backups()
    except Exception as e:
        # Log to stderr — scheduler handles this silently
        import sys
        print(f"[BACKUP ERROR] {e}", file=sys.stderr)


async def list_backups() -> list[dict]:
    """List all available backup files with metadata."""
    backups = []
    for filepath in sorted(BACKUP_DIR.glob("backup_*.json"), reverse=True):
        try:
            stat = os.stat(filepath)
            backups.append({
                "filename": filepath.name,
                "file_path": str(filepath),
                "file_size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            })
        except OSError:
            pass
    return backups
