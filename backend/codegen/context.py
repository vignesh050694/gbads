import json
import logging

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 24000  # ~6000 tokens at 4 chars/token


def estimate_tokens(text: str) -> int:
    """Rough token count estimate: ~4 chars per token."""
    return len(text) // 4


class ContextBuilder:
    def build(
        self,
        iteration_number: int,
        best: dict | None,
        history: list[dict],
    ) -> dict:
        """Build the iteration context dict for the codegen agent."""
        context: dict = {"iteration_number": iteration_number}

        if best and best.get("iteration") is not None:
            best_result = best.get("result", {})
            failing = [
                r for r in best_result.get("results", [])
                if r.get("status") in ("fail", "error")
            ]
            failing_ids = [r["id"] for r in failing]

            # Build error traces dict — truncate long traces
            error_traces = {}
            for r in failing:
                if r.get("error"):
                    trace = r["error"]
                    if len(trace) > 500:
                        trace = trace[:500] + "... (truncated)"
                    error_traces[r["id"]] = trace

            context["best_so_far"] = {
                "iteration": best["iteration"],
                "score": best["score"],
                "failing_cases": failing_ids,
                "error_traces": error_traces,
                "code_diff_summary": best.get("diff_summary", ""),
            }
        else:
            context["best_so_far"] = None

        # Summarize past approaches
        approaches = []
        for h in history:
            approach = (
                f"iteration_{h['iteration']}: score={h['score']:.2f}, "
                f"passed={h.get('passed', '?')}/{h.get('total', '?')}"
            )
            if h.get("approach_note"):
                approach += f", note={h['approach_note']}"
            approaches.append(approach)

        context["all_tried_approaches"] = approaches

        # Enforce context size budget
        context_str = json.dumps(context)
        if len(context_str) > _MAX_CONTEXT_CHARS:
            logger.warning(
                "Context too large (%d chars), summarizing error traces",
                len(context_str),
            )
            if "best_so_far" in context and context["best_so_far"]:
                # Truncate error traces aggressively
                for k in context["best_so_far"].get("error_traces", {}):
                    context["best_so_far"]["error_traces"][k] = (
                        context["best_so_far"]["error_traces"][k][:200] + "..."
                    )
                # Keep only last 5 approaches
                context["all_tried_approaches"] = approaches[-5:]

        return context
