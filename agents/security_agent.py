"""
Security Agent.

Detects security vulnerabilities (OWASP Top-10 / CWE classes) and emits
structured `Finding` objects. Uses the LLM backend with a security-focused
prompt that asks for CWE identifiers so findings are grounded and citable.

(The project roadmap includes a fine-tuned CodeBERT classifier for this role;
this LLM-based implementation is the working version and the same `analyze`
interface will hold when CodeBERT is added.)
"""

from __future__ import annotations

from agents.common import parse_findings_json
from llm.backend import call_llm
from models.schemas import Category, ReviewState

AGENT_NAME = "security_agent"

SYSTEM = (
    "You are an application security engineer specializing in Python. You find "
    "real, exploitable vulnerabilities and map each to a CWE identifier."
)

PROMPT = """Analyze the Python code below for SECURITY vulnerabilities only.
Focus on the OWASP Top 10 and common CWE classes: SQL/command injection,
hardcoded credentials/secrets, weak or plaintext password handling, unsafe
deserialization, path traversal, use of eval/exec, missing input validation,
and insecure cryptography.

Return ONLY a JSON array. Each element must have these keys:
  "line": integer line number (approximate, 1-based) or null
  "severity": one of "Critical", "High", "Medium", "Low"
  "title": short summary of the vulnerability
  "description": what is wrong and how it could be exploited
  "cwe": the CWE id like "CWE-89", or null
  "recommendation": how to fix it

If there are no security issues, return [].

CODE:
```python
{code}
```
"""


def analyze(state: ReviewState) -> ReviewState:
    """Run security analysis over the full source and record findings."""
    try:
        raw = call_llm(PROMPT.format(code=state.source_code), system=SYSTEM)
        findings = parse_findings_json(raw, AGENT_NAME, Category.SECURITY)
        state.add_findings(findings)
        print(f"[security] {len(findings)} finding(s).")
    except Exception as exc:  # noqa: BLE001 - never let one agent kill the run
        state.errors.append(f"security_agent failed: {exc}")
        print(f"[security] ERROR: {exc}")
    return state
