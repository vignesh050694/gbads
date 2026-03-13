from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def notify_success(
    best: dict,
    history: list[dict],
    module_name: str,
    session_id: str,
    output_path: Optional[Path] = None,
    git_log: str = "",
) -> None:
    total_tokens = sum(
        h.get("prompt_tokens", 0) + h.get("completion_tokens", 0)
        for h in history
    )

    result = best.get("result", {})
    passed = result.get("passed", best.get("passed", 0))
    total = result.get("total", best.get("total", 0))

    text = Text()
    text.append(f"Module: {module_name}\n", style="bold")
    text.append(f"Score: {passed}/{total} test cases passed (100%)\n", style="green")
    text.append(f"Iterations used: {best['iteration']} / {len(history)} max\n")
    if total_tokens:
        text.append(f"Tokens consumed: ~{total_tokens:,}\n")
    if output_path:
        text.append(f"\n📁 Output: {output_path}\n", style="cyan")
    if session_id:
        text.append(f"📋 Session ID: {session_id}\n", style="dim")

    console.print(Panel(text, title="✅ SOLVED", border_style="green"))

    if git_log:
        console.print("\n[bold]Git log:[/bold]")
        console.print(git_log, style="dim")


def notify_best_effort(
    best: dict,
    history: list[dict],
    module_name: str,
    session_id: str,
    output_path: Optional[Path] = None,
    report_path: Optional[Path] = None,
    git_log: str = "",
) -> None:
    result = best.get("result", {})
    passed = result.get("passed", 0)
    total = result.get("total", 0)
    score_pct = int(best["score"] * 100)

    text = Text()
    text.append(f"Module: {module_name}\n", style="bold")
    text.append(
        f"Best score: {passed}/{total} test cases passed ({score_pct}%)"
        f" — achieved at iteration {best['iteration']}\n",
        style="yellow",
    )
    text.append(f"Iterations used: {len(history)} / {len(history)} max\n")

    # List failing cases
    failing = [
        r for r in result.get("results", [])
        if r.get("status") in ("fail", "error")
    ]
    if failing:
        text.append("\n❌ Still failing:\n", style="red bold")
        for r in failing[:10]:
            error = r.get("error", "unknown error")
            if len(error) > 100:
                error = error[:100] + "..."
            text.append(f"  - {r['id']}: {error}\n", style="red")
        if len(failing) > 10:
            text.append(f"  ... and {len(failing) - 10} more\n", style="red dim")

    if output_path:
        text.append(f"\n📁 Output: {output_path}\n", style="cyan")
    if report_path:
        text.append(f"📋 Full report: {report_path}\n", style="cyan")
    if session_id:
        text.append(f"🔑 Session ID: {session_id}\n", style="dim")

    console.print(Panel(text, title="⚠️  Best Result Selected (score < 1.0)", border_style="yellow"))

    # Print iteration history table
    table = Table(title="Iteration History", show_lines=True)
    table.add_column("Iter", style="cyan", width=6)
    table.add_column("Score", style="green", width=8)
    table.add_column("Passed/Total", width=14)
    for h in history:
        score_str = f"{h['score']:.3f}"
        pt = f"{h.get('passed', '?')}/{h.get('total', '?')}"
        table.add_row(str(h["iteration"]), score_str, pt)
    console.print(table)

    if git_log:
        console.print("\n[bold]Git log:[/bold]")
        console.print(git_log, style="dim")


def notify_progress(iteration: int, max_iter: int, score: float, passed: int, total: int) -> None:
    console.print(
        f"  [cyan]Iteration {iteration}/{max_iter}[/cyan] "
        f"→ score=[green]{score:.3f}[/green] ({passed}/{total} passed)"
    )
