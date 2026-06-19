"""
JSONL telemetry recorder for the multi-agent code review pipeline.

Three event sources, one append-only file:

    PRReviewEvent   -- one per PR reviewed (handle_pr)
    AgentEvent      -- one per LangGraph node execution
    LLMCallEvent    -- one per call_llm() attempt (success or error)
    PollCycleEvent  -- one per watcher poll iteration

All events share a `type` field so the dashboard can dispatch on read.
Storage: runs/events.jsonl (append-only, line-delimited JSON).

The module is import-safe with no required env vars; failures while writing are
swallowed (a metric write must never break a review). Set
METRICS_DISABLED=1 to disable emission entirely.
"""

from __future__ import annotations

import contextvars
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# --- storage location --------------------------------------------------

# Resolve relative to the project root (the directory that contains this
# package). Keeps the path stable no matter what cwd the caller runs from.
_PKG_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = _PKG_ROOT / "runs"
EVENTS_PATH = RUNS_DIR / "events.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- event schemas -----------------------------------------------------


class _BaseEvent(BaseModel):
    """Common envelope. Subclasses set `type` via Literal."""

    timestamp_utc: datetime = Field(default_factory=_now)


class PRReviewEvent(_BaseEvent):
    type: Literal["pr_review"] = "pr_review"
    run_id: str
    owner: str
    repo: str
    pr_number: int
    head_sha: str
    title: str
    author: str
    files_reviewed: int
    files_skipped: int
    total_findings: int
    findings_by_severity: dict[str, int]
    findings_by_category: dict[str, int]
    needs_human_review: bool
    duration_sec: float
    agent_proposal_status: Optional[str] = None


class AgentEvent(_BaseEvent):
    type: Literal["agent"] = "agent"
    run_id: str
    file_name: str
    agent_name: str
    duration_sec: float
    findings_added: int = 0
    error: Optional[str] = None


class LLMCallEvent(_BaseEvent):
    type: Literal["llm_call"] = "llm_call"
    run_id: Optional[str] = None
    agent_name: Optional[str] = None
    backend: str
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    duration_sec: float
    attempt: int = 1
    error: Optional[str] = None


class PollCycleEvent(_BaseEvent):
    type: Literal["poll_cycle"] = "poll_cycle"
    poll_number: int
    open_pr_count: int
    new_pr_count: int
    reviewed_count: int
    error_count: int = 0
    backoff_sec: float = 0.0


AnyEvent = PRReviewEvent | AgentEvent | LLMCallEvent | PollCycleEvent


# --- recorder ----------------------------------------------------------


class MetricsRecorder:
    """Tiny append-only JSONL writer. Safe to call from anywhere.

    Failures are swallowed so a broken metrics path never breaks a review.
    """

    def __init__(self, path: Path = EVENTS_PATH) -> None:
        self.path = path

    @property
    def disabled(self) -> bool:
        return os.environ.get("METRICS_DISABLED") == "1"

    def record(self, event: AnyEvent) -> None:
        if self.disabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = event.model_dump_json()
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception as exc:  # noqa: BLE001 - never raise from telemetry
            # Print once, don't spam — this is best-effort.
            print(f"[metrics] failed to record event: {exc}")


_default_recorder = MetricsRecorder()


def record(event: AnyEvent) -> None:
    """Module-level convenience: write one event using the default recorder."""
    _default_recorder.record(event)


# --- agent attribution for LLM calls -----------------------------------
#
# `call_llm()` doesn't take a state argument, so we use a contextvar that the
# pipeline node wrappers set right before calling into an agent. Any LLM call
# made transitively from inside that node gets attributed.

_current_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_agent", default=None
)
_current_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_run_id", default=None
)


def set_current_agent(name: Optional[str], run_id: Optional[str] = None) -> Any:
    """Set the active agent name (and optionally run_id) for LLM-call attribution.

    Returns a token tuple suitable for `reset_current_agent`.
    """
    tok_name = _current_agent.set(name)
    tok_run = _current_run_id.set(run_id) if run_id is not None else None
    return (tok_name, tok_run)


def reset_current_agent(token: Any) -> None:
    tok_name, tok_run = token
    _current_agent.reset(tok_name)
    if tok_run is not None:
        _current_run_id.reset(tok_run)


def current_agent() -> tuple[Optional[str], Optional[str]]:
    """Return (agent_name, run_id) for the active LLM-call context."""
    return _current_agent.get(), _current_run_id.get()
