# Case study 04 — Quadratic string concatenation in a loop

> **Live PR:** [rahulilla/airflow#27](https://github.com/rahulilla/airflow/pull/27)
> **Severity:** Low (Performance)
> **Pipeline duration:** 22.7 s · 5 total findings on this file (the fastest review of all 30)

## The buggy code

Appended to `airflow-core/src/airflow/utils/strings.py`:

```python
def join_lines(lines: list) -> str:
    result = ""
    for line in lines:
        result = result + line + "\n"
    return result
```

CPython's `str` is immutable, so `result + line + "\n"` allocates a fresh
string each iteration. For an N-element input the function does O(N) string
allocations, each of which copies the growing buffer — total work O(N²).
On 10K log lines averaging 80 chars each, this takes ~1.6 s. The Pythonic
`'\n'.join(lines)` does it in ~3 ms.

CPython has a peephole optimization that detects **simple `s = s + …`**
loops and avoids the quadratic blowup, but only when there's exactly one
binding to `s` and the operand is a single string. Our buggy version's
`result + line + "\n"` (two `+`'s, two operands beyond `result`) defeats it.

## What the agent posted

> ### [Low] Inefficient string concatenation (line 30)
> The `join_lines` function concatenates strings in a loop, which can be
> inefficient due to the creation of many intermediate string objects.
>
> **Fix:** Use `str.join()` method: `return '\n'.join(lines) + '\n'`.

The fix replaces the entire loop with one expression. The performance agent
caught this even though `pylint` and `radon` typically don't flag it (it's
not a complexity issue, it's a hot-path constant-factor issue).

## The agent's suggested fix

```python
def join_lines(lines: list) -> str:
    return "\n".join(lines) + "\n"
```

Three characters of rewrite. Same semantics. ~500× faster on 10K lines.

## Why this matters

This is the agent doing *performance* work, not just correctness. There are
no security implications and no functional bugs — the function returns the
right string, just slowly. A reviewer skimming a diff would likely accept
this code without comment. The agent flags it as Low severity (correctly —
it's not blocking) but documents the issue and offers a one-line remediation
the human can take or leave.

This is also why the four-agent split matters. A single-prompt reviewer
trying to do everything would either flag the issue or quietly miss it.
A dedicated performance pass that has been told *"look for algorithmic
anti-patterns and inefficient idioms"* surfaces it consistently.

## Telemetry record

```json
{
  "type": "pr_review",
  "pr_number": 27,
  "files_reviewed": 1,
  "total_findings": 5,
  "findings_by_category": {"Security": 0, "Bug": 0, "Style": 4, "Performance": 1},
  "duration_sec": 22.7
}
```
