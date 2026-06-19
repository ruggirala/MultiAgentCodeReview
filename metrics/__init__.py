"""Telemetry for the multi-agent code review pipeline.

A small, dependency-free emission layer:

    metrics.recorder.record(event)  # appends one JSON line to runs/events.jsonl

Every event is a Pydantic model with a `type` discriminator, so the dashboard
can dispatch on type when reading. See `metrics/recorder.py`.
"""

from metrics.recorder import (
    AgentEvent,
    LLMCallEvent,
    MetricsRecorder,
    PRReviewEvent,
    PollCycleEvent,
    current_agent,
    record,
    reset_current_agent,
    set_current_agent,
)

__all__ = [
    "AgentEvent",
    "LLMCallEvent",
    "MetricsRecorder",
    "PRReviewEvent",
    "PollCycleEvent",
    "current_agent",
    "record",
    "reset_current_agent",
    "set_current_agent",
]
