"""
SQLAlchemy async database setup for GBADS v2 (PostgreSQL).
"""
import logging
from urllib.parse import urlparse
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import get_settings
from models import Base

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        _engine = create_async_engine(db_url, echo=False)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def _sync_legacy_postgres_schema(engine) -> None:
    statements = [
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS feature_id VARCHAR",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS project_id VARCHAR",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS repo_path VARCHAR",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS feature_branch VARCHAR",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS pushed_at TIMESTAMP WITHOUT TIME ZONE",
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS push_commit_hash VARCHAR",
        "ALTER TABLE iterations ADD COLUMN IF NOT EXISTS commit_hash VARCHAR",
        "ALTER TABLE iterations ADD COLUMN IF NOT EXISTS diff TEXT",
        "ALTER TABLE iterations ADD COLUMN IF NOT EXISTS is_best BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE llm_calls ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'",
        # system_prompts — created by SQLAlchemy metadata but adding explicit sync for
        # environments that already have the schema without this table.
        """
        CREATE TABLE IF NOT EXISTS system_prompts (
            id          VARCHAR        PRIMARY KEY,
            name        VARCHAR(255)   NOT NULL UNIQUE,
            content     TEXT           NOT NULL,
            description TEXT,
            version     INTEGER        NOT NULL DEFAULT 1,
            is_active   BOOLEAN        NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_system_prompts_name ON system_prompts (name)",
        "CREATE INDEX IF NOT EXISTS ix_system_prompts_is_active ON system_prompts (is_active)",
    ]

    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))


async def init_db() -> None:
    """Create all tables and warm up the prompt cache."""
    engine = get_engine()
    settings = get_settings()
    parsed = urlparse(settings.database_url)
    logger.info(
        "Initializing database: dialect=postgresql host=%s db_name=%s",
        parsed.hostname or "unknown",
        parsed.path.lstrip("/") or "unknown",
    )
    await _sync_legacy_postgres_schema(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")

    # Load system prompts into the in-memory cache so agents can access them
    # synchronously without additional DB round-trips.
    from prompts.loader import PromptCache
    factory = get_session_factory()
    async with factory() as db:
        await PromptCache.load_all(db)


async def close_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for DB session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
