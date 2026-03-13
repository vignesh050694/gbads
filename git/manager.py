import logging
from pathlib import Path
from typing import Optional

import git as gitpython

logger = logging.getLogger(__name__)


class GitManager:
    def __init__(self, output_dir: Path, module_name: str):
        self._output_dir = output_dir
        self._module_name = module_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize git repo if not already one
        try:
            self._repo = gitpython.Repo(output_dir)
            logger.info("Using existing git repo at %s", output_dir)
        except gitpython.InvalidGitRepositoryError:
            self._repo = gitpython.Repo.init(output_dir)
            # Initial empty commit so HEAD exists
            self._repo.index.commit("init: gbads session")
            logger.info("Initialized new git repo at %s", output_dir)

    def _code_path(self) -> Path:
        return self._output_dir / f"{self._module_name}.py"

    def commit_iteration(
        self,
        iteration: int,
        score: float,
        passed: int,
        total: int,
        code: str,
        is_best: bool = False,
    ) -> str:
        """Write code to disk, commit, optionally tag as best. Returns commit sha."""
        code_path = self._code_path()
        code_path.write_text(code, encoding="utf-8")

        self._repo.index.add([str(code_path)])
        message = f"iter_{iteration} | score={score:.3f} | passed={passed}/{total} | {self._module_name}"
        commit = self._repo.index.commit(message)
        sha = commit.hexsha[:8]

        if is_best:
            tag_name = f"iter_{iteration}_best"
            # Delete existing tag if present (from an earlier equal-score iteration)
            existing = [t for t in self._repo.tags if t.name == tag_name]
            for t in existing:
                self._repo.delete_tag(t)
            self._repo.create_tag(tag_name, message=f"Best at iteration {iteration}, score={score:.3f}")
            logger.info("Tagged %s as %s", sha, tag_name)

        logger.info("Committed iteration %d: %s (score=%.3f)", iteration, sha, score)
        return sha

    def tag_head(self) -> None:
        """Tag the final selected head commit."""
        existing = [t for t in self._repo.tags if t.name == "head_selected"]
        for t in existing:
            self._repo.delete_tag(t)
        self._repo.create_tag(
            "head_selected",
            message="Final selected output",
        )
        logger.info("Tagged HEAD as head_selected")

    def get_diff(self, from_sha: Optional[str] = None, to_sha: Optional[str] = None) -> str:
        """Return unified diff between two commits (or last two commits if not specified)."""
        try:
            commits = list(self._repo.iter_commits(max_count=10))
            if len(commits) < 2:
                return ""
            if from_sha and to_sha:
                return self._repo.git.diff(from_sha, to_sha)
            # Default: diff last two commits
            return self._repo.git.diff(commits[1].hexsha, commits[0].hexsha)
        except Exception as exc:
            logger.warning("get_diff failed: %s", exc)
            return ""

    def get_session_log(self) -> str:
        """Return oneline git log for the session."""
        try:
            return self._repo.git.log("--oneline", "--decorate")
        except Exception as exc:
            logger.warning("get_session_log failed: %s", exc)
            return ""

    def get_diff_summary(self) -> str:
        """Return a short summary of the last commit diff (first 500 chars)."""
        diff = self.get_diff()
        if not diff:
            return ""
        lines = [l for l in diff.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
        summary = "\n".join(lines[:20])
        if len(lines) > 20:
            summary += f"\n... ({len(lines) - 20} more diff lines)"
        return summary
