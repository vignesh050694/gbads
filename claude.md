# Goal-Based Autonomous Development System (GBADS)

## Project Overview

Build a self-validating, autonomous code generation system where an AI agent interprets requirements, generates code, validates it inside a Docker sandbox, and iterates until the benchmark is met — without human involvement in the loop.

The core loop is inspired by Karpathy's autoresearch pattern:
```
interpret requirement → generate code → sandbox execution → benchmark score → iterate or ship
```

---

## Tech Stack

- **Backend**: Python (FastAPI)
- **Agent / LLM**: Anthropic Claude API (claude-sonnet-4-6)
- **Sandbox**: Docker (per-iteration throwaway containers)
- **Version Control**: GitPython (local commits only, no remote push)
- **Database**: Postgres (iteration history, benchmark results)
- **Queue**: Python asyncio (iteration loop management)
- **CLI interface**: Typer (for initial version, UI can come later)

---

## System Components

### 1. Requirement Interceptor Agent (`interceptor/agent.py`)

**Responsibility**: Parse natural language requirement, ask minimal clarifying questions, return structured module spec.

**Inputs**:
- Raw user requirement (string)
- Optional follow-up answers from user

**Outputs**:
```json
{
  "module_name": "login",
  "description": "Authenticates user with email and password",
  "fields": [
    { "name": "email", "type": "string", "constraints": ["email_format"] },
    { "name": "password", "type": "string", "constraints": ["min_8_chars", "1_uppercase", "1_special_char"] }
  ],
  "returns": [
    { "name": "token", "type": "string" },
    { "name": "expires_in", "type": "integer" }
  ],
  "clarifying_questions": []
}
```

**Behavior rules**:
- Ask ZERO questions if requirement is unambiguous
- Ask MAX 3 clarifying questions, only architectural ones (e.g. JWT vs session, rate limiting yes/no)
- Never ask about implementation details — agent decides those
- If questions remain unanswered after 1 round, make sensible defaults and proceed

**Prompt design**:
- System prompt must enforce minimal questioning behavior
- Return structured JSON only — no prose
- Include a `confidence_score` (0.0–1.0) on the spec — if below 0.7, surface questions

---

### 2. Benchmark Generator (`benchmark/generator.py`)

**Responsibility**: Take user-provided sample input/output pairs and expand into a full test suite.

**Inputs**:
- Module spec (from Interceptor)
- User-provided examples:
  ```json
  {
    "happy_path": [
      { "input": { "email": "john@test.com", "password": "Pass@123" }, "expected_output": { "token": "<any_jwt>", "expires_in": 3600 } }
    ]
  }
  ```

**Auto-generated test case categories**:
1. **Happy path** — user provided + valid variations
2. **Boundary conditions** — min/max length, exact constraint edges
3. **Null / empty inputs** — missing fields, empty strings, null values
4. **Type mismatches** — integer where string expected, etc.
5. **Constraint violations** — password without uppercase, invalid email format
6. **Security cases** — SQL injection attempts, XSS payloads, oversized inputs
7. **Idempotency** — same input twice should return consistent output

**Output**:
```json
{
  "total_cases": 24,
  "cases": [
    {
      "id": "tc_001",
      "category": "happy_path",
      "input": { ... },
      "expected": { ... },
      "match_strategy": "exact" | "schema" | "contains" | "custom_fn"
    }
  ]
}
```

**Match strategies**:
- `exact` — output must match exactly
- `schema` — output must match shape/types (use for tokens, dynamic values)
- `contains` — output must contain expected keys/values
- `custom_fn` — for cases like JWT validation where you check structure not value

**Score formula**:
```python
score = len(passed_cases) / len(total_cases)  # target: 1.0
```

---

### 3. Code Generation Agent (`codegen/agent.py`)

**Responsibility**: Generate module code given spec + benchmark + iteration history.

**Context window per iteration must include**:
```
1. Module spec (fields, constraints, return types)
2. Full benchmark test cases
3. Current best score + which iteration achieved it
4. Diff summary of best iteration's code
5. Specific failing test case IDs + error traces from best iteration
6. List of approaches already tried (to avoid repetition)
7. Instruction: generate ONLY the implementation file, no test files
```

**Output**: Single implementation file (e.g. `login.py` or `login.js`)

**Rules**:
- Must not modify the test runner
- Must not install packages outside a pre-approved list
- Must handle all constraint validation internally
- Code must be self-contained in one file per module

**Iteration memory structure** (`iteration_context`):
```python
{
  "iteration_number": 3,
  "best_so_far": {
    "iteration": 2,
    "score": 0.75,
    "failing_cases": ["tc_008", "tc_019", "tc_021"],
    "error_traces": { "tc_008": "KeyError: token", ... },
    "code_diff_summary": "Added JWT generation, missing expiry handling"
  },
  "all_tried_approaches": [
    "iteration_1: basic dict return, no JWT",
    "iteration_2: added JWT but missing expiry field"
  ]
}
```

---

### 4. Sandbox Executor (`sandbox/executor.py`)

**Responsibility**: Spin up Docker container, run generated code against benchmark, capture results, destroy container.

**Docker configuration**:
```python
SANDBOX_CONFIG = {
  "base_image": "python:3.11-slim",  # pre-built, kept warm
  "network_mode": "none",            # NO network access
  "mem_limit": "256m",
  "cpu_quota": 50000,                # 0.5 CPU
  "read_only": False,                # needs write for temp files
  "mounts": [
    # ONLY these two paths mounted, nothing else
    "/tmp/gbads/{run_id}/module/",   # generated code (read-only mount)
    "/tmp/gbads/{run_id}/tests/",    # test runner + benchmark cases (read-only mount)
  ],
  "auto_remove": True,               # destroy on exit
  "timeout_seconds": 30              # hard kill after 30s
}
```

**Execution flow**:
```
1. Write generated code to /tmp/gbads/{run_id}/module/
2. Write test runner + benchmark cases to /tmp/gbads/{run_id}/tests/
3. docker run with config above
4. Capture stdout (JSON results) + stderr (error traces)
5. Parse results → { passed: [], failed: [], errors: {} }
6. Container auto-removed
7. Clean up /tmp/gbads/{run_id}/
```

**Test runner** (`sandbox/test_runner.py` — this file is FIXED, never modified by agent):
```python
# Runs inside the container
# Imports the generated module
# Executes each test case
# Returns JSON to stdout:
{
  "run_id": "...",
  "score": 0.75,
  "total": 24,
  "passed": 18,
  "failed": 6,
  "results": [
    { "id": "tc_001", "status": "pass", "duration_ms": 12 },
    { "id": "tc_008", "status": "fail", "error": "KeyError: token", "actual_output": {...} }
  ]
}
```

---

### 5. Iteration Loop Manager (`loop/manager.py`)

**Responsibility**: Orchestrate the full loop, manage best-of-N selection, enforce limits, emit events.

**Configuration** (user-settable):
```python
LOOP_CONFIG = {
  "max_iterations": 10,          # user sets (10 or 20), system hard ceiling: 50
  "target_score": 1.0,           # exit condition
  "early_exit_on_perfect": True, # stop immediately at 1.0
}
```

**Loop pseudocode**:
```python
best = { "score": 0.0, "iteration": None, "code": None }
history = []

for i in range(1, max_iterations + 1):
    
    # Build context from history
    context = build_iteration_context(best, history)
    
    # Generate code
    code = codegen_agent.generate(spec, benchmark, context)
    
    # Execute in sandbox
    result = sandbox.run(code, benchmark)
    
    # Local git commit with diff tag
    git.commit(code, message=f"iteration_{i} score={result.score:.2f}")
    
    # Log iteration
    history.append({ "iteration": i, "score": result.score, "code": code, "result": result })
    db.save_iteration(run_id, i, result)
    
    # Update best
    if result.score > best["score"]:
        best = { "score": result.score, "iteration": i, "code": code, "result": result }
    
    # Early exit
    if result.score >= target_score:
        break

# Select head
head = best
notify_user(head, history)
```

---

### 6. Git Manager (`git/manager.py`)

**Responsibility**: Local git commits per iteration, diff generation, no remote push.

**Commit structure**:
```
commit message: "iter_{N} | score={score} | passed={X}/{Y} | {module_name}"
commit tag:     "iter_{N}_best" (only on iterations that beat previous best)
```

**Per iteration stored**:
- Full generated code file
- Benchmark result JSON
- Diff from previous iteration
- Diff from current best

**On session end**:
- Tag final head commit as `head_selected`
- Generate full session diff report (first iteration → head)

---

### 7. Notification / Output Layer (`output/notifier.py`)

**On success (score = 1.0)**:
```
✅ SOLVED in {N} iteration(s)

Module: login
Score: 24/24 test cases passed (100%)
Iterations used: 3 / 10 max
Tokens consumed: ~12,400

📁 Output: ./output/login.py
📋 Git log: ./output/session.log
```

**On max iterations reached (score < 1.0)**:
```
⚠️ Best result selected (score < 1.0)

Module: login  
Best score: 20/24 test cases passed (83%) — achieved at iteration 7
Iterations used: 10 / 10 max

❌ Still failing:
  - tc_008: Security — SQL injection not rejected (KeyError: token)
  - tc_019: Boundary — password exactly 8 chars not accepted
  - tc_021: Null input — missing email field crashes instead of returning 400
  - tc_024: Type — integer passed as email not rejected

📁 Output: ./output/login.py (best iteration)
📋 Full report: ./output/report.md
📊 Git log: ./output/session.log
```

---

## File Structure

```
gbads/
├── CLAUDE.md                    # this file
├── main.py                      # CLI entry point
├── config.py                    # global config, env vars
│
├── interceptor/
│   ├── agent.py                 # requirement parsing agent
│   └── prompts.py               # system + user prompts
│
├── benchmark/
│   ├── generator.py             # test suite generator
│   ├── cases.py                 # test case data structures
│   └── match.py                 # match strategy implementations
│
├── codegen/
│   ├── agent.py                 # code generation agent
│   ├── context.py               # iteration context builder
│   └── prompts.py               # codegen system prompts
│
├── sandbox/
│   ├── executor.py              # Docker orchestration
│   ├── test_runner.py           # FIXED — runs inside container
│   └── docker_config.py        # container config constants
│
├── loop/
│   └── manager.py               # iteration loop orchestrator
│
├── git/
│   └── manager.py               # local git operations
│
├── output/
│   ├── notifier.py              # user-facing result formatting
│   └── report.py                # full session report generator
│
├── db/
│   └── store.py                 # Postgres iteration history
│
└── tests/
    └── test_benchmark.py        # unit tests for benchmark generator
```

---

## Data Flow Summary

```
User Input (requirement + sample I/O)
        │
        ▼
[Interceptor Agent]  →  Module Spec JSON
        │
        ▼
[Benchmark Generator]  →  Test Suite (N cases, scored 0.0–1.0)
        │
        ▼
[Iteration Loop] ─────────────────────────────────────┐
        │                                              │
        ▼                                              │
[Codegen Agent]  ←  spec + benchmark + iteration ctx  │
        │                                              │
        ▼                                              │
[Sandbox Executor]  →  score + pass/fail per case      │
        │                                              │
        ▼                                              │
[Git Manager]  →  local commit + diff tag              │
        │                                              │
   score == 1.0?                                       │
   OR iterations == max?  ──── NO ─────────────────────┘
        │
       YES
        │
        ▼
[Output Notifier]  →  head code + summary + report
```

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=           # Claude API key
GBADS_MAX_ITERATIONS=10      # default max iterations
GBADS_HARD_CEILING=50        # absolute max, non-negotiable
GBADS_TARGET_SCORE=1.0       # exit threshold
GBADS_SANDBOX_TIMEOUT=30     # seconds per sandbox run
GBADS_OUTPUT_DIR=./output    # where to write results
GBADS_DB_PATH=./gbads.db     # Postgres path
```

---

## Build Order for Claude Code

Build in this sequence — each step is independently testable:

1. **`config.py`** — env vars, constants
2. **`db/store.py`** — Postgres schema, iteration CRUD
3. **`benchmark/cases.py`** — data structures only
4. **`benchmark/match.py`** — match strategy logic (unit testable)
5. **`benchmark/generator.py`** — test suite generator (mock LLM call first)
6. **`sandbox/test_runner.py`** — CRITICAL: build and lock this first, never modify after
7. **`sandbox/docker_config.py`** — container config constants
8. **`sandbox/executor.py`** — Docker orchestration
9. **`interceptor/prompts.py`** — prompts first
10. **`interceptor/agent.py`** — interceptor agent
11. **`codegen/prompts.py`** — codegen prompts
12. **`codegen/context.py`** — iteration context builder
13. **`codegen/agent.py`** — code generation agent
14. **`git/manager.py`** — local git operations
15. **`loop/manager.py`** — iteration loop (wires everything together)
16. **`output/notifier.py`** + **`output/report.py`**
17. **`main.py`** — CLI entry point

---

## Key Invariants (Never Break These)

- `sandbox/test_runner.py` is FIXED — codegen agent must never be given permission to modify it
- Docker containers must have `network_mode: none` — no exceptions
- Git commits are LOCAL ONLY — no `git push` anywhere in codebase
- Score is always `passed / total` — never weighted, never fudged
- Best iteration is always preserved even if later iterations are worse
- On max iterations, ALWAYS deliver best result — never return empty-handed

---

## Example CLI Usage

```bash
# Start a new module generation session
python main.py generate --requirement "Build a login module with JWT auth" 

# With sample I/O file
python main.py generate --requirement "Build a login module" --examples ./examples/login.json

# With custom iteration limit
python main.py generate --requirement "Build a login module" --max-iter 20

# Resume a failed session (start from best iteration)
python main.py resume --session-id abc123
```

---

## Notes for Claude Code

- Use `docker` Python SDK (`docker` package) for container management, not subprocess shell calls
- Use `gitpython` for all git operations
- All LLM calls go through a single `llm/client.py` wrapper — makes it easy to swap models or add retry logic
- Every agent call should log: prompt token count, completion token count, duration — stored in Postgres
- The `test_runner.py` that runs inside Docker must have zero external dependencies beyond stdlib — it cannot `pip install` anything
- Benchmark generator should use Claude to intelligently expand test cases, not just hardcoded templates
- When building the codegen context, keep it under 8000 tokens — summarize aggressively if history grows large