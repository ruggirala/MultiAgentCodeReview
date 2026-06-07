"""
Multi-Agent Code Review — CLI entrypoint.

Runs the full LangGraph pipeline over a Python file and writes:
  - <name>_review.md     (the structured report)
  - <name>_fixed.py      (the patched code)
  - test_<name>          (generated pytest suite)
  - <name>_review.zip    (all of the above, bundled)

Usage:
    python run_pipeline.py sample_bad_code.py
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

from graph.pipeline import run_pipeline
from models.schemas import ReviewState

_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def build_report(state: ReviewState) -> str:
    """Render the findings + patch summary as a Markdown report."""
    lines: list[str] = []
    lines.append(f"# Code Review Report — `{state.file_name}`\n")

    total = len(state.findings)
    lines.append(f"**{total} finding(s)** across {len(state.chunks)} code chunk(s).\n")

    if state.needs_human_review:
        lines.append("> ⚠️ **Critical security findings flagged for human review.**\n")

    grouped = state.findings_by_category()
    for category in ("Security", "Bug", "Performance", "Style"):
        items = grouped.get(category, [])
        if not items:
            continue
        lines.append(f"\n## {category} ({len(items)})\n")
        items = sorted(items, key=lambda f: _SEVERITY_ORDER.get(f.severity.value, 9))
        for f in items:
            loc = f"line {f.line}" if f.line else "general"
            cwe = f" · {f.cwe}" if f.cwe else ""
            lines.append(f"### [{f.severity.value}] {f.title} ({loc}){cwe}")
            lines.append(f"{f.description}")
            if f.recommendation:
                lines.append(f"\n**Fix:** {f.recommendation}")
            lines.append("")

    if state.patch:
        lines.append("\n## Patch Summary\n")
        lines.append(state.patch.summary)

    if state.errors:
        lines.append("\n## Pipeline Notes\n")
        for e in state.errors:
            lines.append(f"- {e}")

    return "\n".join(lines) + "\n"


def write_outputs(state: ReviewState) -> dict[str, str]:
    """Write report, fixed code, and tests to disk; bundle into a ZIP."""
    stem = Path(state.file_name).stem
    outputs: dict[str, str] = {}

    report_path = f"{stem}_review.md"
    Path(report_path).write_text(build_report(state), encoding="utf-8")
    outputs["report"] = report_path

    if state.patch:
        fixed_path = f"{stem}_fixed.py"
        Path(fixed_path).write_text(state.patch.fixed_code, encoding="utf-8")
        outputs["fixed"] = fixed_path

    if state.tests:
        test_path = f"test_{stem}.py"
        Path(test_path).write_text(state.tests.test_code, encoding="utf-8")
        outputs["tests"] = test_path

    zip_path = f"{stem}_review.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in outputs.values():
            zf.write(p)
    outputs["zip"] = zip_path

    return outputs


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python run_pipeline.py <path_to_python_file>")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    if not filepath.exists() or filepath.suffix != ".py":
        print(f"Error: expected an existing .py file, got '{filepath}'")
        sys.exit(1)

    source = filepath.read_text(encoding="utf-8")
    print(f"\n{'=' * 60}\n  MULTI-AGENT CODE REVIEW\n  File: {filepath}\n{'=' * 60}\n")

    state = run_pipeline(filepath.name, source)

    print("\n" + build_report(state))
    outputs = write_outputs(state)
    print("\nWrote:")
    for label, path in outputs.items():
        print(f"  {label:8} -> {path}")


if __name__ == "__main__":
    main()
