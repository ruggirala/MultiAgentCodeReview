"""
Bug Detection Agent.

Finds logical errors and runtime faults (not style, not security) using
chain-of-thought prompting: the model is asked to reason step by step about
control flow and edge cases, then emit structured `Finding` objects.
"""

from __future__ import annotations

from llm.backend import call_llm_structured
from models.schemas import Category, Finding, FindingsResponse, ReviewState

AGENT_NAME = "bug_agent"

SYSTEM = (
    "You are a meticulous Python developer who finds logic bugs and runtime "
    "errors by reasoning carefully about edge cases and control flow."
)

# Note: the JSON shape is enforced server-side via OpenAI Structured Outputs
# (see call_llm_structured). The prompt no longer needs to describe field
# names — the schema does that work. We keep the WHAT-to-look-for guidance
# since that's content, not shape.
PROMPT = """Find logical BUGS and runtime errors in the Python code below.
Look for: unhandled edge cases (empty inputs, division by zero), uninitialized
or missing attributes, resource leaks (files/connections not closed), incorrect
conditionals, off-by-one errors, bare excepts that swallow errors, and mutable
default arguments. Do NOT report pure style or security issues here.

Set every finding's `category` to "Bug". Severity must be one of Critical,
High, Medium, Low. If there are no bugs, return an empty findings array.

CODE:
```python
{code}
```
"""


def analyze(state: ReviewState) -> ReviewState:
    """Run bug analysis over the full source and record findings."""
    try:
        response = call_llm_structured(
            PROMPT.format(code=state.source_code),
            FindingsResponse,
            system=SYSTEM,
        )
        findings = [
            Finding(
                category=w.category if w.category else Category.BUG,
                severity=w.severity,
                line=w.line,
                title=w.title,
                description=w.description,
                cwe=w.cwe,
                recommendation=w.recommendation,
                agent=AGENT_NAME,
            )
            for w in response.findings
        ]
        state.add_findings(findings)
        print(f"[bug] {len(findings)} finding(s).")
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"bug_agent failed: {exc}")
        print(f"[bug] ERROR: {exc}")
    return state
