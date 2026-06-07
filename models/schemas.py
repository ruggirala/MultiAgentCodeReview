"""
Pydantic v2 schemas shared across the multi-agent pipeline.

Every agent reads from and writes to a single `ReviewState` object. Agents never
exchange free-form strings between each other — only structured, validated data.
This keeps the LangGraph pipeline deterministic and testable.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    """Which dimension a finding belongs to. Mirrors the four review angles."""

    SECURITY = "Security"
    BUG = "Bug"
    STYLE = "Style"
    PERFORMANCE = "Performance"


class Severity(str, Enum):
    """Impact ranking for a finding. Drives routing (Critical -> human review)."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

    @property
    def rank(self) -> int:
        """Numeric rank for sorting/threshold checks (higher = more severe)."""
        return {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}[self.value]


class Finding(BaseModel):
    """A single issue discovered by an analysis agent."""

    category: Category
    severity: Severity
    line: Optional[int] = Field(
        default=None, description="Approximate 1-based line number in the source."
    )
    title: str = Field(description="Short one-line summary of the issue.")
    description: str = Field(description="What is wrong and why it matters.")
    cwe: Optional[str] = Field(
        default=None, description="CWE identifier, e.g. 'CWE-89', when applicable."
    )
    recommendation: Optional[str] = Field(
        default=None, description="Suggested remediation."
    )
    agent: str = Field(
        default="unknown", description="Name of the agent that produced this finding."
    )


class CodeChunk(BaseModel):
    """A logical unit of code (function/class/module) produced by the Orchestrator."""

    name: str = Field(description="Symbol name, e.g. 'get_user_data' or '<module>'.")
    kind: str = Field(description="One of: function, class, module.")
    start_line: int
    end_line: int
    source: str = Field(description="The raw source text of this chunk.")


class PatchProposal(BaseModel):
    """Structured output of the Patch Generation agent."""

    summary: str = Field(description="Human-readable summary of what was changed.")
    fixed_code: str = Field(description="The complete corrected source file.")
    addressed_findings: list[str] = Field(
        default_factory=list,
        description="Titles of findings this patch resolves.",
    )


class GeneratedTest(BaseModel):
    """Structured output of the Test Generation agent."""

    framework: str = Field(default="pytest")
    test_code: str = Field(description="A runnable pytest module as text.")
    covered_functions: list[str] = Field(default_factory=list)


class ReviewState(BaseModel):
    """
    Shared state threaded through the LangGraph pipeline.

    Each node receives the state, does its work, and returns an updated copy.
    Optional fields start empty and get populated as the pipeline progresses.
    """

    # --- inputs ---
    file_name: str
    source_code: str

    # --- orchestrator output ---
    chunks: list[CodeChunk] = Field(default_factory=list)

    # --- analysis agent outputs ---
    findings: list[Finding] = Field(default_factory=list)

    # --- downstream outputs ---
    patch: Optional[PatchProposal] = None
    tests: Optional[GeneratedTest] = None

    # --- control / bookkeeping ---
    needs_human_review: bool = False
    errors: list[str] = Field(default_factory=list)

    def add_findings(self, new: list[Finding]) -> None:
        """Append findings, ignoring Nones from failed parses."""
        self.findings.extend(f for f in new if f is not None)

    def critical_security_findings(self) -> list[Finding]:
        """Critical or High security issues that warrant a human-in-the-loop pause."""
        return [
            f
            for f in self.findings
            if f.category == Category.SECURITY
            and f.severity in (Severity.CRITICAL, Severity.HIGH)
        ]

    def findings_by_category(self) -> dict[str, list[Finding]]:
        """Group findings by category name for reporting."""
        grouped: dict[str, list[Finding]] = {}
        for f in self.findings:
            grouped.setdefault(f.category.value, []).append(f)
        return grouped
