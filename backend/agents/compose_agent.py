"""
Compose Agent: AI generates docker-compose.yml for sandbox testing.
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

from llm.client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Docker infrastructure expert. Analyze the provided codebase and write a complete,
production-ready docker-compose.yml for a testing sandbox environment.

Your compose file must:
1. Include ALL external services the app depends on (databases, queues, caches, etc.)
2. Add healthchecks on every service
3. Match service versions to client library versions in requirements.txt / package.json
   (e.g. confluent-kafka==2.3.0 → use bitnami/kafka:3.5)
4. Use the SAME env var names the app expects
   (detect from .env.example, config.py, settings.py)
5. Include a 'test-runner' service that:
   - depends_on all infra with condition: service_healthy
   - mounts /sandbox/module and /sandbox/tests (read-only)
   - command: python /sandbox/tests/test_runner.py
   - has all connection env vars injected

Rules:
- Use KRaft mode for Kafka (no Zookeeper)
- Pin versions — never use 'latest'
- Alpine variants preferred
- restart: no on all services
- No named volumes — ephemeral only (tmpfs or anonymous)

Return format — YAML comment first, then compose:
# META: {"services": ["mongodb","kafka"], "env_vars": {"MONGO_URL": "...", ...}, "detected_stack": {"language":"python","frameworks":["fastapi"],"databases":["mongodb"],"queues":["kafka"]}}
version: '3.8'
services:
  ..."""


async def generate_compose(
    file_tree: list[str],
    key_files: dict[str, str],
) -> dict:
    """
    Call Claude to generate docker-compose.yml.
    Returns dict with compose_yaml, detected_stack, services, env_vars, needs_infra.
    """
    llm = LLMClient()

    # Build user message
    tree_str = "\n".join(file_tree[:300])
    key_files_str = ""
    for path, content in list(key_files.items())[:15]:
        key_files_str += f"\n\n=== {path} ===\n{content}"

    user_msg = f"""Codebase file tree:
{tree_str}

Key files:{key_files_str}

Generate the docker-compose.yml for testing this codebase."""

    try:
        content, _, _ = await llm.complete(SYSTEM_PROMPT, user_msg)
    except Exception as exc:
        logger.error("Compose agent failed: %s", exc)
        return {
            "compose_yaml": None,
            "detected_stack": {},
            "services": [],
            "env_vars": {},
            "needs_infra": False,
        }

    # Parse META comment
    meta = {}
    compose_yaml = content
    meta_match = re.search(r"^#\s*META:\s*(\{.*\})", content, re.MULTILINE)
    if meta_match:
        try:
            meta = json.loads(meta_match.group(1))
        except json.JSONDecodeError:
            pass
        # Remove META line from compose
        compose_yaml = content[meta_match.end():].strip()

    services = meta.get("services", [])
    needs_infra = bool(services)

    return {
        "compose_yaml": compose_yaml if needs_infra else None,
        "detected_stack": meta.get("detected_stack", {}),
        "services": services,
        "env_vars": meta.get("env_vars", {}),
        "needs_infra": needs_infra,
    }


def save_compose_file(project_id: str, session_id: str, compose_yaml: str) -> str:
    """
    Write compose file to workspace/{project_id}/sandboxes/{session_id}/docker-compose.yml.
    Returns absolute path.
    """
    from config import get_settings
    settings = get_settings()
    sandbox_dir = settings.workspace_base / project_id / "sandboxes" / session_id
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    compose_path = sandbox_dir / "docker-compose.yml"
    compose_path.write_text(compose_yaml, encoding="utf-8")
    logger.info("Saved compose file to %s", compose_path)
    return str(compose_path)
