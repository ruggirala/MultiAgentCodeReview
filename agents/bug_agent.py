"""
Bug Detection Agent.

Finds logical errors and runtime faults (not style, not security) using
chain-of-thought prompting: the model is asked to reason step by step about
control flow and edge cases, then emit structured `Finding` objects.
"""

from __future__ import annotations

from agents.common import parse_findings_json
from llm.backend import call_llm
from models.schemas import Category, ReviewState

AGENT_NAME = "bug_agent"

SYSTEM = (
    "You are a meticulous Python developer who finds logic bugs and runtime "
    "errors by reasoning carefully about edge cases and control flow."
)

PROMPT = """Find logical BUGS and runtime errors in the Python code below.
Look for: unhandled edge cases (empty inputs, division by zero), uninitialized
or missing attributes, resource leaks (files/connections not closed), incorrect
conditionals, off-by-one errors, bare excepts that swallow errors, and mutable
default arguments. Do NOT report pure style or security issues here.

First think step by step about how the code could fail. Then return ONLY a JSON
array (your reasoning must NOT appear outside the array). Each element has:
  "line": integer line number (approximate, 1-based) or null
  "severity": one of "Critical", "High", "Medium", "Low"
  "title": short summary of the bug
  "description": the failure scenario and why it happens
  "recommendation": how to fix it

If there are no bugs, return [].

CODE:
```python
{code}
```
"""


def analyze(state: ReviewState) -> ReviewState:
    """Run bug analysis over the full source and record findings."""
    try:
        raw = call_llm(PROMPT.format(code=state.source_code), system=SYSTEM)
        findings = parse_findings_json(raw, AGENT_NAME, Category.BUG)
        state.add_findings(findings)
        print(f"[bug] {len(findings)} finding(s).")
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"bug_agent failed: {exc}")
        print(f"[bug] ERROR: {exc}")
    return state
