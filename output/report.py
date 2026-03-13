import json
from datetime import datetime
from pathlib import Path
from typing import Optional


def generate(
    session_id: str,
    spec: dict,
    suite,  # TestSuite
    best: dict,
    history: list[dict],
    git_log: str = "",
    output_dir: Optional[Path] = None,
) -> Path:
    """Generate a full session report and write it to output_dir/report.md."""
    if output_dir is None:
        output_dir = Path("./output")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "report.md"
    lines = []

    module_name = spec.get("module_name", "module")
    result = best.get("result", {})
    passed = result.get("passed", 0)
    total = result.get("total", 0)
    score_pct = int(best.get("score", 0) * 100)

    lines.append(f"# GBADS Session Report\n")
    lines.append(f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
    lines.append(f"**Session ID**: `{session_id}`\n")
    lines.append(f"**Module**: `{module_name}`\n")
    lines.append(f"**Description**: {spec.get('description', '')}\n")
    lines.append("\n---\n")

    # Summary
    lines.append("## Summary\n")
    lines.append(f"- **Final score**: {passed}/{total} ({score_pct}%)\n")
    lines.append(f"- **Best iteration**: {best.get('iteration', 'N/A')}\n")
    lines.append(f"- **Total iterations**: {len(history)}\n")
    lines.append(f"- **Test cases**: {suite.total_cases}\n")
    lines.append("\n")

    # Iteration table
    lines.append("## Iteration History\n")
    lines.append("| Iter | Score | Passed | Total |\n")
    lines.append("|------|-------|--------|-------|\n")
    for h in history:
        lines.append(
            f"| {h['iteration']} | {h['score']:.3f} | {h.get('passed','?')} | {h.get('total','?')} |\n"
        )
    lines.append("\n")

    # Failing cases
    failing = [
        r for r in result.get("results", [])
        if r.get("status") in ("fail", "error")
    ]
    if failing:
        lines.append("## Failing Cases\n")
        for r in failing:
            lines.append(f"### {r['id']}\n")
            lines.append(f"- **Status**: {r['status']}\n")
            if r.get("error"):
                lines.append(f"- **Error**: `{r['error'][:300]}`\n")
            if r.get("actual_output") is not None:
                lines.append(f"- **Actual output**: `{json.dumps(r['actual_output'])[:200]}`\n")
            lines.append("\n")

    # Module spec
    lines.append("## Module Spec\n")
    lines.append("```json\n")
    lines.append(json.dumps(spec, indent=2))
    lines.append("\n```\n\n")

    # Git log
    if git_log:
        lines.append("## Git Log\n")
        lines.append("```\n")
        lines.append(git_log)
        lines.append("\n```\n")

    report_path.write_text("".join(lines), encoding="utf-8")
    return report_path
