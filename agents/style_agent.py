"""
Style & Performance Agent.

Combines deterministic static analysis with LLM judgement:
- **pylint** for PEP 8 / style violations (convention, refactor, warning).
- **radon** for cyclomatic complexity (flags overly complex functions).
- An **LLM pass** for performance anti-patterns (e.g. O(n^2) loops, repeated
  work) that static tools don't catch well.

pylint and radon are invoked via their library APIs when importable; if either
is missing, that portion is skipped gracefully and the LLM pass still runs, so
the agent always produces something useful.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agents.common import parse_findings_json
from llm.backend import call_llm
from models.schemas import Category, Finding, ReviewState, Severity

AGENT_NAME = "style_agent"

# pylint message-category -> our severity
_PYLINT_SEVERITY = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "refactor": Severity.LOW,
    "convention": Severity.LOW,
    "fatal": Severity.HIGH,
}

PERF_SYSTEM = "You are a Python performance reviewer."

PERF_PROMPT = """Identify PERFORMANCE problems in the Python code below: quadratic
or worse loops, repeated recomputation, inefficient data structures, unnecessary
work inside loops. Do NOT report style or security issues.

Return ONLY a JSON array; each element has:
  "line": integer or null
  "severity": "Critical" | "High" | "Medium" | "Low"
  "title": short summary
  "description": why it is slow
  "recommendation": how to speed it up

If there are none, return [].

CODE:
```python
{code}
```
"""


def _run_pylint(source: str) -> list[Finding]:
    """Run pylint via its library API; return [] if pylint is unavailable."""
    try:
        from pylint.lint import Run
        from pylint.reporters.json_reporter import JSONReporter
    except Exception:
        return []

    import io
    import json as _json

    findings: list[Finding] = []
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(source)
        tmp_path = tmp.name

    try:
        buffer = io.StringIO()
        reporter = JSONReporter(buffer)
        # Disable the score footer; we only want messages.
        Run(
            [tmp_path, "--disable=missing-module-docstring"],
            reporter=reporter,
            exit=False,
        )
        messages = _json.loads(buffer.getvalue() or "[]")
        for m in messages:
            findings.append(
                Finding(
                    category=Category.STYLE,
                    severity=_PYLINT_SEVERITY.get(m.get("type", ""), Severity.LOW),
                    line=m.get("line"),
                    title=f"{m.get('symbol', 'pylint')}: {m.get('message-id', '')}",
                    description=m.get("message", ""),
                    recommendation=None,
                    agent=AGENT_NAME,
                )
            )
    except Exception:
        return findings
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return findings


def _run_radon(source: str) -> list[Finding]:
    """Flag functions with high cyclomatic complexity; [] if radon missing."""
    try:
        from radon.complexity import cc_visit
    except Exception:
        return []

    findings: list[Finding] = []
    try:
        for block in cc_visit(source):
            if block.complexity >= 8:  # B-grade threshold and worse
                sev = (
                    Severity.HIGH if block.complexity >= 15 else Severity.MEDIUM
                )
                findings.append(
                    Finding(
                        category=Category.PERFORMANCE,
                        severity=sev,
                        line=getattr(block, "lineno", None),
                        title=f"High cyclomatic complexity ({block.complexity})",
                        description=(
                            f"'{block.name}' has cyclomatic complexity "
                            f"{block.complexity}; consider refactoring into "
                            "smaller units."
                        ),
                        recommendation="Break the function into smaller helpers.",
                        agent=AGENT_NAME,
                    )
                )
    except Exception:
        return findings
    return findings


def _run_perf_llm(source: str) -> list[Finding]:
    raw = call_llm(PERF_PROMPT.format(code=source), system=PERF_SYSTEM)
    return parse_findings_json(raw, AGENT_NAME, Category.PERFORMANCE)


def analyze(state: ReviewState) -> ReviewState:
    """Static analysis (pylint+radon) plus an LLM performance pass."""
    try:
        findings: list[Finding] = []
        findings.extend(_run_pylint(state.source_code))
        findings.extend(_run_radon(state.source_code))
        try:
            findings.extend(_run_perf_llm(state.source_code))
        except Exception as exc:  # noqa: BLE001 - LLM pass is best-effort
            state.errors.append(f"style_agent perf pass failed: {exc}")
        state.add_findings(findings)
        print(f"[style] {len(findings)} finding(s).")
    except Exception as exc:  # noqa: BLE001
        state.errors.append(f"style_agent failed: {exc}")
        print(f"[style] ERROR: {exc}")
    return state
