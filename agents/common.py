"""
Shared helpers for agents.

The analysis agents (security, bug) ask the LLM for findings as JSON. LLMs are
not perfectly reliable JSON emitters, so `parse_findings_json` is defensive: it
strips markdown fences, finds the JSON array, and skips malformed entries rather
than crashing the whole pipeline.
"""

from __future__ import annotations

import json
import re
from typing import Any

from models.schemas import Category, Finding, Severity


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding ```json ... ``` or ``` ... ``` fence if present."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text.strip()


def _extract_json_array(text: str) -> str | None:
    """Return the first top-level [...] JSON array substring, if any."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + 1]


def _coerce_category(value: Any, default: Category) -> Category:
    try:
        return Category(str(value).capitalize())
    except (ValueError, AttributeError):
        return default


def _coerce_severity(value: Any) -> Severity:
    try:
        return Severity(str(value).capitalize())
    except (ValueError, AttributeError):
        return Severity.MEDIUM


def parse_findings_json(
    raw: str,
    agent_name: str,
    default_category: Category,
) -> list[Finding]:
    """
    Parse an LLM response into a list of Finding objects.

    Tolerant of fences, prose around the JSON, and missing/odd fields. Entries
    that can't be parsed at all are skipped (and counted nowhere — best effort).
    """
    cleaned = _strip_code_fence(raw)
    array_text = _extract_json_array(cleaned) or cleaned

    try:
        data = json.loads(array_text)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        # Some models wrap the list, e.g. {"findings": [...]}.
        for key in ("findings", "issues", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]

    if not isinstance(data, list):
        return []

    findings: list[Finding] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        line = item.get("line")
        try:
            line = int(line) if line is not None else None
        except (ValueError, TypeError):
            line = None
        findings.append(
            Finding(
                category=_coerce_category(item.get("category"), default_category),
                severity=_coerce_severity(item.get("severity")),
                line=line,
                title=str(item.get("title") or item.get("issue") or "Untitled issue"),
                description=str(item.get("description") or item.get("why") or ""),
                cwe=(str(item["cwe"]) if item.get("cwe") else None),
                recommendation=(
                    str(item["recommendation"])
                    if item.get("recommendation")
                    else None
                ),
                agent=agent_name,
            )
        )
    return findings


def extract_code_block(text: str, lang: str = "python") -> str | None:
    """Pull the last fenced code block out of an LLM response (the fixed code)."""
    marker = f"```{lang}"
    start = text.rfind(marker)
    if start == -1:
        # try a bare fence
        start = text.rfind("```")
        if start == -1:
            return None
        start += 3
    else:
        start += len(marker)
    end = text.find("```", start)
    if end == -1:
        return None
    return text[start:end].strip()
