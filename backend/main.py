"""
GBADS v2 — Goal-Based Autonomous Development System
Entry point: FastAPI server + Typer CLI (including Agentic mode).
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console

import db.store as store_v1  # v1 legacy store (used by LoopManager)
from config import get_settings
from database import init_db
from loop.manager import LoopManager
from output import notifier, report as report_gen
from routers import auth, projects, features, requirements

# ── FastAPI app ────────────────────────────────────────────────────────────────

api = FastAPI(
    title="GBADS API",
    description="Goal-Based Autonomous Development System v2",
    version="2.0.0",
)
api.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api.include_router(auth.router)
api.include_router(projects.router)
api.include_router(features.router)
api.include_router(requirements.router)


@api.on_event("startup")
async def _startup():
    await init_db()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


# ── Typer CLI ──────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="gbads",
    help="Goal-Based Autonomous Development System — autonomous code generation + agentic coding.",
    no_args_is_help=True,
)
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)


def _load_examples(examples_path: Optional[Path]) -> dict:
    if examples_path is None:
        return {}
    try:
        return json.loads(examples_path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]Failed to load examples file: {exc}[/red]")
        raise typer.Exit(1)


async def _run_generate(
    requirement: str,
    examples: Optional[Path],
    max_iter: Optional[int],
) -> None:
    settings = get_settings()
    user_examples = _load_examples(examples)

    console.print(f"\n[bold cyan]GBADS[/bold cyan] — Starting autonomous generation")
    console.print(f"[dim]Requirement:[/dim] {requirement}")
    if max_iter:
        console.print(f"[dim]Max iterations:[/dim] {max_iter}")

    await store_v1.init_pool()

    try:
        loop_mgr = LoopManager()

        async def callback(event: str, data):
            if event == "iteration_start":
                console.print(
                    f"\n[bold]Iteration {data['iteration']}/{data['max']}[/bold]"
                )
            elif event == "iteration_done":
                r = data["result"]
                notifier.notify_progress(
                    data["iteration"],
                    data["best"].get("iteration", data["iteration"]),
                    r.score,
                    r.passed,
                    r.total,
                )
            elif event == "suite_ready":
                console.print(f"[green]Test suite ready:[/green] {data.total_cases} cases")
            return None

        outcome = await loop_mgr.run(
            requirement=requirement,
            user_examples=user_examples,
            max_iterations=max_iter,
            notify_callback=callback,
        )

        session_id = outcome["session_id"]
        best = outcome["best"]
        history = outcome["history"]
        spec = outcome["spec"]
        suite = outcome["suite"]
        git_log = outcome["git_log"]

        report_path = report_gen.generate(
            session_id=session_id,
            spec=spec,
            suite=suite,
            best=best,
            history=history,
            git_log=git_log,
            output_dir=settings.output_dir,
        )

        module_name = spec.get("module_name", "module")
        output_path = settings.output_dir / f"{module_name}.py"

        if best["score"] >= settings.target_score:
            notifier.notify_success(
                best=best,
                history=history,
                module_name=module_name,
                session_id=session_id,
                output_path=output_path,
                git_log=git_log,
            )
        else:
            notifier.notify_best_effort(
                best=best,
                history=history,
                module_name=module_name,
                session_id=session_id,
                output_path=output_path,
                report_path=report_path,
                git_log=git_log,
            )

    finally:
        await store_v1.close_pool()


async def _run_resume(session_id: str) -> None:
    settings = get_settings()
    await store_v1.init_pool()

    try:
        loop_mgr = LoopManager()
        console.print(f"\n[bold cyan]GBADS[/bold cyan] — Resuming session [dim]{session_id}[/dim]")
        outcome = await loop_mgr.resume(session_id)

        best = outcome["best"]
        history = outcome["history"]
        spec = outcome["spec"]
        suite = outcome["suite"]
        git_log = outcome["git_log"]
        module_name = spec.get("module_name", "module")

        report_path = report_gen.generate(
            session_id=session_id,
            spec=spec,
            suite=suite,
            best=best,
            history=history,
            git_log=git_log,
            output_dir=settings.output_dir,
        )

        output_path = settings.output_dir / f"{module_name}.py"

        if best["score"] >= settings.target_score:
            notifier.notify_success(
                best=best,
                history=history,
                module_name=module_name,
                session_id=session_id,
                output_path=output_path,
                git_log=git_log,
            )
        else:
            notifier.notify_best_effort(
                best=best,
                history=history,
                module_name=module_name,
                session_id=session_id,
                output_path=output_path,
                report_path=report_path,
                git_log=git_log,
            )
    finally:
        await store_v1.close_pool()


@app.command()
def generate(
    requirement: str = typer.Option(..., "--requirement", "-r", help="Natural language module requirement"),
    examples: Optional[Path] = typer.Option(
        None, "--examples", "-e",
        help="Path to JSON file with sample input/output pairs",
        exists=False,
    ),
    max_iter: Optional[int] = typer.Option(
        None, "--max-iter", "-n",
        help="Maximum number of iterations (default: GBADS_MAX_ITERATIONS env var)",
    ),
) -> None:
    """Generate a module autonomously from a requirement."""
    asyncio.run(_run_generate(requirement, examples, max_iter))


@app.command()
def resume(
    session_id: str = typer.Option(..., "--session-id", "-s", help="Session ID to resume"),
) -> None:
    """Resume a previous generation session from its best result."""
    asyncio.run(_run_resume(session_id))


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable hot reload"),
) -> None:
    """Start the GBADS v2 FastAPI server."""
    console.print(f"[bold cyan]GBADS v2 API[/bold cyan] -> http://{host}:{port}")
    uvicorn.run("main:api", host=host, port=port, reload=reload)


@app.command()
def agent(
    task: Optional[str] = typer.Option(
        None, "--task", "-t",
        help="Coding task to perform (omit for interactive mode)",
    ),
    working_dir: Path = typer.Option(
        Path("."), "--working-dir", "-d",
        help="Working directory (default: current directory)",
    ),
    max_turns: int = typer.Option(
        20, "--max-turns",
        help="Maximum tool-use turns before concluding",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i",
        help="Start in interactive REPL mode",
    ),
) -> None:
    """
    Agentic CLI mode -- Claude autonomously reads, edits, and tests code.

    Like GitHub Copilot's agent mode: provide a task and Claude will use
    tools (read_file, write_file, run_command, search_code) to complete it.

    Examples:

      python main.py agent --task "Add input validation to auth/login.py"

      python main.py agent -t "Fix the failing tests" -d ./my-project

      python main.py agent --interactive -d ./my-project
    """
    from agents.agentic_cli import AgenticCLI

    cli_agent = AgenticCLI(max_turns=max_turns)
    resolved_dir = working_dir.resolve()

    if not resolved_dir.exists():
        console.print(f"[red]Working directory not found: {resolved_dir}[/red]")
        raise typer.Exit(1)

    if interactive or not task:
        asyncio.run(cli_agent.run_interactive(resolved_dir))
    else:
        result = asyncio.run(cli_agent.run(task=task, working_dir=resolved_dir))
        if not result.success:
            raise typer.Exit(1)


if __name__ == "__main__":
    app()
