"""
Application Configuration
=========================
Centralized configuration using Pydantic BaseSettings.
Loads values from environment variables and .env file.
"""

import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve project root (one level up from backend/)
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = DATA_DIR / "backups"
VAULT_DIR = DATA_DIR / "vault"

# Ensure runtime directories exist
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)
VAULT_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Defaults are suitable for local development only.
    """

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_name: str = "FaceAuth"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ── Database ─────────────────────────────────────────────
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'faceauth.db'}"

    # ── JWT ──────────────────────────────────────────────────
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_use_secrets_token_urlsafe_64"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # ── Encryption ───────────────────────────────────────────
    master_encryption_key: str = "CHANGE_ME_IN_PRODUCTION"

    # ── Face Recognition ─────────────────────────────────────
    face_match_threshold: float = 0.6
    face_quality_min_score: int = 85
    face_min_size: int = 100
    liveness_required_frames: int = 3

    # ── Rate Limiting ────────────────────────────────────────
    max_login_attempts: int = 5
    account_lock_duration_minutes: int = 30
    rate_limit_per_minute: int = 100

    # ── Sessions ─────────────────────────────────────────────
    max_active_sessions: int = 5

    # ── Email ────────────────────────────────────────────────
    email_backend: str = "console"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@faceauth.local"

    # ── CORS ─────────────────────────────────────────────────
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    # ── Backup ───────────────────────────────────────────────
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    backup_retention_days: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton — loaded once per process."""
    return Settings()
