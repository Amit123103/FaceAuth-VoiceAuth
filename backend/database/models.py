"""
Database ORM Models
===================
SQLAlchemy 2.0 models for all application tables.
Includes proper indexing, relationships, and column constraints.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    Text, LargeBinary, ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database.database import Base


def utcnow():
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def generate_uuid():
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════
# USERS TABLE
# ═══════════════════════════════════════════════════════════════
class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # Face biometric data (encrypted/hashed)
    face_encoding_encrypted = Column(LargeBinary, nullable=True)
    face_encoding_iv = Column(LargeBinary, nullable=True)
    encryption_salt = Column(LargeBinary, nullable=True)
    face_registered = Column(Boolean, default=False)
    face_image_base64 = Column(Text, nullable=True) # Stored reference image
    
    # Voice biometric data (encrypted/hashed)
    voice_registered = Column(Boolean, default=False)
    voice_embedding_encrypted = Column(LargeBinary, nullable=True)
    voice_sample_blob = Column(LargeBinary, nullable=True) # Stored reference WAV
    voice_phrase_hash = Column(String(512), nullable=True)
    voice_phrase_encrypted = Column(LargeBinary, nullable=True)
    voice_phrase_iv = Column(LargeBinary, nullable=True)
    
    # AI Authentication Metrics
    spoof_detection_score = Column(Float, default=1.0)
    authentication_confidence_score = Column(Float, default=1.0)

    # Account status
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    verification_code = Column(String(6), nullable=True)
    verification_expires = Column(DateTime, nullable=True)

    # 2FA
    is_2fa_enabled = Column(Boolean, default=False)
    totp_secret_encrypted = Column(LargeBinary, nullable=True)
    recovery_codes_encrypted = Column(LargeBinary, nullable=True)

    # Security
    failed_login_count = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    last_password_change = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    login_history = relationship("LoginHistory", back_populates="user", cascade="all, delete-orphan")
    active_sessions = relationship("ActiveSession", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"

    @property
    def is_locked(self) -> bool:
        """Check if account is currently locked."""
        if self.locked_until is None:
            return False
        return datetime.now(timezone.utc) < self.locked_until


# ═══════════════════════════════════════════════════════════════
# LOGIN HISTORY TABLE
# ═══════════════════════════════════════════════════════════════
class LoginHistory(Base):
    __tablename__ = "login_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    user_agent = Column(Text, nullable=True)
    device_fingerprint = Column(String(64), nullable=True)
    geo_location = Column(String(255), nullable=True)
    login_method = Column(String(20), nullable=True)  # 'password', 'face', 'face+password'
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="login_history")

    __table_args__ = (
        Index("idx_login_history_user_time", "user_id", "timestamp"),
    )


# ═══════════════════════════════════════════════════════════════
# ACTIVE SESSIONS TABLE
# ═══════════════════════════════════════════════════════════════
class ActiveSession(Base):
    __tablename__ = "active_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    refresh_token_hash = Column(String(255), nullable=False, unique=True)
    device_info = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_used = Column(DateTime, default=utcnow, nullable=True)

    # Relationships
    user = relationship("User", back_populates="active_sessions")

    __table_args__ = (
        Index("idx_sessions_user", "user_id"),
        Index("idx_sessions_expires", "expires_at"),
    )


# ═══════════════════════════════════════════════════════════════
# AUDIT LOGS TABLE
# ═══════════════════════════════════════════════════════════════
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_user_time", "user_id", "timestamp"),
        Index("idx_audit_action", "action"),
    )


# ═══════════════════════════════════════════════════════════════
# BACKUP LOGS TABLE
# ═══════════════════════════════════════════════════════════════
class BackupLog(Base):
    __tablename__ = "backup_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    backup_type = Column(String(20), nullable=False)  # 'automatic', 'manual'
    file_path = Column(String(500), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    tables_exported = Column(Text, nullable=True)  # JSON list of table names
    record_count = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False)  # 'success', 'failed'
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)


# ═══════════════════════════════════════════════════════════════
# TOKEN BLACKLIST TABLE (for JWT logout)
# ═══════════════════════════════════════════════════════════════
class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    jti = Column(String(36), unique=True, nullable=False, index=True)  # JWT ID
    user_id = Column(String(36), nullable=True)
    token_type = Column(String(10), nullable=False)  # 'access' or 'refresh'
    expires_at = Column(DateTime, nullable=False)
    blacklisted_at = Column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        Index("idx_blacklist_expires", "expires_at"),
    )
