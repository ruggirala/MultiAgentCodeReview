"""
LangGraph StateGraph that orchestrates the multi-agent code review pipeline.

Flow:

    orchestrate
        -> security ─┐
        -> bug       ├─ (analysis, run sequentially; all append to findings)
        -> style ────┘
        -> triage  ── conditional ──> human_review ─┐
                                   └────────────────┤
                                                     v
                                                   patch
                                                     v
                                                   tests
                                                     v
                                                    END

The conditional edge after triage routes Critical/High *security* findings to a
human-review node (a human-in-the-loop checkpoint). With no interrupt configured
it logs and continues, but the graph structure supports a real interrupt on Colab.

State is the Pydantic `ReviewState`; each node returns the mutated state.
"""

from __future__ import annotations

import time
from typing import Callable

from agents import (
    bug_agent,
    orchestrator,
    patch_agent,
    security_agent,
    style_agent,
    test_agent,
)
from metrics import AgentEvent, record, reset_current_agent, set_current_agent
from models.schemas import ReviewState

# Routing threshold lives in one place.
HUMAN_REVIEW_BRANCH = "human_review"
CONTINUE_BRANCH = "patch"


def _instrumented(
    name: str, fn: Callable[[ReviewState], ReviewState]
) -> Callable[[ReviewState], ReviewState]:
    """Wrap an agent function to time it, count findings added, and emit an AgentEvent.

    Also sets a contextvar so any LLM calls made inside `fn` are attributed to
    this agent in the LLM telemetry.
    """

    def wrapper(state: ReviewState) -> ReviewState:
        before = len(state.findings)
        start = time.perf_counter()
        token = set_current_agent(name, state.run_id)
        err: str | None = None
        try:
            result = fn(state)
            return result
        except Exception as exc:  # noqa: BLE001 - re-raised after recording
            err = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            reset_current_agent(token)
            duration = time.perf_counter() - start
            added = max(0, len(state.findings) - before)
            record(
                AgentEvent(
                    run_id=state.run_id or "unknown",
                    file_name=state.file_name,
                    agent_name=name,
                    duration_sec=duration,
                    findings_added=added,
                    error=err,
                )
            )

    return wrapper


# --- node wrappers -------------------------------------------------------
# Each agent already takes/returns ReviewState, so nodes are thin.


def _orchestrate(state: ReviewState) -> ReviewState:
    return orchestrator.orchestrate(state)


def _security(state: ReviewState) -> ReviewState:
    return security_agent.analyze(state)


def _bug(state: ReviewState) -> ReviewState:
    return bug_agent.analyze(state)


def _style(state: ReviewState) -> ReviewState:
    return style_agent.analyze(state)


def _triage(state: ReviewState) -> ReviewState:
    """Decide whether the findings warrant a human-in-the-loop pause."""
    critical = state.critical_security_findings()
    state.needs_human_review = bool(critical)
    if state.needs_human_review:
        print(
            f"[triage] {len(critical)} critical/high security finding(s) — "
            "flagging for human review."
        )
    return state


def _human_review(state: ReviewState) -> ReviewState:
    """
    Human-in-the-loop checkpoint.

    In a notebook/CLI this surfaces the critical findings for acknowledgement.
    A production deployment would use LangGraph's `interrupt` to truly pause.
    """
    print("\n" + "=" * 60)
    print("  HUMAN REVIEW REQUESTED — critical security findings")
    print("=" * 60)
    for f in state.critical_security_findings():
        loc = f"line {f.line}" if f.line else "general"
        cwe = f" [{f.cwe}]" if f.cwe else ""
        print(f"  - ({loc}) {f.title}{cwe}: {f.description}")
    print("=" * 60 + "\n")
    return state


def _patch(state: ReviewState) -> ReviewState:
    return patch_agent.generate(state)


def _tests(state: ReviewState) -> ReviewState:
    return test_agent.generate(state)


# Wrapped versions used as graph nodes — these are what emit AgentEvents.
_node_orchestrate = _instrumented("orchestrate", _orchestrate)
_node_security = _instrumented("security", _security)
_node_bug = _instrumented("bug", _bug)
_node_style = _instrumented("style", _style)
_node_triage = _instrumented("triage", _triage)
_node_human_review = _instrumented("human_review", _human_review)
_node_patch = _instrumented("patch", _patch)
_node_tests = _instrumented("tests", _tests)


def _route_after_triage(state: ReviewState) -> str:
    """Conditional edge: pause for humans on critical security, else proceed."""
    return HUMAN_REVIEW_BRANCH if state.needs_human_review else CONTINUE_BRANCH


def build_graph():
    """Construct and compile the LangGraph StateGraph."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ReviewState)

    graph.add_node("orchestrate", _node_orchestrate)
    graph.add_node("security", _node_security)
    graph.add_node("bug", _node_bug)
    graph.add_node("style", _node_style)
    graph.add_node("triage", _node_triage)
    graph.add_node("human_review", _node_human_review)
    graph.add_node("patch", _node_patch)
    graph.add_node("tests", _node_tests)

    # Linear analysis chain (sequential keeps shared-state writes simple).
    graph.add_edge(START, "orchestrate")
    graph.add_edge("orchestrate", "security")
    graph.add_edge("security", "bug")
    graph.add_edge("bug", "style")
    graph.add_edge("style", "triage")

    # Conditional routing out of triage.
    graph.add_conditional_edges(
        "triage",
        _route_after_triage,
        {HUMAN_REVIEW_BRANCH: "human_review", CONTINUE_BRANCH: "patch"},
    )
    graph.add_edge("human_review", "patch")
    graph.add_edge("patch", "tests")
    graph.add_edge("tests", END)

    return graph.compile()


def run_pipeline(
    file_name: str,
    source_code: str,
    *,
    run_id: str | None = None,
) -> ReviewState:
    """
    Convenience entrypoint: build the graph, run it, and return final state.

    LangGraph returns the state as a dict-like; we re-validate it back into a
    `ReviewState` so callers always get a typed object.

    `run_id` is stamped onto the state so AgentEvent/LLMCallEvent emissions
    from this run are linkable back to the PR review that started them.
    """
    app = build_graph()
    initial = ReviewState(
        file_name=file_name,
        source_code=source_code,
        run_id=run_id,
    )
    result = app.invoke(initial)
    if isinstance(result, ReviewState):
        return result
    return ReviewState.model_validate(result)
