"""
Recall scorer for the multi-agent code review pipeline.

Reads `load_test/status.json` (produced by the 30-PR load test) and computes
**recall on the planted bugs** — i.e. for each load-test template, did the
pipeline produce at least one finding in every category we deliberately
introduced?

Why recall and not precision: each load-test PR appends a synthetic buggy
function to a real airflow utility file. The expected category is what we
*planted*; any other findings the agent produces are on the surrounding real
code (e.g. radon catching genuine cyclomatic-complexity issues in
airflow-core). We have no ground truth for whether those surrounding
findings are valid, so labeling them as false-positives would be wrong. We
score "did we catch the bug we planted" and stop there.

This script is intentionally simple:
    python -m eval.score
prints a table to stdout and writes `eval/results.json`.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATUS_PATH = PROJECT_ROOT / "load_test" / "status.json"
RESULTS_PATH = PROJECT_ROOT / "eval" / "results.json"


def _load_runs() -> list[dict[str, Any]]:
    if not STATUS_PATH.exists():
        raise SystemExit(
            f"Cannot find {STATUS_PATH}. Run the load test first: "
            f"`python -m load_test.orchestrator`."
        )
    runs = json.loads(STATUS_PATH.read_text())["runs"]
    return [r for r in runs if r.get("status") == "ok"]


def score_run(run: dict[str, Any]) -> dict[str, Any]:
    """Score one PR review against its expected categories.

    Returns a per-template record with:
      - expected: list of categories we planted
      - actual_categories: list of categories the agent flagged at least once
      - hit: bool — did every expected category appear in actual?
      - missing: list of expected categories the agent failed to flag
    """
    expected = list(run.get("expected_findings") or [])
    fbc = run.get("findings_by_category") or {}
    actual = [cat for cat, count in fbc.items() if count > 0]
    missing = [cat for cat in expected if cat not in actual]
    return {
        "idx": run.get("idx"),
        "name": run.get("name"),
        "pr_number": run.get("pr_number"),
        "expected": expected,
        "actual": sorted(actual),
        "hit": len(missing) == 0,
        "missing": missing,
        "total_findings": run.get("total_findings", 0),
    }


def aggregate(scored: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-category and overall recall."""
    n = len(scored)
    overall_hits = sum(1 for s in scored if s["hit"])

    # Per-category: recall = (templates with this category in expected AND in actual) /
    #                       (templates with this category in expected)
    per_cat_total: Counter[str] = Counter()
    per_cat_hit: Counter[str] = Counter()
    for s in scored:
        for cat in s["expected"]:
            per_cat_total[cat] += 1
            if cat in s["actual"]:
                per_cat_hit[cat] += 1

    per_category = {
        cat: {
            "expected_count": per_cat_total[cat],
            "hit_count": per_cat_hit[cat],
            "recall": (per_cat_hit[cat] / per_cat_total[cat]) if per_cat_total[cat] else 0.0,
        }
        for cat in sorted(per_cat_total)
    }

    return {
        "templates_scored": n,
        "overall_hits": overall_hits,
        "overall_recall": (overall_hits / n) if n else 0.0,
        "per_category": per_category,
    }


def main() -> int:
    runs = _load_runs()
    scored = [score_run(r) for r in runs]
    summary = aggregate(scored)

    out = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(STATUS_PATH.relative_to(PROJECT_ROOT)),
        "summary": summary,
        "per_template": scored,
    }
    RESULTS_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # Pretty-print to stdout
    print()
    print("=" * 72)
    print(f"  RECALL EVALUATION — {summary['templates_scored']} load-test templates")
    print("=" * 72)
    print(f"  Overall recall:  {summary['overall_hits']}/{summary['templates_scored']} = {summary['overall_recall'] * 100:.1f}%")
    print()
    print(f"  {'Category':14}  {'Expected':>8}  {'Hit':>5}  {'Recall':>8}")
    print(f"  {'-' * 14}  {'-' * 8}  {'-' * 5}  {'-' * 8}")
    for cat, stats in summary["per_category"].items():
        print(
            f"  {cat:14}  {stats['expected_count']:>8d}  {stats['hit_count']:>5d}  "
            f"{stats['recall'] * 100:>7.1f}%"
        )
    print()

    misses = [s for s in scored if not s["hit"]]
    if misses:
        print(f"  Misses ({len(misses)}):")
        for m in misses:
            print(f"    - #{m['idx']} {m['name']:30}  expected={m['expected']}  missing={m['missing']}")
    else:
        print("  No misses — every planted bug-category was caught.")
    print()
    print(f"  Results written to: {RESULTS_PATH.relative_to(PROJECT_ROOT)}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
