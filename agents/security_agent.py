"""
Security Agent.

Detects security vulnerabilities (OWASP Top-10 / CWE classes) and emits
structured `Finding` objects. Uses the LLM backend with a security-focused
prompt that asks for CWE identifiers so findings are grounded and citable.

**Optional RAG grounding:** when `USE_RAG=1` is set in the environment, this
agent retrieves the most relevant OWASP/CWE entries from a ChromaDB index
(see `rag/retriever.py`) and splices them into the prompt. The model then
labels findings with real CWE IDs from a known list instead of guessing,
producing more grounded and consistent output.

RAG is OFF by default to keep the watcher and CLI runnable without the heavy
chromadb / sentence-transformers dependencies. Turn it on in the Colab
notebook where those deps are pre-installed.

(The project roadmap also includes a fine-tuned CodeBERT classifier for this
role; both upgrades preserve the `analyze` interface.)
"""

from __future__ import annotations

import os

from llm.backend import call_llm_structured
from models.schemas import Category, Finding, FindingsResponse, ReviewState

AGENT_NAME = "security_agent"

SYSTEM = (
    "You are an application security engineer specializing in Python. You find "
    "real, exploitable vulnerabilities and map each to a CWE identifier."
)

# JSON shape is enforced server-side via OpenAI Structured Outputs
# (see llm.backend.call_llm_structured). The prompt focuses on WHAT to
# look for, not the response format.
PROMPT_TEMPLATE = """{rag_context}Analyze the Python code below for SECURITY vulnerabilities only.
Focus on the OWASP Top 10 and common CWE classes: SQL/command injection,
hardcoded credentials/secrets, weak or plaintext password handling, unsafe
deserialization, path traversal, use of eval/exec, missing input validation,
and insecure cryptography.

Set every finding's `category` to "Security" and populate `cwe` (e.g. "CWE-89")
when the issue maps to a known weakness class. If there are no security issues,
return an empty findings array.

CODE:
```python
{code}
```
"""

# Kept for backwards compatibility with anything that imported `PROMPT`.
PROMPT = PROMPT_TEMPLATE.replace("{rag_context}", "")


def _maybe_rag_context(code: str) -> str:
    """
    Retrieve relevant OWASP/CWE entries for ``code`` and format as a prompt
    prefix. Returns an empty string when RAG is disabled or unavailable.
    """
    if os.environ.get("USE_RAG") != "1":
        return ""
    try:
        from rag.retriever import format_context, get_retriever

        # Top-4 hits keyed off the source code itself — the embedder picks up
        # idioms (sqlite3.connect, pickle.loads, etc.) that match CWE entries.
        hits = get_retriever().query(code, k=4)
        ctx = format_context(hits)
        if not ctx:
            return ""
        return ctx + "\n\n"
    except Exception as exc:  # noqa: BLE001 - never block the agent on RAG errors
        print(f"[security] RAG lookup failed (continuing without): {exc}")
        return ""


def analyze(state: ReviewState) -> ReviewState:
    """Run security analysis over the full source and record findings."""
    try:
        rag_context = _maybe_rag_context(state.source_code)
        prompt = PROMPT_TEMPLATE.format(
            rag_context=rag_context, code=state.source_code
        )
        response = call_llm_structured(prompt, FindingsResponse, system=SYSTEM)
        findings = [
            Finding(
                category=w.category if w.category else Category.SECURITY,
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
        rag_note = " (RAG-grounded)" if rag_context else ""
        print(f"[security] {len(findings)} finding(s){rag_note}.")
    except Exception as exc:  # noqa: BLE001 - never let one agent kill the run
        state.errors.append(f"security_agent failed: {exc}")
        print(f"[security] ERROR: {exc}")
    return state
