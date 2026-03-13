"""
GBADSState — the shared state passed between all LangGraph workflow nodes.

Every field is Optional-safe so that the workflow can start with a minimal
initial state and each node enriches it as it runs.
"""
from typing import Optional
from typing_extensions import TypedDict


class GBADSState(TypedDict):
    # ── Identity ────────────────────────────────────────────────────────────
    correlation_id: str        # Propagated to all logs inside nodes
    feature_id: str
    session_id: str
    project_id: str
    access_token: str          # GitHub token for pushing the branch

    # ── Input data ──────────────────────────────────────────────────────────
    spec: dict                 # Module spec produced by InterceptorAgent
    suite_dict: list           # Serialised list of test-case dicts

    # ── Loop counters ────────────────────────────────────────────────────────
    iteration_number: int      # Current iteration (incremented at start of generate_code)
    max_iterations: int
    target_score: float

    # ── Generated artefacts (transient — updated every iteration) ───────────
    generated_code: Optional[str]
    target_file: Optional[str]
    sandbox_result: Optional[dict]

    # ── Best-result tracking ─────────────────────────────────────────────────
    best_score: float
    best_commit_hash: Optional[str]
    best_iteration_entry: Optional[dict]
    history: list              # list[dict] — one entry per completed iteration

    # ── Repo / infra context ────────────────────────────────────────────────
    local_path: Optional[str]
    branch_name: Optional[str]
    repo_context: Optional[dict]   # Populated by setup_context node
    compose_result: dict

    # ── Error handling ───────────────────────────────────────────────────────
    error: Optional[str]
