# Multi-Agent Code Review & Auto-Debugging System

An AI-powered multi-agent system that reviews Python code from multiple angles
(security, bugs, style, performance), proposes fixes, and generates test cases.
It can review a local file or a **live GitHub pull request** and post its analysis
back as a PR comment.

> **Slides:** [rahulilla.github.io/MultiAgentCodeReview](https://rahulilla.github.io/MultiAgentCodeReview/) — 10-slide deck on architecture, telemetry, and load-test results.

## Architecture

A [LangGraph](https://github.com/langchain-ai/langgraph) state machine orchestrates
six agents over a shared Pydantic state object:

```
Orchestrator → Security → Bug → Style/Perf → Triage → [Human review] → Patch → Tests
```

- **Orchestrator** — parses code into logical chunks (tree-sitter, with a stdlib
  `ast` fallback).
- **Security** — detects OWASP/CWE vulnerabilities.
- **Bug** — finds logic and runtime errors via chain-of-thought.
- **Style & Performance** — pylint + radon, plus an LLM performance pass.
- **Triage** — routes Critical/High security findings to a human-review checkpoint.
- **Patch** — produces a corrected version of the file.
- **Tests** — generates a pytest suite.

### LLM backend (hybrid)

`llm/backend.py` selects a backend automatically:

- **GPT-4o** when an OpenAI key is available (best quality) — primary/dev path.
- **CodeLlama-7B-Instruct (4-bit)** as a keyless local fallback so the system runs
  with no API key (e.g. on a Colab T4 GPU).

Override with `LLM_BACKEND=auto|openai|codellama`.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then add your keys
```

`.env`:

```
OPENAI_API_KEY=sk-...
GITHUB_TOKEN=ghp_...        # only needed for PR review / posting comments
```

## Quick start

One script starts both the PR watcher and the Streamlit dashboard, with
clean Ctrl-C teardown for both:

```bash
# From the repo root:
./scripts/start.sh                                # watch the airflow fork (default)
./scripts/start.sh rahulilla/python-simple-webapp # different repo
./scripts/start.sh rahulilla/airflow --interval 15
```

The dashboard opens at <http://localhost:8501>. Each child's stdout is
tee'd to `logs/watcher.log` and `logs/dashboard.log` and printed in this
terminal with a colored prefix.

### Run from anywhere

Symlink the wrapper into your `$PATH`:

```bash
ln -s "$(pwd)/scripts/macr-start" ~/.local/bin/macr-start
```

Now `macr-start` works from any directory:

```bash
macr-start                                  # finds the project automatically
macr-start rahulilla/python-simple-webapp
```

It locates the project by walking up from `$PWD`, then checking
`$MULTIAGENTCODEREVIEW_DIR`, `~/AI_Training`, and a couple of other
common spots. Set `MULTIAGENTCODEREVIEW_DIR` if your checkout lives
elsewhere.

## Usage

### Review a local file

```bash
python run_pipeline.py sample_bad_code.py
```

Writes `<name>_review.md`, `<name>_fixed.py`, a pytest suite, and a `.zip` bundle.

### Review a GitHub PR

```bash
python review_pr.py https://github.com/<owner>/<repo>/pull/<n>
python review_pr.py <pr_url> --comment        # also post a summary comment
```

### Auto-review new PRs (live watcher)

The watcher polls a repo and, the moment a new PR is opened, runs the full
pipeline and posts the analysis as a PR comment — no manual step.

#### Step 1 — be in the project directory

The watcher resolves its modules and `.env` relative to the project root, so run
it from the repo root (running it from a subdirectory causes
`ModuleNotFoundError: No module named 'integrations'`):

```bash
cd path/to/MultiAgentCodeReview
```

#### Step 2 — make sure `.env` has both keys

```
OPENAI_API_KEY=sk-...    # used by the agents to review
GITHUB_TOKEN=ghp_...     # used to read PRs and post comments
```

(On a machine behind a SOCKS proxy you also need `pip install socksio` for the
OpenAI calls to work.)

#### Step 3 — run it

```bash
python3 watch_prs.py rahulilla/airflow
```

This will:

- **pre-seed** currently-open PRs, so it ignores existing ones and only reacts to
  PRs opened *after* it starts;
- poll every 20s, printing a heartbeat (`poll #N: X open, Y new`);
- on a new PR → run the 6 agents → **post the analysis as a comment**;
- dedup on `(PR number, head commit)` so it never double-comments (a new commit
  pushed to the PR triggers exactly one re-review).

Stop it with **Ctrl-C** (it saves state and exits cleanly).

#### Demo flow

1. Start the watcher (command above).
2. Open a new PR on `rahulilla/airflow` with a small `.py` change.
3. Within ~one poll cycle, watch the terminal detect it and the comment appear on
   the PR.

#### Flags

| Flag | Effect | When to use |
|------|--------|-------------|
| `--interval 15` | poll every 15s (default 20) | snappier demo |
| `--no-comment` | review + write local report, do **not** post | watching a repo you can't comment on, or a dry run |
| `--review-existing` | also review PRs already open at startup ⚠️ comments on **all** open PRs | process a PR that already exists |
| `--max-files 5` | cap Python files reviewed per PR | large PRs / cost control |

#### Which repos can I watch?

You can **review** any public repo. You can only **post comments** on repos where
you have write access (your own repos/forks, or repos you're a collaborator on).
For any other public repo, run with `--no-comment` and the analysis is saved
locally instead:

```bash
python3 watch_prs.py pallets/flask --no-comment
```

Always run with a `GITHUB_TOKEN` set — the anonymous rate limit (60 req/hour) is
too low for polling; an authenticated token allows 5,000 req/hour. If the token
isn't picked up from `.env`, you can force it inline:

```bash
GITHUB_TOKEN=ghp_xxx python3 watch_prs.py rahulilla/airflow
```

## Telemetry & dashboard

Every PR review emits structured events to `runs/events.jsonl` (line-delimited
JSON, append-only, gitignored). Four event types share a `type` discriminator:

- `pr_review` — one per PR reviewed (counts, severities, duration)
- `agent` — one per LangGraph node (per-agent timing, findings added, errors)
- `llm_call` — one per `call_llm()` attempt (backend, model, tokens, retries)
- `poll_cycle` — one per watcher poll iteration

A Streamlit dashboard tails this file and renders KPIs, a Sankey of agent flow,
per-agent duration distributions, LLM telemetry, and the watcher's poll history.

### Run the dashboard

From the repo root, with the venv active (or via its `streamlit` binary):

```bash
streamlit run dashboard/app.py
# → opens http://localhost:8501 — auto-refreshes every 10s
```

If `streamlit` isn't on your PATH, run it via the venv directly:

```bash
.venv/bin/streamlit run dashboard/app.py
```

The dashboard is read-only and reads `runs/events.jsonl` directly, so you can
run it alongside an active watcher (in another terminal) and see PRs land live.
Set `METRICS_DISABLED=1` to suppress emission entirely (e.g. in tests).

## Load testing

`load_test/` exercises the full pipeline by opening 30 deliberately-bad PRs
against a target repo (your fork — never a public repo you don't own) and
verifying each gets reviewed end-to-end:

```bash
# Terminal A — start the watcher with the agent-proposer step disabled
# (the proposer polls CI for 5min; load-test fork need not have Actions)
SKIP_AGENT_PROPOSAL=1 python watch_prs.py <owner>/<repo>

# Terminal B — drive 30 buggy PRs sequentially
python -m load_test.orchestrator --dry-run     # plan only, no GitHub calls
python -m load_test.orchestrator --count 1     # single-PR pre-flight
python -m load_test.orchestrator               # full 30 (~40 min)

# Terminal C — watch the dashboard fill in real time
streamlit run dashboard/app.py
```

The target owner/repo is set as a constant at the top of
`load_test/orchestrator.py` (and there's a hard guard refusing to run against
known public repos). Per-PR results land in `load_test/status.json`. See
`load_test/README.md` for template details and a one-liner to close the
resulting PRs afterward.

## Case studies

Five concrete bugs the pipeline caught on real PRs to `rahulilla/airflow`
during the load test, with the agent's verbatim output and suggested fix:

| # | Category | CWE / metric | Live PR |
|---|---|---|---|
| [SQL injection via string concatenation](case_studies/01-sql-injection.md) | Security | CWE-89 | [#5](https://github.com/rahulilla/airflow/pull/5) |
| [Hardcoded production API key](case_studies/02-hardcoded-api-key.md) | Security | CWE-798 | [#9](https://github.com/rahulilla/airflow/pull/9) |
| [Mutable default argument](case_studies/03-mutable-default-arg.md) | Bug | CWE-582 | [#15](https://github.com/rahulilla/airflow/pull/15) |
| [Quadratic string concatenation](case_studies/04-string-concat-loop.md) | Performance | — | [#27](https://github.com/rahulilla/airflow/pull/27) |
| [Pathological cyclomatic complexity](case_studies/05-cyclomatic-complexity.md) | Style | radon CC=14 | [#30](https://github.com/rahulilla/airflow/pull/30) |

See [`case_studies/README.md`](case_studies/README.md) for the index.

## Evaluation

Recall on planted bugs across the 30 load-test templates:

| Category | Expected | Hit | Recall |
|---|---|---|---|
| Security | 10 | 10 | 100% |
| Bug | 10 | 10 | 100% |
| Performance | 5 | 5 | 100% |
| Style | 6 | 6 | 100% |
| **Overall** | **30** | **30** | **100%** |

Re-run with `python -m eval.score`. Methodology, caveats (we measure recall,
not precision; "category caught" not "exact bug caught"), and per-template
breakdown live in [`eval/README.md`](eval/README.md).

## Project layout

| Path | Purpose |
|------|---------|
| `models/schemas.py` | Pydantic state + finding schemas |
| `llm/backend.py` | Hybrid GPT-4o / CodeLlama backend |
| `agents/` | The six analysis & generation agents |
| `graph/pipeline.py` | LangGraph state machine |
| `run_pipeline.py` | Local-file CLI |
| `integrations/github_pr.py` | GitHub REST client |
| `pr_review_core.py` | Shared "review one PR" logic |
| `review_pr.py` | PR review CLI |
| `watch_prs.py` | Polling watcher (auto-trigger) |
| `metrics/recorder.py` | Pydantic event schemas + JSONL emitter |
| `dashboard/app.py` | Streamlit dashboard over `runs/events.jsonl` |
| `load_test/` | 30-PR load-test driver + buggy-code templates |
| `eval/` | Recall scorer over the 30 templates + results |
| `case_studies/` | Five real bugs with verbatim agent output |
| `docs/` | GitHub Pages slide deck (HTML/CSS/JS) |
| `scripts/start.sh` | One-command launcher for watcher + dashboard |
| `scripts/macr-start` | Portable wrapper — run from any directory |
| `build_notebook.py` | Generates the Colab notebook |

## Status

Phases 1–3 (single agent → multi-agent pipeline → patch/test generation) and the
GitHub PR integration are implemented. RAG grounding (ChromaDB + CWE/OWASP) and a
Gradio UI are planned.
