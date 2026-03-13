"""
PromptCache — loads system prompts from the database at startup and serves
them synchronously from an in-memory cache.

Usage:
    # At startup (inside an async context with a DB session):
    await PromptCache.load_all(db_session)

    # In agents / anywhere:
    system = PromptCache.get("interceptor_system", fallback=INTERCEPTOR_SYSTEM)
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


class PromptCache:
    """In-memory cache for system prompts loaded from PostgreSQL.

    The cache is populated once at application startup by calling
    ``await PromptCache.load_all(db)``.  After that all lookups are
    synchronous O(1) dict reads with an optional hardcoded fallback,
    so agents never block on I/O just to retrieve a prompt.
    """

    _cache: dict[str, str] = {}

    @classmethod
    async def load_all(cls, db: AsyncSession) -> None:
        """Bulk-load all active prompts from the database into the cache.

        Safe to call multiple times — subsequent calls refresh the cache.
        """
        from models import SystemPrompt  # local import to avoid circular deps

        try:
            result = await db.execute(
                select(SystemPrompt).where(SystemPrompt.is_active.is_(True))
            )
            rows = result.scalars().all()
            cls._cache = {row.name: row.content for row in rows}
            logger.info(
                "PromptCache: loaded %d system prompt(s) from database",
                len(cls._cache),
            )
        except Exception as exc:
            # Non-fatal: fall back to hardcoded defaults for all prompts
            logger.warning(
                "PromptCache: failed to load prompts from database (%s) — "
                "agents will use hardcoded defaults",
                exc,
            )
            cls._cache = {}

    @classmethod
    def get(cls, name: str, fallback: str = "") -> str:
        """Return the cached prompt for *name*, or *fallback* if not found.

        Args:
            name:     Prompt key, e.g. ``"interceptor_system"``.
            fallback: Hardcoded default to use when the DB cache is empty
                      or the key is missing.  Always pass the original
                      constant so the system degrades gracefully.
        """
        return cls._cache.get(name, fallback)

    @classmethod
    def is_loaded(cls) -> bool:
        """Return True if the cache has been populated at least once."""
        return bool(cls._cache)

    @classmethod
    def clear(cls) -> None:
        """Clear the cache (useful in tests)."""
        cls._cache = {}
