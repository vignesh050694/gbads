"""
Tool implementations for the Agentic CLI mode.
These are called when Claude invokes a tool during the agentic loop.
"""
import fnmatch
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Safety constraints ─────────────────────────────────────────────────────────

_BLOCKED_PATTERNS = [
    r"rm\s+-rf", r"rm\s+--rf",
    r"sudo\b",
    r":\(\)\s*\{.*\}", r"fork\s+bomb",
    r"git\s+push\s+(--force|-f)\b",
    r"git\s+reset\s+--hard\b",
    r"git\s+checkout\s+--\b",
    r">\s*/dev/",
    r"dd\s+if=",
    r"mkfs\b",
    r"shutdown\b",
    r"reboot\b",
    r"halt\b",
]
_BLOCKED_RE = re.compile("|".join(_BLOCKED_PATTERNS), re.IGNORECASE)

MAX_COMMAND_TIMEOUT = 30
MAX_FILE_READ_BYTES = 200_000
MAX_SEARCH_RESULTS = 50


# ── Tool definitions (Anthropic tool_use format) ───────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file at the given path (relative to working directory). "
            "Returns the file content as a string."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to working directory"},
                "start_line": {"type": "integer", "description": "Optional: 1-based start line"},
                "end_line": {"type": "integer", "description": "Optional: 1-based end line"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file at the given path (relative to working directory). "
            "Creates parent directories if needed. Overwrites existing content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to working directory"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "List files matching a glob pattern (relative to working directory). "
            "Examples: '**/*.py', 'src/*.ts', '*.json'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern"},
                "directory": {
                    "type": "string",
                    "description": "Directory to search in (default: working directory)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run a shell command in the working directory. Returns stdout, stderr, and return code. "
            "Safe for running tests (pytest, npm test), linters, compilers, etc. "
            "Timeout: 30 seconds. Blocked: rm -rf, sudo, force-push, destructive git ops."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_code",
        "description": (
            "Search for a pattern in source files using regex. "
            "Returns matching lines with file paths and line numbers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex search pattern"},
                "path": {
                    "type": "string",
                    "description": "Directory or file to search (default: working directory)",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob to filter files, e.g. '*.py' (default: all files)",
                },
            },
            "required": ["pattern"],
        },
    },
]


# ── Tool executor ──────────────────────────────────────────────────────────────

class ToolExecutor:
    def __init__(self, working_dir: Path):
        self.working_dir = working_dir.resolve()
        self.files_written: list[str] = []
        self.files_read: list[str] = []

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Dispatch tool call and return result string."""
        try:
            if tool_name == "read_file":
                return self._read_file(**tool_input)
            elif tool_name == "write_file":
                return self._write_file(**tool_input)
            elif tool_name == "list_files":
                return self._list_files(**tool_input)
            elif tool_name == "run_command":
                return self._run_command(**tool_input)
            elif tool_name == "search_code":
                return self._search_code(**tool_input)
            else:
                return f"Error: unknown tool '{tool_name}'"
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            return f"Error: {exc}"

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to working_dir, validate it stays within."""
        resolved = (self.working_dir / path).resolve()
        if not str(resolved).startswith(str(self.working_dir)):
            raise ValueError(f"Path escapes working directory: {path}")
        return resolved

    def _read_file(self, path: str, start_line: int = None, end_line: int = None) -> str:
        full_path = self._resolve_path(path)
        if not full_path.exists():
            return f"Error: file not found: {path}"

        content = full_path.read_bytes()[:MAX_FILE_READ_BYTES].decode("utf-8", errors="replace")
        self.files_read.append(path)

        if start_line or end_line:
            lines = content.splitlines()
            s = (start_line or 1) - 1
            e = end_line or len(lines)
            content = "\n".join(lines[s:e])

        return content

    def _write_file(self, path: str, content: str) -> str:
        full_path = self._resolve_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        existed = full_path.exists()
        full_path.write_text(content, encoding="utf-8")

        self.files_written.append(path)
        action = "updated" if existed else "created"
        return f"File {action}: {path} ({len(content.splitlines())} lines)"

    def _list_files(self, pattern: str, directory: str = None) -> str:
        base = self._resolve_path(directory) if directory else self.working_dir
        if not base.exists():
            return f"Error: directory not found: {directory}"

        matches = []
        for p in base.rglob("*"):
            if p.is_file() and fnmatch.fnmatch(p.name, pattern.split("/")[-1]):
                rel = str(p.relative_to(self.working_dir))
                matches.append(rel)
            if len(matches) >= 200:
                break

        # Also try glob from base
        try:
            glob_matches = list(base.glob(pattern))
            for p in glob_matches:
                rel = str(p.relative_to(self.working_dir))
                if rel not in matches:
                    matches.append(rel)
        except Exception:
            pass

        if not matches:
            return f"No files found matching: {pattern}"
        return "\n".join(sorted(set(matches))[:100])

    def _run_command(self, command: str) -> str:
        # Safety check
        if _BLOCKED_RE.search(command):
            return f"Error: command blocked for safety: {command}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=MAX_COMMAND_TIMEOUT,
            )
            output = ""
            if result.stdout:
                output += result.stdout[-5000:]  # last 5000 chars
            if result.stderr:
                output += "\n[stderr]\n" + result.stderr[-2000:]
            output += f"\n[exit code: {result.returncode}]"
            return output.strip()
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {MAX_COMMAND_TIMEOUT}s"

    def _search_code(
        self,
        pattern: str,
        path: str = None,
        file_pattern: str = None,
    ) -> str:
        search_dir = self._resolve_path(path) if path else self.working_dir
        results = []
        count = 0

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            return f"Error: invalid regex pattern: {exc}"

        for file_path in search_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_pattern and not fnmatch.fnmatch(file_path.name, file_pattern):
                continue
            # Skip binary-like files
            if file_path.suffix in {".pyc", ".pyo", ".so", ".dll", ".exe", ".jpg", ".png", ".gif"}:
                continue
            try:
                for line_num, line in enumerate(
                    file_path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
                ):
                    if regex.search(line):
                        rel = str(file_path.relative_to(self.working_dir))
                        results.append(f"{rel}:{line_num}: {line.strip()}")
                        count += 1
                        if count >= MAX_SEARCH_RESULTS:
                            results.append(f"... (truncated at {MAX_SEARCH_RESULTS} results)")
                            return "\n".join(results)
            except Exception:
                continue

        if not results:
            return f"No matches found for pattern: {pattern}"
        return "\n".join(results)
