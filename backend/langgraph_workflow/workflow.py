"""
GBADS generation workflow built with LangGraph.

The workflow covers the code-generation iteration loop:

    setup_context
         │
    generate_code ◄──────────────────────────────────┐
         │                                            │
    run_sandbox                                       │
         │                                            │
    commit_and_track                                  │
         │                                            │
    check_target ──► should_continue ──► "generate_code"
         │
         └──────────────────────────────► finalize
                                               │
                                              END

Usage::

    from langgraph_workflow.workflow import generation_workflow
    final_state = await generation_workflow.ainvoke(initial_state)
"""
from langgraph.graph import END, StateGraph

from langgraph_workflow.nodes import (
    check_target,
    commit_and_track,
    finalize,
    generate_code,
    run_sandbox,
    setup_context,
    should_continue,
)
from langgraph_workflow.state import GBADSState


def build_workflow():
    """Construct and compile the GBADS StateGraph."""
    g = StateGraph(GBADSState)

    # ── Register nodes ────────────────────────────────────────────────────────
    g.add_node("setup_context", setup_context)
    g.add_node("generate_code", generate_code)
    g.add_node("run_sandbox", run_sandbox)
    g.add_node("commit_and_track", commit_and_track)
    g.add_node("check_target", check_target)
    g.add_node("finalize", finalize)

    # ── Entry point ───────────────────────────────────────────────────────────
    g.set_entry_point("setup_context")

    # ── Edges ─────────────────────────────────────────────────────────────────
    g.add_edge("setup_context", "generate_code")
    g.add_edge("generate_code", "run_sandbox")
    g.add_edge("run_sandbox", "commit_and_track")
    g.add_edge("commit_and_track", "check_target")

    # Conditional: loop back or finish
    g.add_conditional_edges(
        "check_target",
        should_continue,
        {
            "generate_code": "generate_code",
            "finalize": "finalize",
        },
    )

    g.add_edge("finalize", END)

    return g.compile()


# Module-level compiled workflow — import and call .ainvoke() directly
generation_workflow = build_workflow()
