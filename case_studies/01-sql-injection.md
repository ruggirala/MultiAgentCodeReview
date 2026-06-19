# Case study 01 — SQL injection via string concatenation

> **Live PR:** [rahulilla/airflow#5](https://github.com/rahulilla/airflow/pull/5)
> **Posted comment:** [#issuecomment-4728345411](https://github.com/rahulilla/airflow/pull/5#issuecomment-4728345411)
> **Severity:** High · **CWE-89** · flagged for human review
> **Pipeline duration:** 64.5 s · 22 total findings on this file

## The buggy code

Appended to `airflow-core/src/airflow/utils/helpers.py`:

```python
def lookup_user(db_conn, username: str):
    cursor = db_conn.cursor()
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchall()
```

A textbook SQL injection: the username string is concatenated straight into
the query. Calling `lookup_user(conn, "alice' OR '1'='1")` returns every user
row. With a more aggressive payload an attacker drops or rewrites tables.

## What the agent posted

> ### [High] SQL Injection Vulnerability (line 249) · CWE-89
> The code constructs an SQL query by concatenating user input directly into
> the query string. This allows an attacker to inject arbitrary SQL code by
> manipulating the `'username'` parameter, potentially leading to unauthorized
> data access or modification.
>
> **Fix:** Use parameterized queries or prepared statements to safely include
> user input in SQL queries. For example, use
> `cursor.execute("SELECT * FROM users WHERE username = %s", (username,))`
> instead.

The triage node (`graph/pipeline.py::_triage`) saw a **Critical/High security**
finding and routed the run through the `human_review` checkpoint before the
patch agent generated the fix.

## The agent's suggested fix

The patch agent rewrote `lookup_user` to use a parameterized query — committed
to the sibling branch `loadtest/01-sqli-string-concat-agent-suggested` and
opened as a follow-up PR.

```python
def lookup_user(db_conn, username: str):
    cursor = db_conn.cursor()
    query = "SELECT * FROM users WHERE username = ?"
    cursor.execute(query, (username,))
    return cursor.fetchall()
```

The fix uses positional placeholders (`?` for sqlite3, `%s` for psycopg2) so
the database driver escapes the value, not the application.

## Why this matters

SQL injection remains in the [OWASP Top-10 2021 — A03 Injection](https://owasp.org/Top10/A03_2021-Injection/).
The pipeline didn't just flag the vulnerability — it cited the precise CWE
(89), explained the attack vector concretely (manipulating the `username`
parameter), and gave a runnable replacement. A reviewer can accept the
follow-up PR or merge a manual fix; either way they have a reproducible
report and an attribution to the line of code.

## Telemetry record

```json
{
  "type": "pr_review",
  "pr_number": 5,
  "head_sha": "37a531da9413b4d4e605b078e820b3785d27f286",
  "files_reviewed": 1,
  "total_findings": 22,
  "findings_by_severity": {"Critical": 0, "High": 7, "Medium": 6, "Low": 9},
  "findings_by_category": {"Security": 1, "Bug": 6, "Style": 13, "Performance": 2},
  "needs_human_review": true,
  "duration_sec": 64.52
}
```
