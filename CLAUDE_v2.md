# Goal-Based Autonomous Development System (GBADS) — v2

## What Changed from v1

v1 built the core autonomous loop: requirement → benchmark → codegen → sandbox → iterate.

v2 adds:
1. **Project management** — projects own multiple features/sessions
2. **GitHub OAuth** — user authentication via GitHub (private repo scope)
3. **GitHub repo cloning** — projects attach to real codebases
4. **Codebase-aware code generation** — agent reads existing code before generating
5. **AI-generated docker-compose** — agent analyzes codebase and writes the compose file
6. **Metric approval gate** — user sees and approves the benchmark before the loop starts
7. **Feature branch push** — best iteration pushed to `feature/{session_id}` on GitHub, never main/develop
8. **Multi-repo provision** — data model supports microservices, MVP uses mono-repo

---

## Tech Stack (unchanged from v1, additions marked NEW)

- **Backend**: Python (FastAPI)
- **Agent / LLM**: Anthropic Claude API (`claude-sonnet-4-6`)
- **Sandbox**: Docker (Python SDK)
- **Version Control**: GitPython — clone, branch, commit, push to feature branch (**updated**)
- **Database**: SQLite (SQLAlchemy)
- **Frontend**: React + Tailwind CSS
- **Auth**: GitHub OAuth 2.0 — `httpx` for token exchange (**NEW**)
- **Git clone**: GitPython + `git.Repo.clone_from()` (**NEW**)

---

## Environment Variables

```bash
# Existing
ANTHROPIC_API_KEY=
GBADS_MAX_ITERATIONS=10
GBADS_HARD_CEILING=50
GBADS_TARGET_SCORE=1.0
GBADS_SANDBOX_TIMEOUT=30
GBADS_OUTPUT_DIR=./output
GBADS_DB_PATH=./gbads.db

# New in v2
GITHUB_CLIENT_ID=           # from GitHub OAuth App settings
GITHUB_CLIENT_SECRET=       # from GitHub OAuth App settings
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback
JWT_SECRET_KEY=             # random secret for signing session JWTs
JWT_EXPIRE_HOURS=72
WORKSPACE_BASE=./workspace  # where cloned repos live locally
```

---

## Updated Project Structure

```
gbads/
├── CLAUDE.md
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── models.py
│   ├── database.py
│   ├── auth/
│   │   ├── github.py                ← OAuth flow, token exchange (NEW)
│   │   └── middleware.py            ← JWT verify dependency (NEW)
│   ├── agents/
│   │   ├── interceptor.py           ← codebase-aware (updated)
│   │   ├── benchmark.py             ← metric approval plan (updated)
│   │   ├── codegen.py               ← codebase-aware, outputs TARGET_FILE (updated)
│   │   └── compose_agent.py         ← AI writes docker-compose (NEW)
│   ├── runner/
│   │   ├── sandbox.py               ← compose-based execution (updated)
│   │   ├── scorer.py                ← unchanged
│   │   └── loop.py                  ← feature branch push on completion (updated)
│   ├── git_manager.py               ← clone, branch, commit, push (updated)
│   └── routers/
│       ├── auth.py                  ← GitHub OAuth routes (NEW)
│       ├── projects.py              ← project CRUD (NEW)
│       ├── features.py              ← feature lifecycle (NEW)
│       ├── sessions.py              ← updated
│       ├── requirements.py          ← metric approval gate (updated)
│       └── iterations.py            ← unchanged
├── frontend/
│   └── App.jsx
├── sandbox_base/
│   └── Dockerfile
├── workspace/                       ← cloned repos live here
│   └── {project_id}/
│       ├── {repo_name}/             ← full cloned repo (working copy)
│       └── sandboxes/
│           └── {session_id}/        ← compose file + test runner scratch space
└── docker-compose.yml               ← system compose (not sandbox compose)
```

---

## Data Models (`backend/models.py`)

Add these to v1's `Session`, `Iteration`, `TestCase`:

### User (NEW)
```
User
  - id: UUID (primary key)
  - github_id: str (unique)
  - github_username: str
  - github_email: str
  - github_access_token: str        ← Fernet-encrypted before storing
  - avatar_url: str
  - created_at: datetime
  - last_login: datetime
```

### Project (NEW)
```
Project
  - id: UUID (primary key)
  - user_id: UUID FK → User
  - name: str
  - description: str
  - created_at: datetime
  - status: enum [ACTIVE, ARCHIVED]
  - repo_structure: enum [MONO, MULTI, MICROSERVICES]  ← MVP always MONO
  - detected_stack: JSON            ← populated by compose agent after clone
  - generated_compose: str          ← full docker-compose YAML from AI agent
```

### ProjectRepo (NEW)
```
ProjectRepo
  - id: UUID (primary key)
  - project_id: UUID FK → Project
  - github_url: str
  - repo_name: str
  - local_path: str                 ← absolute path to cloned repo
  - clone_status: enum [PENDING, CLONING, DONE, FAILED]
  - clone_error: str (nullable)
  - default_branch: str             ← detected on clone (main or master)
  - cloned_at: datetime
  - role: enum [PRIMARY, SERVICE]   ← future multi-repo support
```

### Feature (NEW)
```
Feature
  - id: UUID (primary key)
  - project_id: UUID FK → Project
  - title: str
  - raw_requirement: str
  - status: enum [
      INTERCEPTING,
      AWAITING_CLARIFICATION,
      AWAITING_METRIC_APPROVAL,
      RUNNING,
      DONE,
      PARTIAL,
      CANCELLED
    ]
  - module_spec: JSON
  - benchmark_plan: JSON            ← shown to user before approval
  - approved_at: datetime           ← null until user approves
  - feature_branch: str             ← "feature/{session_id}"
  - pr_url: str (nullable)          ← GitHub PR URL (future)
  - created_at: datetime
  - session_id: UUID FK → Session (nullable until loop starts)
```

### Session model (updated fields)
```
Session
  - feature_id: UUID FK → Feature   (NEW)
  - project_id: UUID FK → Project   (NEW)
  - repo_path: str                   (NEW)
  - feature_branch: str              (NEW)
  - pushed_at: datetime (nullable)   (NEW)
  - push_commit_hash: str (nullable) (NEW)
```

---

## New Components

---

### 1. GitHub OAuth (`backend/auth/github.py`)

**Scope must be `repo`** — private repos are the primary use case (90%+). This gives read/write which is needed for cloning private repos AND pushing feature branches back.

```python
GITHUB_SCOPES = "read:user user:email repo"
```

**OAuth flow**:
```
GET /auth/github
  → RedirectResponse to GitHub authorize URL with repo scope

GET /auth/github/callback?code=XXX
  1. POST github.com/login/oauth/access_token  → access_token
  2. GET  api.github.com/user                  → profile
  3. Upsert User (encrypt token with Fernet)
  4. Create signed JWT
  5. RedirectResponse("http://localhost:3000?token={jwt}")
```

```python
# backend/auth/github.py

# Fernet key: derive at startup from JWT_SECRET_KEY using SHA-256
# fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(JWT_SECRET_KEY.encode()).digest()))

def encrypt_token(token: str) -> str: ...
def decrypt_token(encrypted: str) -> str: ...

def get_oauth_redirect_url() -> str:
    """Build GitHub authorize URL with repo scope"""

async def exchange_code_for_token(code: str) -> str:
    """POST to GitHub token endpoint, return plain access_token"""

async def fetch_github_user(access_token: str) -> dict:
    """GET api.github.com/user"""

async def upsert_user(github_profile: dict, access_token: str) -> User:
    """Create or update User. Fernet-encrypt access_token before storing."""

def create_jwt(user_id: str) -> str:
    """HS256, exp = now + JWT_EXPIRE_HOURS"""

def verify_jwt(token: str) -> dict:
    """Raise HTTPException 401 on failure"""
```

**Auth middleware** (`backend/auth/middleware.py`):
```python
async def get_current_user(authorization: str = Header(...)) -> User:
    """
    Expect: Authorization: Bearer {jwt}
    Verify JWT → user_id → load User from DB → return User
    Raise 401 if anything fails
    """
```

**All project / feature / session routes must `Depends(get_current_user)`**

---

### 2. Project API (`backend/routers/projects.py`)

```
POST /projects
  Auth: required
  Body: {
    "name": str,
    "description": str,
    "github_urls": ["https://github.com/org/repo"],
    "repo_structure": "MONO"
  }
  Validation: if len(github_urls) > 1 or repo_structure != "MONO" → 400
  Response: { "project_id": uuid, "status": "CLONING", "repos": [...] }

  Background task on create:
    1. clone_repo() for each URL using user's decrypted access_token
    2. get_repo_file_tree() + read_key_files()
    3. compose_agent.generate_compose(file_tree, key_files)
    4. Save project.generated_compose + project.detected_stack

GET /projects                    → user's projects list
GET /projects/{project_id}       → full project + repos + features
DELETE /projects/{project_id}    → soft delete (ARCHIVED)
```

---

### 3. Git Manager (`backend/git_manager.py`) — fully updated

```python
# ── CLONE ──────────────────────────────────────────────────────────────────────

async def clone_repo(project_repo_id, github_url, user_access_token, local_path):
    """
    Auth URL: https://{access_token}@github.com/{owner}/{repo}.git
    Full clone (depth=None) — needed for branch operations.
    Detect default branch after clone: repo.active_branch.name
    Timeout: 180s
    Updates ProjectRepo.clone_status in DB.
    """

def get_repo_file_tree(local_path, max_depth=4) -> list[str]:
    """
    Walk repo, return relative paths.
    Exclude: .git/ node_modules/ __pycache__/ .env *.pyc dist/ build/
    Cap at 500 files.
    """

def read_key_files(local_path) -> dict[str, str]:
    """
    Read and return content of: package.json, requirements.txt, pyproject.toml,
    go.mod, Dockerfile, docker-compose.yml (if exists), README.md (80 lines),
    config.py, settings.py, app.py, main.py, index.js, server.js,
    .env.example, .env.sample
    Cap each at 200 lines. Returns {relative_path: content}.
    """

# ── BRANCH ─────────────────────────────────────────────────────────────────────

def create_feature_branch(local_path, session_id) -> str:
    """
    branch_name = f"feature/{session_id}"
    Checkout from default branch.
    repo.git.checkout('-b', branch_name)
    Local only — no push yet.
    Returns branch_name.
    """

# ── COMMIT ─────────────────────────────────────────────────────────────────────

def write_generated_code_to_repo(local_path, target_file, code):
    """
    Write code to {local_path}/{target_file}.
    Create parent directories if needed.
    Never write outside local_path (validate path).
    target_file comes from codegen agent's TARGET_FILE: header.
    """

def commit_iteration(local_path, session_id, iteration_number, score, passed, total):
    """
    git add -A
    commit message: "gbads: iter-{N} score={score:.2f} passed={passed}/{total} [session:{session_id}]"
    Returns (commit_hash, diff_string).
    Local only.
    """

def get_diff_from_previous(local_path) -> str:
    """git diff HEAD~1 HEAD. If first commit, diff against empty tree."""

def summarize_diff(diff) -> str:
    """One-liner: '+N lines, -M lines, modified: fn1(), fn2()'"""

# ── PUSH ───────────────────────────────────────────────────────────────────────

def reset_to_best_iteration(local_path, best_commit_hash):
    """
    git reset --hard {best_commit_hash}
    Rewinds feature branch to best iteration before push.
    """

def push_feature_branch(local_path, branch_name, user_access_token):
    """
    GUARD: if not branch_name.startswith("feature/"):
        raise ValueError("Will only push to feature/* branches")

    Set authenticated remote URL:
      repo.remotes.origin.set_url(f"https://{access_token}@github.com/{owner}/{repo}.git")

    Push:
      repo.git.push('origin', branch_name, '--force-with-lease')

    Immediately reset remote URL to non-authenticated form:
      repo.remotes.origin.set_url(f"https://github.com/{owner}/{repo}.git")
      # Never leave token in git config

    Returns pushed branch name.
    """

def get_git_log(local_path, branch) -> list[dict]:
    """Commits on branch as list of {hash, short_hash, message, score, date}"""
```

---

### 4. Compose Agent (`backend/agents/compose_agent.py`)

**AI writes the entire docker-compose.yml** — not templates. This allows the agent to match library versions, use existing env var names, and handle edge cases like Kafka needing specific client compatibility.

```
System Prompt:

You are a Docker infrastructure expert. Analyze the provided codebase and write a complete,
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
  ...
```

```python
async def generate_compose(file_tree: list[str], key_files: dict[str, str]) -> dict:
    """
    Call Claude with system prompt above.
    Parse response:
      - Extract # META: comment → detected_stack, services, env_vars
      - Full YAML string (everything after the comment line)

    Returns:
    {
      "compose_yaml": str,
      "detected_stack": dict,
      "services": list[str],
      "env_vars": dict,
      "needs_infra": bool   ← False if no external services found
    }

    If no services detected: needs_infra=False, compose_yaml=None
    → v1 single-container sandbox will be used instead
    """

def save_compose_file(project_id, session_id, compose_yaml) -> str:
    """
    Write to workspace/{project_id}/sandboxes/{session_id}/docker-compose.yml
    Returns absolute path.
    This directory is sandbox scratch — separate from the cloned repo.
    """
```

---

### 5. Updated Sandbox Executor (`backend/runner/sandbox.py`)

```python
def run_in_sandbox(generated_code, test_cases, session_id, project_id, compose_result) -> dict:
    """
    if compose_result["needs_infra"]:
        prepare_sandbox_files(...)        # write code + test runner to scratch dir
        run_compose_sandbox(compose_path, timeout=120)
    else:
        run v1 single-container (network_mode=none, timeout=30)
    """

def prepare_sandbox_files(session_id, project_id, generated_code, test_cases, env_vars) -> str:
    """
    Write to workspace/{project_id}/sandboxes/{session_id}/:
      module.py         ← generated code
      test_cases.json   ← benchmark
      test_runner.py    ← fixed test runner (same as v1)

    The docker-compose test-runner service mounts this directory.
    Returns path to sandbox scratch dir.
    """

def run_compose_sandbox(compose_path, timeout=120) -> dict:
    """
    subprocess.run([
        "docker", "compose", "-f", compose_path,
        "up", "--abort-on-container-exit", "--exit-code-from", "test-runner"
    ], timeout=timeout, capture_output=True)

    finally:  # always cleanup
        subprocess.run(["docker", "compose", "-f", compose_path, "down", "-v", "--remove-orphans"])

    Parse test-runner logs as JSON.
    On timeout: kill compose, run down -v, return {error: "timeout", passed: 0}
    """
```

---

### 6. Metric Approval Gate

**Plan generation** (runs after interceptor completes):

```python
# backend/agents/benchmark.py — NEW function

async def generate_metric_plan(module_spec, user_examples, repo_context=None, compose_result=None) -> dict:
    """
    Return human-readable plan BEFORE generating test cases.
    User must approve this. Loop must not start without approval.

    Output:
    {
      "metric": "Test case pass rate",
      "formula": "passed_cases / total_cases",
      "target": "1.0 (100%)",
      "planned_test_cases": {
        "happy_path": { "count": 3, "examples": ["Valid login returns JWT", ...] },
        "security":   { "count": 4, "examples": ["SQL injection rejected", ...] },
        "boundary":   { "count": 3, "examples": ["Password exactly 8 chars", ...] },
        "null_input": { "count": 3, "examples": ["Missing email field", ...] },
        "edge_case":  { "count": 2, "examples": ["Unicode in password", ...] }
      },
      "total_planned": 15,
      "real_infra_testing": true,
      "infra_services": ["mongodb", "kafka"],
      "infra_note": "Tests will perform actual MongoDB writes and Kafka publishes",
      "success_definition": "All 15 tests pass against real running services",
      "estimated_seconds_per_iteration": 90
    }
    """
```

**API endpoints** (`backend/routers/requirements.py`):

```
POST /requirements/metric-plan
  Auth: required
  Body: { "feature_id": uuid }
  Action:
    Verify feature.module_spec exists
    Call generate_metric_plan()
    Save to feature.benchmark_plan
    Set feature.status = AWAITING_METRIC_APPROVAL
  Response: metric_plan dict

POST /requirements/approve-metric
  Auth: required
  Body: { "feature_id": uuid, "approved": true }
  Action:
    Set feature.approved_at = utcnow()
    Background: generate full test cases → create Session → run loop
    Set feature.status = RUNNING
  Response: { "status": "RUNNING", "feature_branch": "feature/{session_id}" }
```

---

### 7. Updated Codegen Agent (`backend/agents/codegen.py`)

Agent must output `TARGET_FILE:` header so the system knows where in the repo to write the code:

**System prompt addition**:
```
You are modifying an existing codebase. Study the existing structure carefully and follow
its exact patterns — directory layout, import style, naming conventions, error handling.

Your response MUST start with:
TARGET_FILE: {relative/path/to/file.py}
---
{code here}

Choose the TARGET_FILE path to fit naturally into the existing structure.
If adding a new feature, follow where similar features live.
If modifying an existing file, use its exact current path.
Use the following env vars for service connections: {connection_env_vars}
The test runner will import your module as: from module import execute
So your TARGET_FILE must expose an execute(input_data: dict) -> dict function.
```

```python
async def generate_code(
    module_spec, test_cases, iteration_number,
    previous_iterations, current_best,
    repo_context=None, connection_env_vars=None
) -> tuple[str, str, int]:
    """
    Returns (target_file_path, code_string, tokens_used)
    Parse TARGET_FILE: line from response before returning.
    """
```

---

### 8. Updated Iteration Loop (`backend/runner/loop.py`)

```python
async def run_iteration_loop(feature_id, session_id):

    # ── GATE ───────────────────────────────────────────────────────────────────
    feature = db.get_feature(feature_id)
    assert feature.approved_at, "Metric must be approved before loop starts"

    # ── SETUP ──────────────────────────────────────────────────────────────────
    project = db.get_project(feature.project_id)
    user = db.get_user(project.user_id)
    access_token = decrypt_token(user.github_access_token)  # decrypt once, use, discard

    repo = db.get_primary_repo(project.id)
    local_path = repo.local_path

    # Create feature branch locally
    branch_name = create_feature_branch(local_path, session_id)
    db.update_feature(feature_id, feature_branch=branch_name)
    db.update_session(session_id, feature_branch=branch_name)

    # Compose setup
    compose_result = {
        "compose_yaml": project.generated_compose,
        "needs_infra": bool(project.generated_compose),
        "env_vars": project.detected_stack.get("env_vars", {}) if project.detected_stack else {}
    }
    if compose_result["needs_infra"]:
        compose_path = save_compose_file(project.id, session_id, compose_result["compose_yaml"])
        compose_result["compose_path"] = compose_path

    repo_context = {
        "file_tree": get_repo_file_tree(local_path),
        "key_files": read_key_files(local_path),
        "detected_stack": project.detected_stack
    }

    # ── LOOP ───────────────────────────────────────────────────────────────────
    best = {"score": 0.0, "commit_hash": None, "iteration": None}
    history = []

    for i in range(1, max_iterations + 1):

        # Generate code (returns target_file + code + tokens)
        target_file, code, tokens = await generate_code(
            feature.module_spec, test_cases, i,
            history[-5:], best["iteration"],
            repo_context, compose_result.get("env_vars", {})
        )

        # Write into cloned repo at correct path
        write_generated_code_to_repo(local_path, target_file, code)

        # Run sandbox
        result = run_in_sandbox(code, test_cases, session_id, project.id, compose_result)
        score = compute_score(result)
        failed_details = extract_failed_details(result, test_cases)

        # Commit to feature branch (local only)
        commit_hash, diff = commit_iteration(local_path, session_id, i, score,
                                             result["passed"], result["total"])

        # Persist
        iteration = save_iteration(session_id, i, score, code, commit_hash, diff,
                                   result, failed_details, tokens)

        # Update best
        if score > best["score"]:
            best = {"score": score, "commit_hash": commit_hash, "iteration": iteration}
            mark_as_best(iteration.id)

        history.append({
            "iteration_number": i, "score": score,
            "diff_summary": summarize_diff(diff),
            "failed_details": failed_details
        })

        if score >= 1.0:
            break

    # ── PUSH BEST TO GITHUB ────────────────────────────────────────────────────
    reset_to_best_iteration(local_path, best["commit_hash"])
    push_feature_branch(local_path, branch_name, access_token)

    db.update_session(session_id, pushed_at=utcnow(), push_commit_hash=best["commit_hash"])
    db.update_feature(feature_id, status="DONE" if best["score"] >= 1.0 else "PARTIAL")
```

---

### 9. Feature API (`backend/routers/features.py`)

```
POST /projects/{project_id}/features
  Auth: required
  Body: { "title": str, "raw_requirement": str }
  Response: { "feature_id": uuid, "status": "INTERCEPTING" }
  Background: intercept_requirement(raw_requirement, repo_context=...)

GET /projects/{project_id}/features
  Response: list with status + feature_branch + pushed_at

GET /features/{feature_id}
  Response: full feature including:
    module_spec, benchmark_plan, session, best iteration,
    feature_branch, pushed_at,
    github_branch_url: "https://github.com/{owner}/{repo}/tree/{branch}"

POST /features/{feature_id}/clarify
  Body: { "answers": { "question": "answer" } }
  Response: updated interceptor result

POST /features/{feature_id}/approve-metric
  Body: { "approved": true }
  Response: { "status": "RUNNING", "feature_branch": "feature/{session_id}" }
```

---

## Auth Routes (`backend/routers/auth.py`)

```
GET  /auth/github           → RedirectResponse to GitHub OAuth (repo scope)
GET  /auth/github/callback  → exchange code, upsert user, issue JWT, redirect frontend
GET  /auth/me               → { github_username, avatar_url, email }
POST /auth/logout           → { status: "ok" } (client deletes JWT)
```

---

## Frontend (`frontend/App.jsx`)

### Screen 0: Login
```
No JWT in localStorage → show login screen
"Login with GitHub" button → window.location.href = /auth/github
On load: if ?token= in URL → save to localStorage → navigate to /dashboard
```

### Screen 1: Dashboard
```
GET /projects → project cards
Each card: name | repo clone badges | detected stack badges (🍃 MongoDB 📨 Kafka) | feature count
"+ New Project" button
```

### Screen 2: New Project
```
Form: Name | Description | GitHub URLs (dynamic list) | Repo Structure (Mono ✓ | Multi (soon) | Microservices (soon))
On submit → POST /projects
Poll GET /projects/{id} every 2s:
  Per repo: PENDING → CLONING ⏳ → DONE ✅ / FAILED ❌
  After all DONE: "🤖 AI analyzing codebase..." → "🤖 AI writing sandbox config..." → "✅ Ready"
  Show detected stack badges
"View Project →" appears when ready
```

### Screen 3: Project — Feature List
```
Project header + repo badges
Feature list: title | status badge | score | branch name | "View →"
"+ Add Feature" button
```

### Screen 4: Add Feature
```
Textarea: requirement
Submit → POST /projects/{id}/features
Poll status:
  INTERCEPTING → "🤖 Analyzing..."
  AWAITING_CLARIFICATION → render question form → POST /features/{id}/clarify
  AWAITING_METRIC_APPROVAL → navigate to Screen 5
```

### Screen 5: Metric Approval (hard gate)
```
┌────────────────────────────────────────────────────────────┐
│  📊 Here's exactly what we will measure                    │
│                                                            │
│  Metric:  Test case pass rate                              │
│  Formula: passed_cases / total_cases                       │
│  Target:  100% — all 15 test cases must pass               │
│                                                            │
│  Test breakdown:                                           │
│  ├─ ✅  3  Happy path   Valid login, token refresh          │
│  ├─ 🔒  4  Security     SQL injection, XSS, overflow       │
│  ├─ 📏  3  Boundary     Password=8 chars, 50-char email    │
│  ├─ ⚠️   3  Null input  Missing email, null body           │
│  └─ 🔀  2  Edge case    Unicode password, subdomain email  │
│                                                            │
│  🐳 Real infrastructure:  MongoDB · Kafka                  │
│     Tests will perform actual reads, writes, publishes     │
│                                                            │
│  ⏱  ~90 seconds per iteration                             │
│                                                            │
│  📁 Code pushed to:                                        │
│     feature/{session_id}  (never touches main or develop)  │
│                                                            │
│  [ ✅ Approve & Start Development ]  [ ✏️ Edit Requirement ]│
└────────────────────────────────────────────────────────────┘
```

### Screen 6: Live Loop Dashboard
```
Header: "Building: {title}" | Branch: feature/{session_id} | Iter {N}/{max}

Score (large, color-coded):
  < 50%  → red
  50-99% → amber
  100%   → green

Progress bar: N of max_iterations

Iteration feed (newest first):
  Card: Iter N | Score 83% | ✅ 10/12 | ⏱ 87s
  [Expand] → diff viewer | failed cases | error log

On complete:
  ✅ "Solved in N iterations" OR ⚠️ "Best: X% — N cases failing"
  "🚀 Pushed to: feature/{session_id}"
  [View Branch on GitHub ↗]
  Code viewer | Benchmark breakdown | Git log
  [Retry] button (if PARTIAL)
```

---

## Multi-Repo / Microservices Provision

Data model supports it (`ProjectRepo.role`, `Project.repo_structure`).

MVP enforcement:
```python
if len(github_urls) > 1 or repo_structure != "MONO":
    raise HTTPException(400, detail="Multi-repo coming soon. Use single mono-repo for now.")
```

Mark junctions with `# TODO(v3-multi-repo):` in:
- `git_manager.py` — clone_all_repos, cross-repo diff
- `codegen.py` — multi-repo context building
- `compose_agent.py` — inter-service networking
- `loop.py` — cross-service test orchestration

---

## Build Order for Claude Code

**Auth first — everything depends on it**
1. `backend/auth/github.py` — OAuth functions + Fernet (no DB yet)
2. `backend/models.py` — add User, Project, ProjectRepo, Feature to v1 models
3. `backend/database.py` — run migrations
4. `backend/auth/middleware.py` — JWT Bearer dependency
5. `backend/routers/auth.py` — /auth/github + /auth/github/callback
6. ✅ Test: full OAuth flow → JWT → /auth/me returns profile

**Project + clone**
7. `backend/git_manager.py` — clone_repo(), get_repo_file_tree(), read_key_files()
8. `backend/agents/compose_agent.py` — generate_compose()
9. `backend/routers/projects.py` — CRUD + background clone + compose task
10. ✅ Test: POST /projects with real private GitHub URL → clones → compose generated

**Feature lifecycle**
11. `backend/agents/benchmark.py` — add generate_metric_plan()
12. `backend/agents/interceptor.py` — add repo_context parameter
13. `backend/agents/codegen.py` — add repo_context, TARGET_FILE output format
14. `backend/routers/features.py` — all feature routes
15. `backend/routers/requirements.py` — /metric-plan + /approve-metric

**Compose sandbox**
16. `backend/runner/sandbox.py` — prepare_sandbox_files() + run_compose_sandbox()
17. ✅ Test: project with Mongo → compose spins real Mongo → test runs against it

**Loop + branch + push**
18. `backend/git_manager.py` — create_feature_branch(), commit_iteration(), reset_to_best_iteration(), push_feature_branch()
19. `backend/runner/loop.py` — full updated loop with gate + branch + push
20. ✅ End-to-end: approve metric → loop runs → feature branch appears on GitHub

**Frontend**
21. `frontend/App.jsx` — screens 0–6, test each screen against live API before next

---

## Key Invariants

**From v1 (still apply):**
- Score formula immutable: `passed / total`
- Iteration always commits (even score = 0.0)
- Context window capped: last 5 iterations detail + summary of all prior
- Temp sandbox dirs cleaned in `finally` blocks

**New in v2:**
- **`repo` OAuth scope required** — do not downgrade; private repos are primary use case
- **Fernet-encrypt access tokens** — decrypt only at moment of use, never store plain
- **Feature branch guard** — `push_feature_branch()` refuses if branch doesn't start with `feature/`
- **Reset before push** — always `reset_to_best_iteration()` before `push_feature_branch()`; push BEST, not latest
- **Clear token from remote URL** — immediately after push, set remote URL back to unauthenticated form
- **Metric approval hard gate** — loop checks `feature.approved_at` at startup; raises if null
- **Compose cleanup always runs** — `docker compose down -v --remove-orphans` in `finally`
- **Sandbox scratch is separate from repo** — never mix `sandboxes/{session_id}/` with the cloned repo directory
- **Never push to main or develop** — enforced by guard in push_feature_branch()
- **Multi-repo returns 400** — enforced at POST /projects
