"""
Patch Generation Agent.

Consumes the accumulated findings and the original source, then asks the LLM to
produce a single corrected version of the file. Output is wrapped in a
structured `PatchProposal` (summary + fixed code + which findings it addresses).
"""

from __future__ import annotations

from agents.common import extract_code_block
from llm.backend import call_llm
from models.schemas import PatchProposal, ReviewState

AGENT_NAME = "patch_agent"

SYSTEM = (
    "You are a senior Python engineer who fixes code while preserving its public "
    "behavior and interfaces."
)

PROMPT = """You are given Python code and a list of issues found by reviewers.
Produce a corrected version of the ENTIRE file that resolves the issues without
changing intended functionality or public function/class signatures.

Apply these fixes where relevant: parameterized SQL, context managers for files,
guards for empty inputs / missing attributes, specific exception handling,
PascalCase class names, secure password handling, and efficient algorithms.

Respond with:
1. A one-paragraph summary of the changes you made.
2. The complete fixed file inside a single ```python code block.

ISSUES FOUND:
{findings}

ORIGINAL CODE:
```python
{code}
```
"""


def _format_findings(state: ReviewState) -> str:
    if not state.findings:
        return "(no issues were reported)"
    lines = []
    for i, f in enumerate(state.findings, 1):
        loc = f"line {f.line}" if f.line else "general"
        lines.append(
            f"{i}. [{f.category.value}/{f.severity.value}] ({loc}) "
            f"{f.title} — {f.description}"
        )
    return "\n".join(lines)


def generate(state: ReviewState) -> ReviewState:
    """Produce a PatchProposal and attach it to the state."""
    try:
        prompt = PROMPT.format(
            findings=_format_findings(state), code=state.source_code
        )
        raw = call_llm(prompt, system=SYSTEM)
        fixed = extract_code_block(raw, "python")

        if not fixed:
            # No usable code block — keep original, record the issue.
            state.errors.append("patch_agent: could not extract fixed code")
            fixed = state.source_code
            summary = "Patch generation did not return a usable code block."
        else:
            # The text before the first code fence is the summary, if any.
            summary = raw.split("```")[0].strip() or "Applied fixes for reported issues."

        state.patch = PatchProposal(
            summary=summary,
            fixed_code=fixed,
            addressed_findings=[f.title for f in state.findings],
        )
        print("[patch] proposal generated.")
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"patch_agent failed: {exc}")
        print(f"[patch] ERROR: {exc}")
    return state
