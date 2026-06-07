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

Polls a repo and reviews each newly opened PR automatically, posting a comment:

```bash
export GITHUB_TOKEN=...
python watch_prs.py <owner>/<repo>
```

It dedups on `(PR number, head commit)` and pre-seeds existing PRs, so it only
reacts to PRs opened after it starts.

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
