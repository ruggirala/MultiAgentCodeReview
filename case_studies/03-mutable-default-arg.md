# Case study 03 — Mutable default argument

> **Live PR:** [rahulilla/airflow#15](https://github.com/rahulilla/airflow/pull/15)
> **Severity:** Medium · **CWE-582**
> **Pipeline duration:** 84.6 s · 22 total findings on this file

## The buggy code

Appended to `airflow-core/src/airflow/utils/helpers.py`:

```python
def append_log_entry(msg: str, log: list = []) -> list:
    log.append(msg)
    return log
```

The classic Python footgun: `log: list = []` is evaluated **once at function
definition**, not on each call. Every invocation that doesn't pass an
explicit `log` argument shares the same list:

```python
>>> append_log_entry("hello")
['hello']
>>> append_log_entry("world")
['hello', 'world']      # surprise — leaked from the previous call
```

In a long-running service this manifests as memory growing unbounded and
state leaking between requests. The bug typically only surfaces in
production traffic and is notoriously hard to attribute.

## What the agent posted

> ### [Medium] Mutable Default Argument (line 157) · CWE-582
> The function `append_log_entry` uses a mutable default argument `log` which
> is a list. This can lead to unexpected behavior because the same list is
> used across multiple calls to the function, potentially leading to data
> leakage or corruption.
>
> **Fix:** Use `None` as the default value for the `log` parameter and
> initialize it inside the function if it is `None`.

CWE-582 ("Array Declared Public, Final, and Static") is the canonical
classification for shared-mutable-state-via-default. The agent recognized
the language-specific Python idiom and articulated the failure mode
("the same list is used across multiple calls") in one sentence.

## The agent's suggested fix

```python
def append_log_entry(msg: str, log: list | None = None) -> list:
    if log is None:
        log = []
    log.append(msg)
    return log
```

The standard Python remediation: default to `None`, allocate inside the
function. Each call now gets a fresh list when the caller doesn't supply
one.

## Why this matters

The Bug agent caught this *without* the security agent's CWE database — the
chain-of-thought prompt against GPT-4o reasons about Python semantics
directly. The finding shows the multi-agent split is doing real work:
security agents focus on injection/auth/secrets; bug agents focus on
language-level correctness.

This kind of bug never trips a SAST tool because it's syntactically valid
and locally indistinguishable from intentional code. Catching it requires
understanding *Python's evaluation model*, which is exactly the affordance
an LLM-based reviewer has over rule-based linters.

## Telemetry record

```json
{
  "type": "pr_review",
  "pr_number": 15,
  "files_reviewed": 1,
  "total_findings": 22,
  "findings_by_category": {"Security": 0, "Bug": 5, "Style": 16, "Performance": 1},
  "needs_human_review": false,
  "duration_sec": 84.6
}
```

`needs_human_review: false` because no Critical/High **security** finding —
the bug is a correctness issue, not an attack vector. The agent classified
it correctly.
