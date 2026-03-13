import json
import uuid
import logging
from typing import Any, Optional

import asyncpg

from config import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None

CREATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  UUID PRIMARY KEY,
    module_name TEXT NOT NULL,
    requirement TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status      TEXT NOT NULL DEFAULT 'running',
    best_score  FLOAT,
    best_iteration INT
);

CREATE TABLE IF NOT EXISTS iterations (
    iteration_id     UUID PRIMARY KEY,
    session_id       UUID NOT NULL REFERENCES sessions(session_id),
    iteration_number INT  NOT NULL,
    score            FLOAT NOT NULL,
    passed           INT  NOT NULL,
    failed           INT  NOT NULL,
    total            INT  NOT NULL,
    code             TEXT NOT NULL,
    result_json      JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id           UUID PRIMARY KEY,
    session_id        UUID NOT NULL REFERENCES sessions(session_id),
    iteration_number  INT,
    prompt_tokens     INT  NOT NULL,
    completion_tokens INT  NOT NULL,
    duration_ms       INT  NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def init_pool() -> None:
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute(CREATE_SCHEMA)
    logger.info("Database pool initialized")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")
    return _pool


async def create_session(module_name: str, requirement: str) -> str:
    session_id = str(uuid.uuid4())
    async with _get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (session_id, module_name, requirement) VALUES ($1, $2, $3)",
            uuid.UUID(session_id),
            module_name,
            requirement,
        )
    return session_id


async def update_session_status(
    session_id: str,
    status: str,
    best_score: Optional[float] = None,
    best_iteration: Optional[int] = None,
) -> None:
    async with _get_pool().acquire() as conn:
        await conn.execute(
            """UPDATE sessions
               SET status=$2, best_score=$3, best_iteration=$4
               WHERE session_id=$1""",
            uuid.UUID(session_id),
            status,
            best_score,
            best_iteration,
        )


async def save_iteration(
    session_id: str,
    iteration_number: int,
    score: float,
    passed: int,
    failed: int,
    total: int,
    code: str,
    result_json: dict,
) -> None:
    iteration_id = str(uuid.uuid4())
    async with _get_pool().acquire() as conn:
        await conn.execute(
            """INSERT INTO iterations
               (iteration_id, session_id, iteration_number, score, passed, failed, total, code, result_json)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            uuid.UUID(iteration_id),
            uuid.UUID(session_id),
            iteration_number,
            score,
            passed,
            failed,
            total,
            code,
            json.dumps(result_json),
        )


async def log_llm_call(
    session_id: str,
    iteration_number: Optional[int],
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: int,
) -> None:
    call_id = str(uuid.uuid4())
    async with _get_pool().acquire() as conn:
        await conn.execute(
            """INSERT INTO llm_calls
               (call_id, session_id, iteration_number, prompt_tokens, completion_tokens, duration_ms)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            uuid.UUID(call_id),
            uuid.UUID(session_id),
            iteration_number,
            prompt_tokens,
            completion_tokens,
            duration_ms,
        )


async def get_session(session_id: str) -> Optional[dict]:
    async with _get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM sessions WHERE session_id=$1",
            uuid.UUID(session_id),
        )
    return dict(row) if row else None


async def get_iterations(session_id: str) -> list[dict]:
    async with _get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM iterations WHERE session_id=$1 ORDER BY iteration_number",
            uuid.UUID(session_id),
        )
    return [dict(r) for r in rows]


async def get_best_iteration(session_id: str) -> Optional[dict]:
    async with _get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM iterations WHERE session_id=$1 ORDER BY score DESC, iteration_number ASC LIMIT 1",
            uuid.UUID(session_id),
        )
    return dict(row) if row else None
