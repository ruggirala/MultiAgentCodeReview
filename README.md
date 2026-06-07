# Multi-Agent Code Review & Auto-Debugging System

An AI-powered multi-agent system that reviews Python code from multiple angles
(security, bugs, style, performance), proposes fixes, and generates test cases.
It can review a local file or a **live GitHub pull request** and post its analysis
back as a PR comment.

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
it from there (running it from `scripts/` or elsewhere causes
`ModuleNotFoundError: No module named 'integrations'`):

```bash
cd /Users/rilla/AI_Training
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
| `build_notebook.py` | Generates the Colab notebook |

## Status

Phases 1–3 (single agent → multi-agent pipeline → patch/test generation) and the
GitHub PR integration are implemented. RAG grounding (ChromaDB + CWE/OWASP) and a
Gradio UI are planned.
