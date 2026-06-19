# Case study 02 — Hardcoded production API key

> **Live PR:** [rahulilla/airflow#9](https://github.com/rahulilla/airflow/pull/9)
> **Severity:** High · **CWE-798** · flagged for human review
> **Pipeline duration:** 63.2 s · 25 total findings on this file

## The buggy code

Appended to `airflow-core/src/airflow/utils/helpers.py`:

```python
def call_payment_api(amount: float):
    api_key = "sk_live_4EC9aV3LzTpmf_REAL_LOOKING_SECRET_KEY"
    headers = {"Authorization": "Bearer " + api_key}
    return _post("https://api.payments.example.com/charge", amount, headers)
```

Production-style secret key checked straight into the source. `sk_live_…` is
the prefix Stripe uses for live secret keys — an LLM scanning code for leaked
credentials would fingerprint this in milliseconds, and so do most secret
scanners (GitGuardian, TruffleHog, GitHub's own secret scanning).

## What the agent posted

> ### [High] Hardcoded API Key (line 267) · CWE-798
> The API key for the payment service is hardcoded in the source code. This
> can lead to unauthorized access if the code is exposed.
>
> **Fix:** Store the API key in a secure environment variable or a secrets
> management service, and retrieve it at runtime.

The agent recognized the `sk_live_` shape as a real-looking credential, not a
placeholder, and escalated severity to High. CWE-798 ("Use of Hard-coded
Credentials") is the precise classification.

## The agent's suggested fix

```python
import os

def call_payment_api(amount: float):
    api_key = os.environ.get("PAYMENT_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PAYMENT_API_KEY environment variable is not set"
        )
    headers = {"Authorization": f"Bearer {api_key}"}
    return _post("https://api.payments.example.com/charge", amount, headers)
```

The patch swaps the literal for an environment lookup, fails loudly if it's
unset (better than silently sending requests with `Bearer None`), and tightens
the string concat to an f-string.

## Why this matters

GitHub's [2024 Octoverse on secret leaks](https://docs.github.com/en/code-security/secret-scanning/about-secret-scanning)
reports tens of thousands of valid credentials leaked into public repos
weekly. Once a secret hits a public commit, rotation is the only remediation
— scrubbing the history doesn't help because clones already exist. Catching
the secret **at PR review time, before merge** is the only effective gate.

A multi-agent reviewer catches this without depending on a separate secret-
scanner running asynchronously. The finding includes the CWE attribution and
the exact remediation, so a reviewer doesn't have to context-switch to figure
out what to do.

## Telemetry record

```json
{
  "type": "pr_review",
  "pr_number": 9,
  "files_reviewed": 1,
  "total_findings": 25,
  "needs_human_review": true,
  "duration_sec": 63.2
}
```
