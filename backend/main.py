"""
GBADS — Goal-Based Autonomous Development System
CLI entry point.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

import db.store as store
from config import get_settings
from loop.manager import LoopManager
from output import notifier, report as report_gen

app = typer.Typer(
    name="gbads",
    help="Goal-Based Autonomous Development System — autonomous code generation with iterative benchmarking.",
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

    # Init DB
    await store.init_pool()

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

        # Write report
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
        await store.close_pool()


async def _run_resume(session_id: str) -> None:
    settings = get_settings()
    await store.init_pool()

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
        await store.close_pool()


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


if __name__ == "__main__":
    app()
