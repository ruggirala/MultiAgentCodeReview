# Case study 05 — Pathological cyclomatic complexity

> **Live PR:** [rahulilla/airflow#30](https://github.com/rahulilla/airflow/pull/30)
> **Severity:** Medium (Style/maintainability)
> **Pipeline duration:** 62.9 s · 32 total findings on this file (most findings of any load-test PR)

## The buggy code

Appended to `airflow-core/src/airflow/utils/helpers.py`. Trimmed for length —
the full version has 28 returns across 7 levels of nesting:

```python
def classify_priority(score: int, urgent: bool, paid: bool, region: str, tier: int) -> str:
    if urgent:
        if paid:
            if score > 90:
                return "critical-paid-urgent"
            elif score > 70:
                if region == "US" or region == "EU":
                    if tier > 2:
                        return "high-paid-urgent-tier"
                    else:
                        return "high-paid-urgent"
                else:
                    return "high-paid-urgent-rest"
            else:
                return "medium-paid-urgent"
        else:
            ...   # 16 more lines of nested else branches
```

This compiles, runs, and produces correct outputs. But the
**cyclomatic complexity is 14** — the number of independent paths through
the function. A function this branchy is unreviewable: the diff that
introduces a subtle classification bug looks identical to one that doesn't.

## What the agent posted (two findings, complementary)

The Style agent (via `radon`) caught the structural problem:

> ### [Medium] High cyclomatic complexity (14) (line 325)
> `classify_priority` has cyclomatic complexity 14; consider refactoring into
> smaller units.
>
> **Fix:** Break the function into smaller helpers.

The Bug agent (via GPT-4o chain-of-thought) caught the *semantic* hole:

> ### [Low] Incorrect condition in classify_priority (line 328)
> In the `classify_priority` function, the condition for checking the region
> is `'US'` or `'EU'` is not exhaustive. If the region is not `'US'` or `'EU'`,
> it defaults to `'high-paid-urgent-rest'`, which may not be the intended
> behavior.
>
> **Fix:** Consider explicitly handling all possible region values or adding
> a default case to handle unexpected regions.

Two agents, two completely different angles on the same function. The first
is a structural metric (radon counts decision points); the second is the LLM
reasoning about the code's *intent*.

## The agent's suggested fix

The patch agent refactored to a table-driven lookup:

```python
_PRIORITY_TABLE = {
    # (urgent, paid, score_band, region_band, tier_band) → priority
    (True, True, "high",   "primary",   "high"): "high-paid-urgent-tier",
    (True, True, "high",   "primary",   "low"):  "high-paid-urgent",
    (True, True, "high",   "rest",      "any"):  "high-paid-urgent-rest",
    (True, True, "medium", "any",       "any"):  "medium-paid-urgent",
    # ... etc
}

def classify_priority(score, urgent, paid, region, tier):
    score_band  = "high"   if score > 70 else "medium" if score > 50 else "low"
    region_band = "primary" if region in ("US", "EU") else "rest"
    tier_band   = "high"   if tier > 2 else "low"
    key = (urgent, paid, score_band, region_band, tier_band)
    return _PRIORITY_TABLE.get(key, "low-default")
```

Cyclomatic complexity of the rewritten function: **3**. The decision logic
moves into data, where it can be tested table-by-table.

## Why this matters

This case study shows two value propositions of the multi-agent system that
either agent alone can't deliver:

1. **Combining static analysis with LLM reasoning.** `radon` saw the metric
   blow past threshold. GPT-4o saw an actual logic gap (unhandled regions).
   Either signal alone would underrepresent the problem; together they
   triangulate.

2. **The patch agent generates non-trivial refactors, not just fixes.** The
   suggested rewrite is structurally different from the input — table-driven,
   not nested-conditional. A linter telling you "complexity 14, refactor"
   leaves a human to invent the rewrite. The agent ships a candidate.

This was the highest-finding PR of the load test (32 findings). The pipeline
processed all 32 in 62.9 s and produced a runnable patched version, on the
sibling branch, ready for review.

## Telemetry record

```json
{
  "type": "pr_review",
  "pr_number": 30,
  "files_reviewed": 1,
  "total_findings": 32,
  "findings_by_severity": {"Critical": 0, "High": 6, "Medium": 8, "Low": 18},
  "findings_by_category": {"Security": 1, "Bug": 5, "Style": 22, "Performance": 4},
  "needs_human_review": true,
  "duration_sec": 62.9
}
```
