"""
Git operations for GBADS v2.
Handles clone, branch, commit, push for project repositories.
"""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import git
from git import Repo

logger = logging.getLogger(__name__)

# Files to exclude from the repo file tree
_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv", ".env"}
_EXCLUDE_EXTS = {".pyc", ".pyo", ".class", ".o", ".so", ".dll"}

# Key files to read for codebase context
_KEY_FILE_NAMES = {
    "package.json", "requirements.txt", "pyproject.toml", "go.mod",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "README.md", "config.py", "settings.py", "app.py", "main.py",
    "index.js", "server.js", ".env.example", ".env.sample",
}


# ── CLONE ──────────────────────────────────────────────────────────────────────

async def clone_repo(
    project_repo_id: str,
    github_url: str,
    user_access_token: str,
    local_path: str,
    db_update_fn=None,
) -> str:
    """
    Clone a GitHub repository to local_path using an authenticated URL.
    Returns the default branch name.
    """
    local = Path(local_path)
    local.mkdir(parents=True, exist_ok=True)

    # Build authenticated URL: https://{token}@github.com/{owner}/{repo}.git
    parsed = urlparse(github_url)
    auth_url = f"https://{user_access_token}@{parsed.netloc}{parsed.path}"
    if not auth_url.endswith(".git"):
        auth_url += ".git"

    if db_update_fn:
        await db_update_fn(project_repo_id, "CLONING")

    try:
        repo = Repo.clone_from(auth_url, str(local), timeout=180)
        default_branch = repo.active_branch.name
        cloned_at = datetime.now(timezone.utc)

        if db_update_fn:
            await db_update_fn(project_repo_id, "DONE", default_branch=default_branch, cloned_at=cloned_at)

        logger.info("Cloned %s → %s (branch: %s)", github_url, local_path, default_branch)
        return default_branch

    except Exception as exc:
        logger.error("Clone failed for %s: %s", github_url, exc)
        if db_update_fn:
            await db_update_fn(project_repo_id, "FAILED", clone_error=str(exc))
        raise


def get_repo_file_tree(local_path: str, max_depth: int = 4) -> list[str]:
    """
    Walk the repo and return relative file paths.
    Excludes .git, node_modules, __pycache__, etc. Capped at 500 files.
    """
    root = Path(local_path)
    paths = []

    for path in root.rglob("*"):
        if len(paths) >= 500:
            break
        if path.is_dir():
            continue
        # Check if any parent dir is excluded
        rel = path.relative_to(root)
        parts = rel.parts
        if any(p in _EXCLUDE_DIRS for p in parts):
            continue
        # Check depth
        if len(parts) > max_depth:
            continue
        # Check extension
        if path.suffix in _EXCLUDE_EXTS:
            continue
        paths.append(str(rel))

    return sorted(paths)


def read_key_files(local_path: str, max_lines: int = 200) -> dict[str, str]:
    """
    Read content of key configuration/entry-point files.
    Returns {relative_path: content}, each capped at max_lines lines.
    """
    root = Path(local_path)
    result = {}

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if any(p in _EXCLUDE_DIRS for p in parts):
            continue
        if path.name in _KEY_FILE_NAMES:
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                result[str(rel)] = "\n".join(lines[:max_lines])
            except Exception:
                pass

    return result


# ── BRANCH ─────────────────────────────────────────────────────────────────────

def create_feature_branch(local_path: str, session_id: str) -> str:
    """
    Create and checkout a feature branch from the default branch.
    Returns the branch name.
    """
    branch_name = f"feature/{session_id}"
    repo = Repo(local_path)
    repo.git.checkout("-b", branch_name)
    logger.info("Created feature branch: %s", branch_name)
    return branch_name


# ── WRITE + COMMIT ─────────────────────────────────────────────────────────────

def write_generated_code_to_repo(local_path: str, target_file: str, code: str) -> None:
    """
    Write generated code to {local_path}/{target_file}.
    Validates that target_file stays within local_path.
    """
    root = Path(local_path).resolve()
    dest = (root / target_file).resolve()

    # Security: never write outside the repo root
    if not str(dest).startswith(str(root)):
        raise ValueError(f"target_file escapes repo root: {target_file}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(code, encoding="utf-8")
    logger.info("Wrote generated code to %s", dest)


def commit_iteration(
    local_path: str,
    session_id: str,
    iteration_number: int,
    score: float,
    passed: int,
    total: int,
) -> tuple[str, str]:
    """
    git add -A and commit with standard message.
    Returns (commit_hash, diff_string).
    """
    repo = Repo(local_path)
    repo.git.add("-A")

    msg = (
        f"gbads: iter-{iteration_number} score={score:.2f} "
        f"passed={passed}/{total} [session:{session_id[:8]}]"
    )
    commit = repo.index.commit(msg)
    diff = get_diff_from_previous(local_path)
    return commit.hexsha, diff


def get_diff_from_previous(local_path: str) -> str:
    """git diff HEAD~1 HEAD. If first commit, diff against empty tree."""
    repo = Repo(local_path)
    try:
        return repo.git.diff("HEAD~1", "HEAD")
    except git.GitCommandError:
        # First commit — diff against empty tree
        return repo.git.show("HEAD", "--stat")


def summarize_diff(diff: str) -> str:
    """One-liner: '+N lines, -M lines'"""
    added = diff.count("\n+") - diff.count("\n+++")
    removed = diff.count("\n-") - diff.count("\n---")
    return f"+{added} lines, -{removed} lines"


# ── PUSH ───────────────────────────────────────────────────────────────────────

def reset_to_best_iteration(local_path: str, best_commit_hash: str) -> None:
    """Rewind feature branch to the best iteration's commit."""
    repo = Repo(local_path)
    repo.git.reset("--hard", best_commit_hash)
    logger.info("Reset to best commit: %s", best_commit_hash[:8])


def push_feature_branch(
    local_path: str,
    branch_name: str,
    user_access_token: str,
) -> str:
    """
    Push feature branch to GitHub. Only pushes feature/* branches.
    Clears token from remote URL immediately after push.
    """
    if not branch_name.startswith("feature/"):
        raise ValueError(f"Will only push to feature/* branches, got: {branch_name}")

    repo = Repo(local_path)

    # Get current remote URL and build authenticated version
    origin_url = repo.remotes.origin.url
    parsed = urlparse(origin_url.replace("https://", ""))
    # Strip any existing token from URL
    netloc = parsed.netloc.split("@")[-1]
    auth_url = f"https://{user_access_token}@{netloc}{parsed.path}"

    try:
        repo.remotes.origin.set_url(auth_url)
        repo.git.push("origin", branch_name, "--force-with-lease")
        logger.info("Pushed %s to origin", branch_name)
    finally:
        # Always clear the token from the remote URL
        clean_url = f"https://{netloc}{parsed.path}"
        repo.remotes.origin.set_url(clean_url)

    return branch_name


def get_git_log(local_path: str, branch: Optional[str] = None) -> list[dict]:
    """Return commits as list of dicts."""
    repo = Repo(local_path)
    ref = branch or repo.active_branch.name
    commits = []
    for commit in repo.iter_commits(ref, max_count=50):
        commits.append({
            "hash": commit.hexsha,
            "short_hash": commit.hexsha[:8],
            "message": commit.message.strip(),
            "date": str(commit.committed_datetime),
        })
    return commits
