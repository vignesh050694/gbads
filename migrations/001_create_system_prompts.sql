-- Migration 001: Create system_prompts table
-- Run this against the PostgreSQL database before starting the application.
-- This script is idempotent (safe to run multiple times).

CREATE TABLE IF NOT EXISTS system_prompts (
    id          VARCHAR        PRIMARY KEY,
    name        VARCHAR(255)   NOT NULL UNIQUE,
    content     TEXT           NOT NULL,
    description TEXT,
    version     INTEGER        NOT NULL DEFAULT 1,
    is_active   BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

-- Index for fast lookup by name
CREATE INDEX IF NOT EXISTS ix_system_prompts_name ON system_prompts (name);
-- Index for filtering active prompts
CREATE INDEX IF NOT EXISTS ix_system_prompts_is_active ON system_prompts (is_active);
