# Evaluation

Recall measurement for the multi-agent code review pipeline against the 30
load-test templates.

## What's measured

For each load-test template (`load_test/buggy_templates.py`), we know the
**category we deliberately planted** (e.g. SQL injection → Security; mutable
default arg → Bug). The scorer asks one question per template:

> Did the pipeline produce at least one finding in every expected category?

If yes, that template is a **hit**. Aggregating across all 30 templates gives
overall and per-category recall.

## Result (current run)

| Category | Expected | Hit | Recall |
|---|---|---|---|
| Security | 10 | 10 | 100% |
| Bug | 10 | 10 | 100% |
| Performance | 5 | 5 | 100% |
| Style | 6 | 6 | 100% |
| **Overall** | **30** | **30** | **100%** |

`results.json` has the per-template breakdown.

## What this is not

**It's not precision.** Each load-test PR appends a synthetic buggy function
to a real airflow utility file, so the agent sees both the planted bug *and*
the real surrounding code. Findings on the surrounding code are typically
valid (e.g. radon catching genuine cyclomatic-complexity issues in
airflow-core) but we have no ground truth for them. Counting them as false-
positives would be wrong; counting them as true-positives would inflate the
score. We just don't measure precision here.

**It's not granular.** A "Security hit" means *some* Security finding fired,
not necessarily that the *exact* planted CWE was attributed. Hand-spot-checks
on 8 representative templates confirm 7 of 8 cited the precise CWE
(CWE-89 / 78 / 502 / 798 / 327 / 582 / O(n²) / cyclomatic). The 8th was a
local-grep miss, not an actual missed bug — verified separately in PR #5.

**It's not on a public benchmark.** We considered CodeXGLUE (Devign for
defect detection, Bugs2Fix for refinement) but neither matches our pipeline
shape — Devign is C function-level binary classification; our agents produce
structured findings on Python files. Adapting to either would measure the
adapter as much as the agent. Internal benchmark on our own templates is
the more honest deliverable.

## How to run

```bash
python -m eval.score
```

Reads `load_test/status.json`, prints a table to stdout, writes
`eval/results.json`. Deterministic — same input produces the same output.

Re-run the load test (`python -m load_test.orchestrator`) first if you want
fresh numbers from a new pipeline run; the scorer just measures the latest
`status.json`.

## Files

- `score.py` — the scorer
- `results.json` — generated; committed so the slide numbers are reproducible
- this README
