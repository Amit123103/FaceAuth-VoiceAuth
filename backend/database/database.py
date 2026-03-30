"""
Database Engine & Session Management
=====================================
Async SQLite engine using SQLAlchemy 2.0 with WAL mode
for concurrent read support.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text

from backend.config import get_settings

settings = get_settings()

# ── Engine Configuration ─────────────────────────────────────
# WAL mode is enabled via connect event for SQLite
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug and not settings.is_production,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False},
)

# ── Session Factory ──────────────────────────────────────────
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base Model ───────────────────────────────────────────────
class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


# ── WAL Mode for SQLite ─────────────────────────────────────
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and foreign keys for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# ── Dependency for FastAPI ───────────────────────────────────
async def get_db() -> AsyncSession:
    """
    Yield an async database session for use in FastAPI dependencies.
    Automatically closes when the request completes.
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Database Initialization ──────────────────────────────────
async def init_db():
    """Create all tables if they don't exist and run auto-migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Auto-migration for new Voice Biometrics columns
        columns = [
            "voice_registered BOOLEAN DEFAULT 0",
            "voice_embedding_encrypted BLOB",
            "voice_phrase_hash VARCHAR(512)",
            "voice_phrase_encrypted BLOB",
            "voice_phrase_iv BLOB",
            "spoof_detection_score FLOAT DEFAULT 1.0",
            "authentication_confidence_score FLOAT DEFAULT 1.0",
            "face_image_base64 TEXT",
            "voice_sample_blob BLOB"
        ]
        for col in columns:
            try:
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN {col}"))
            except Exception:
                pass # Column already exists


async def close_db():
    """Dispose engine on shutdown."""
    await engine.dispose()
