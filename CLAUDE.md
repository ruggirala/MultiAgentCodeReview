# Multi-Agent Code Review & Auto-Debugging System

This file is loaded automatically by Claude Code when running `claude .` in this
repo. It captures the project's current architecture, conventions, and the
decisions a contributor needs to know on day one.

> **For deeper context** (design decisions, telemetry shapes, env-knob
> distinctions, known open questions): see [`docs/CONTEXT.md`](docs/CONTEXT.md).
> Claude Code follows linked references so it gets loaded into context too.

## What this is

A LangGraph state machine of seven AI agents that reviews Python code for
**security, bugs, performance, and style**, proposes fixes, and generates
pytest suites. Two ways to run it:

- **Local file** — `python run_pipeline.py path/to/file.py`
- **Live GitHub PR** — `python watch_prs.py <owner>/<repo>` polls the repo and
  posts a structured review comment on every new PR; optionally pushes the
  agent's fixed code to a sibling branch and opens a follow-up PR.

Public deck: <https://rahulilla.github.io/MultiAgentCodeReview/>

---

## Architecture

```
GitHub PR (webhook → watcher)
        │
        ▼
   Orchestrator         tree-sitter chunking (stdlib `ast` fallback)
        │
        ▼
┌────────────────────────────────────────┐
│  Security · Bug · Style/Perf agents    │
│  (sequential; shared ReviewState)      │
└────────────────────────────────────────┘
        │  ──── RAG: CWE + OWASP via ChromaDB (USE_RAG=1) ────►
        ▼
   Triage  (Critical/High security → human review branch)
        │
        ▼
   Patch  →  Tests  →  Comment + follow-up PR
```

Every node mutates a single Pydantic `ReviewState` (`models/schemas.py`).
LangGraph routes via `add_conditional_edges` so the human-review branch is a
real interrupt point, not a hallucinated decision.

---

## Project layout

```
.
├── CLAUDE.md                    # ← you are here
├── README.md                    # public-facing usage docs
├── requirements.txt             # core + dashboard deps
├── .env.example                 # OPENAI_API_KEY + GITHUB_TOKEN template
├── .streamlit/config.toml       # dashboard dark + purple theme
│
├── models/schemas.py            # ReviewState, Finding, PatchProposal, GeneratedTest
├── llm/backend.py               # GPT-4o primary / CodeLlama-7B (4-bit) fallback
├── agents/                      # one module per agent (security, bug, style, ...)
├── graph/pipeline.py            # LangGraph StateGraph + _instrumented() wrapper
├── rag/                         # CWE/OWASP corpus + ChromaDB build script
│
├── integrations/github_pr.py    # GitHub REST client (PR fetch, comments, refs, commits)
├── pr_review_core.py            # shared "review one PR" logic; emits PRReviewEvent
├── review_pr.py                 # one-shot PR review CLI
├── watch_prs.py                 # polling watcher; emits PollCycleEvent per loop
├── agent_pr_proposer.py         # post-review: commit fixes → branch → follow-up PR
├── run_pipeline.py              # one-shot local-file CLI
│
├── metrics/recorder.py          # 4 Pydantic event schemas + JSONL writer + contextvars
├── dashboard/app.py             # Streamlit dashboard (reads runs/events.jsonl)
├── load_test/                   # 30-PR sequential load-test driver
│   ├── orchestrator.py          # opens PRs, tails events.jsonl, writes status.json
│   └── buggy_templates.py       # 30 hand-curated BuggyTemplate entries
│
└── docs/                        # GitHub Pages slide deck (index.html + style.css + script.js)
```

---

## Tech stack

| Component | Tool | Notes |
|---|---|---|
| Orchestration | **LangGraph** | StateGraph, conditional edges, retries |
| Schemas | **Pydantic v2** | every agent input/output is structured |
| Code parsing | **tree-sitter** | AST chunking (stdlib `ast` fallback) |
| Static analysis | **pylint + radon** | style + cyclomatic complexity |
| Vector DB | **ChromaDB** | CWE + OWASP RAG store |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | 384-dim |
| LLM (primary) | **GPT-4o** via OpenAI API | dev path, best quality |
| LLM (fallback) | **CodeLlama-7B-Instruct** 4-bit | keyless, runs on Colab T4 |
| Telemetry | JSONL + Pydantic | `runs/events.jsonl`, append-only |
| Dashboard | **Streamlit + Plotly + pandas** | dark + purple, auto-refresh 10s |
| Slide deck | hand-written HTML/CSS/JS | served via GitHub Pages from `/docs` |
| GitHub | REST v3 via `requests` | no PyGithub dep |

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in OPENAI_API_KEY (and GITHUB_TOKEN if reviewing PRs)
```

The watcher needs a `GITHUB_TOKEN` with PR read/write to post comments. Without
one, anonymous rate limit (60 req/hour) is too low for polling.

---

## Running

### Review a local Python file
```bash
python run_pipeline.py sample_bad_code.py
```
Writes `<name>_review.md`, `<name>_fixed.py`, a pytest suite, and a `.zip`.

### Review a single GitHub PR
```bash
python review_pr.py https://github.com/owner/repo/pull/N
python review_pr.py <pr_url> --comment   # also posts a summary comment
```

### Auto-review every new PR (watcher)
```bash
python watch_prs.py owner/repo --interval 20
```
Pre-seeds currently-open PRs (so it ignores them), polls every 20s, runs the
pipeline on the first new PR it sees, posts the comment, and (CI permitting)
pushes the agent's fixed code to a sibling branch + opens a follow-up PR.

### Dashboard
```bash
streamlit run dashboard/app.py
# opens http://localhost:8501 — auto-refreshes every 10s
```

### Load test (30 buggy PRs sequentially against a fork)
```bash
# Terminal A — watcher with proposer disabled (load test wants only review comments)
SKIP_AGENT_PROPOSAL=1 python watch_prs.py <owner>/<fork>

# Terminal B — driver
python -m load_test.orchestrator --dry-run             # plan only
python -m load_test.orchestrator --count 1             # single-PR pre-flight
python -m load_test.orchestrator                       # full 30 (~40 min)
```
The orchestrator hardcodes `OWNER = "rahulilla"` and refuses to run against
known public repos (`apache`, `Apache`). Modify the source to retarget —
deliberate friction.

---

## Important env knobs

| Env | Effect | When to use |
|---|---|---|
| `OPENAI_API_KEY` | enables GPT-4o backend | dev path |
| `GITHUB_TOKEN` | required for PR comments + commits | always when watching/reviewing PRs |
| `LLM_BACKEND` | `auto` (default) / `openai` / `codellama` | force a specific backend |
| `USE_RAG=1` | enables ChromaDB grounding in security agent | adds CWE citations to findings |
| `METRICS_DISABLED=1` | suppresses all event emission to `runs/events.jsonl` | tests, debugging |
| **`SKIP_AGENT_PROPOSAL=1`** | skips the entire `propose_agent_fixes()` step | load testing, or any case where you only want the review comment |
| **`SKIP_CI_GATE=1`** | proposer runs, but skips Actions `workflow_dispatch` + 5-min CI poll | repos without `health-check.yml` (e.g. forks of upstream projects) |

The two `SKIP_*` vars sound similar but differ — see `agent_pr_proposer.py`
header comment for the distinction.

---

## Telemetry

Every PR review emits structured JSONL events to `runs/events.jsonl` (gitignored).
Four event types share a `type` discriminator:

- **`pr_review`** — one per `handle_pr()` call (counts, severities, duration)
- **`agent`** — one per LangGraph node (per-agent timing, findings added, errors)
- **`llm_call`** — one per `call_llm()` attempt (backend, model, tokens, retries)
- **`poll_cycle`** — one per watcher poll (open / new / reviewed / error counts)

`call_llm()` doesn't take a state arg, so attribution to the calling agent uses
a `contextvars.ContextVar` set by the LangGraph node wrapper in
`graph/pipeline.py::_instrumented()`. Any LLM call made transitively gets
attributed.

Schemas + writer: `metrics/recorder.py`. Disable with `METRICS_DISABLED=1`.

The Streamlit dashboard at `dashboard/app.py` tails this file and renders
KPIs, agent-flow Sankey, per-agent duration distributions, LLM telemetry,
and watcher poll history.

---

## Conventions

- **Python:** 3.10+
- **Style:** PEP 8, type hints on public function signatures
- **Schemas:** Pydantic v2 for all agent I/O — no free-form string parsing between agents
- **LLM calls:** temperature 0.1–0.3 for deterministic analysis
- **Error handling:** retry with exponential backoff in `llm.backend.call_llm` (3 attempts max)
- **File naming:** `snake_case` modules, `PascalCase` classes
- **Prompts:** module-level string constants, f-string injection
- **Don't commit:** `.env`, model weights, `runs/events.jsonl`, `load_test/status.json`,
  per-PR review artifacts (matched by patterns in `.gitignore`)
- **Public docs (README, slides):** never include personal local paths like
  `/Users/...`. Use `path/to/MultiAgentCodeReview` or instruct "from the repo root."

---

## Key design decisions

1. **LangGraph over raw LangChain** — explicit conditional edges, real human-review
   interrupt point, support for retry logic.
2. **Pydantic for everything between agents** — no free-form text parsing.
   Every finding, patch, and test suite is a typed schema.
3. **JSONL telemetry, not a DB** — append-only, crash-safe, trivially tailable
   from Streamlit's `cache_data(ttl=10)`. Easy to migrate to DuckDB later.
4. **Hybrid LLM** — GPT-4o for quality on the dev path; CodeLlama-7B (4-bit)
   means the system runs end-to-end on a Colab T4 with no API key.
5. **RAG grounding for security findings** — every Critical/High vulnerability
   cites a CWE, not a hallucinated category.
6. **tree-sitter for parsing** — AST-level chunking means agents review logical
   units (functions, classes), not arbitrary line splits. Language-agnostic.

---

## Repos

- **This project** — github.com/rahulilla/MultiAgentCodeReview
- **Demo target** (Flask + GitHub Actions for the proposer's CI gate) — github.com/rahulilla/python-simple-webapp
- **Load-test target** (no Actions workflow, run with `SKIP_CI_GATE=1`) — github.com/rahulilla/airflow

---

## Datasets

| Dataset | Purpose | Source |
|---|---|---|
| CWE database | Security RAG corpus | MITRE |
| OWASP Top-10 (2021) | Security RAG corpus | OWASP |
| Hand-curated 30 buggy templates | Load-test PR generation | `load_test/buggy_templates.py` |

---

## Where to look first when…

- **Adding a new agent** → `agents/`, then wire it into `graph/pipeline.py` and apply
  `_instrumented()` so it gets telemetry for free.
- **Changing event shape** → `metrics/recorder.py` (Pydantic schemas) → update
  the dashboard reader at `dashboard/app.py`.
- **Touching the LLM backend** → `llm/backend.py`. Keep the OpenAI/CodeLlama
  abstraction so `call_llm()` callers stay backend-agnostic.
- **Editing slides** → `docs/index.html` + `docs/style.css`. Pages auto-deploys
  on push to main; URL is rahulilla.github.io/MultiAgentCodeReview/.
- **Debugging a missing PR review** → check the watcher's stdout; check
  `runs/events.jsonl` for a matching `poll_cycle` event; check the watcher's
  dedup state at `.pr_watch_state.json`.
