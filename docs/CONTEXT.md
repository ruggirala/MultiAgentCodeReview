# Project context

Sanitized, third-person knowledge transfer for human contributors and AI
assistants alike. The CLAUDE.md at the repo root references this file so
Claude Code pulls it into context on `claude .`.

If you're a human reading this: it's the same project context the original
author has been building up across many sessions, with the personal /
preference / open-decision parts stripped out.

---

## 1. What this project is

A LangGraph state machine of seven AI agents that reviews Python code for
**security, bugs, performance, and style**, proposes fixes, and generates
pytest suites. Built as an AI training course capstone.

Two run modes:

- **Local file** — `python run_pipeline.py path/to/file.py`
- **Live GitHub PR** — `python watch_prs.py <owner>/<repo>` polls a repo and,
  on every new PR, runs the pipeline and posts a structured review comment.
  Optionally pushes the agent's fixed code to a sibling branch and opens a
  follow-up PR.

Three working repos:

| Repo | Role |
|---|---|
| `rahulilla/MultiAgentCodeReview` | This codebase |
| `rahulilla/python-simple-webapp` | Demo target — Flask + `/health` + GitHub Actions `health-check.yml` workflow. The full proposer flow (incl. CI gating) runs against this. |
| `rahulilla/airflow` | Load-test target — public Airflow fork. No `health-check.yml`, so reviews run with `SKIP_CI_GATE=1`. |

---

## 2. Architecture

`graph/pipeline.py` is a LangGraph `StateGraph`. Every node mutates one
shared `ReviewState` (Pydantic v2 model in `models/schemas.py`).

```
GitHub PR
   │
   ▼
Orchestrator     # tree-sitter chunking (stdlib `ast` fallback)
   │
   ▼
Security → Bug → Style/Perf       # sequential analysis agents
   │
   ▼
Triage           # rule-based: any Critical/High security finding → human_review
   │
   ├── human_review (logged-only checkpoint; LangGraph interrupt hook stubbed)
   ▼
Patch            # writes state.patch.fixed_code
   │
   ▼
Tests            # writes state.tests.test_code (pytest suite)
   │
   ▼
PR comment + (optional) sibling branch with fixed code + follow-up PR
```

Each agent only reads/writes the typed `ReviewState`. The security and bug
agents go further — they use OpenAI's **Structured Outputs**
(`response_format={"type": "json_schema", strict: true}`) so the response
is schema-conformant at the API boundary, not just downstream. See
`llm.backend.call_llm_structured`.

---

## 3. Project layout

```
.
├── CLAUDE.md / README.md / docs/CONTEXT.md   # the "what + why" surface
├── requirements.txt · .env.example · .streamlit/config.toml
│
├── models/schemas.py              # ReviewState, Finding, FindingsResponse, ...
├── llm/backend.py                 # call_llm + call_llm_structured
├── agents/                        # one module per agent (security, bug, style, ...)
├── graph/pipeline.py              # LangGraph StateGraph + _instrumented() wrapper
├── rag/                           # CWE / OWASP corpus + ChromaDB build script
│
├── integrations/github_pr.py      # GitHub REST client (no PyGithub dep)
├── pr_review_core.py              # shared "review one PR" logic
├── review_pr.py                   # one-shot PR review CLI
├── watch_prs.py                   # polling watcher CLI
├── agent_pr_proposer.py           # post-review: commit fixes → branch → follow-up PR
├── run_pipeline.py                # one-shot local-file CLI
│
├── metrics/recorder.py            # 4 Pydantic event schemas + JSONL emitter
├── dashboard/app.py               # Streamlit dashboard over runs/events.jsonl
├── load_test/                     # 30-PR sequential load-test driver
├── eval/                          # recall scorer + results.json
├── case_studies/                  # five real bugs the pipeline caught
│
├── docs/                          # GitHub Pages slide deck (index.html, style.css, script.js)
└── scripts/                       # start.sh (launcher) + macr-start (portable wrapper)
```

---

## 4. The seven agents

| # | Agent | Module | What it does |
|---|---|---|---|
| 1 | Orchestrator | `agents/orchestrator.py` | tree-sitter AST chunking (`function` / `class` / `module`), stdlib `ast` fallback |
| 2 | Security | `agents/security_agent.py` | OWASP/CWE classes, calls `call_llm_structured(FindingsResponse)`, optional ChromaDB RAG when `USE_RAG=1` |
| 3 | Bug | `agents/bug_agent.py` | Logic/runtime bugs, chain-of-thought prompting, also via `call_llm_structured` |
| 4 | Style/Perf | `agents/style_agent.py` | pylint (style) + radon (cyclomatic complexity) + an LLM perf pass; each step degrades gracefully if its dep is missing |
| 5 | Triage | `graph/pipeline.py::_triage` | Rule-based — sets `state.needs_human_review` if any Critical/High **security** finding present |
| 6 | Patch | `agents/patch_agent.py` | Produces `PatchProposal` (summary + full fixed file) |
| 7 | Tests | `agents/test_agent.py` | Produces `GeneratedTest` — a pytest suite that imports the code as `solution`. The proposer rewrites that to the real dotted module path when committing. |

`human_review` is a real node in the graph but currently a stub — it logs
the critical findings and the pipeline continues. The wiring is there; a
real LangGraph `interrupt_before=["human_review"]` is a small change away.

---

## 5. LLM backend (hybrid)

`llm/backend.py` selects automatically:

- **GPT-4o** when an `OPENAI_API_KEY` is present (best quality, dev path)
- **CodeLlama-7B-Instruct (4-bit, BitsAndBytes)** as a keyless local
  fallback — the system runs end-to-end on a Colab T4 GPU with no API key

Override via `LLM_BACKEND=auto|openai|codellama`. Agents are
backend-agnostic — both `call_llm` and `call_llm_structured` route through
`get_backend()`. The OpenAI path uses `response_format={"type": "json_schema"}`
to enforce structure server-side. The CodeLlama path can't honor that
natively, so it falls back to a polite-ask prompt + lenient Pydantic parse.

Retries: 3 attempts, exponential backoff (2s → 4s → 8s). Every attempt
(success or failure) emits an `LLMCallEvent` to telemetry.

---

## 6. GitHub integration

`integrations/github_pr.py` is a hand-rolled REST client (no PyGithub).
Methods needed by the pipeline:

- `get_pr`, `list_open_prs`, `list_changed_files`, `get_file_content`
- `post_pr_comment`, `open_pr`, `close_pr`
- `get_branch`, `create_or_update_ref`, `commit_files` (high-level
  blobs→tree→commit→ref)
- `dispatch_workflow`, `list_workflow_runs`, `get_workflow_run`

Token resolution mirrors the LLM backend: `GITHUB_TOKEN` /  `GH_TOKEN` env
var, then Colab `userdata`. The watcher needs at least PR read+write to
post comments.

**Per-file cap** — `MAX_FILE_BYTES = 50_000` in `integrations/github_pr.py`.
Files larger than 50 KB are **skipped** (not truncated) with a "(too large)"
tag in the report. This is a context-cost cap, not a "long files are hard
to review" one — 50 KB of Python is ~12K–17K tokens through the OpenAI
tokenizer, comfortably within GPT-4o's window.

**Per-PR file-count cap** — `--max-files`, default 10. The first 10 Python
files in GitHub's diff order are reviewed; the rest land in `result.skipped`.

---

## 7. Telemetry

Every PR review emits structured JSONL events to `runs/events.jsonl`
(gitignored). Four event types share a `type` discriminator:

- `pr_review` — one per `handle_pr()` call (counts, severities, duration)
- `agent` — one per LangGraph node (per-agent timing, findings added, errors)
- `llm_call` — one per `call_llm[/_structured]` attempt (backend, model,
  tokens, retry attempt, error)
- `poll_cycle` — one per watcher poll (open/new/reviewed/error counts)

`call_llm` doesn't take a state arg, so attribution to the calling agent
uses a `contextvars.ContextVar` set by `_instrumented()` in
`graph/pipeline.py`. Any LLM call made transitively gets attributed.

Schemas + writer: `metrics/recorder.py`. Disable with `METRICS_DISABLED=1`.

The Streamlit dashboard at `dashboard/app.py` tails this file and renders
KPIs, agent-flow Sankey, per-agent duration distributions, LLM telemetry
(incl. cost-per-PR computed at OpenAI list prices), and watcher poll
history. Auto-refreshes every 10 s.

---

## 8. Env knobs (the ones contributors actually need to know)

| Env | Effect | When to set |
|---|---|---|
| `OPENAI_API_KEY` | enables GPT-4o backend | dev path |
| `GITHUB_TOKEN` | required for PR comments + commits | always when watching/reviewing PRs |
| `LLM_BACKEND` | `auto` (default) / `openai` / `codellama` | force a specific backend |
| `USE_RAG=1` | enables ChromaDB grounding in the security agent | adds verbatim CWE citations to findings |
| `METRICS_DISABLED=1` | suppresses all event emission to `runs/events.jsonl` | tests, debugging |
| **`SKIP_AGENT_PROPOSAL=1`** | skips the entire `propose_agent_fixes()` step (commit + follow-up PR) | load testing, or any case where you only want the review comment |
| **`SKIP_CI_GATE=1`** | proposer runs, but skips the GitHub Actions `workflow_dispatch` + 5-min CI poll | repos without a `health-check.yml` workflow (e.g. the airflow fork) |

The two `SKIP_*` vars sound similar but differ — see
`agent_pr_proposer.py` header for the distinction. Mixing them up causes
every PR review on the airflow fork to hang for 5 min waiting for a CI
workflow that doesn't exist.

---

## 9. Design decisions (and what was chosen against)

| Decision | Picked | Rejected | Reason |
|---|---|---|---|
| Orchestration | LangGraph | raw LangChain chains | Explicit conditional edges; `human_review` is a real interrupt hook, not an LLM judgment |
| Inter-agent contract | Pydantic state | free-form text | Schema enforced server-side via OpenAI Structured Outputs; no parse-and-pray |
| Agent execution | Sequential | parallel security/bug/style | One shared `ReviewState` — no race on `findings.extend()`; patch+tests dominate latency anyway |
| Telemetry store | JSONL append-only | SQLite/Postgres | No DB to operate; crash-safe; Streamlit reads incrementally |
| LLM backend | GPT-4o + CodeLlama hybrid | single backend | Cost-vs-quality knob flippable per environment (incl. keyless Colab) |
| Load-test corpus | 30 hand-curated templates | LLM-generated bugs | Deterministic; recall-gradable (`eval/score.py`); no extra token cost |

These are also visualized as slide 6 of the deck (`docs/index.html`),
which is publicly served at <https://rahulilla.github.io/MultiAgentCodeReview/>.

---

## 10. Capabilities verified live

A few things the system has been shown to do end-to-end:

- **30-PR sequential load test** on `rahulilla/airflow` (load_test/): 30/30
  reviewed, 0 failures, median 56.5 s/PR. Each template plants a known bug
  category (10 Security / 10 Bug / 5 Performance / 5 Style); `eval/score.py`
  measures recall on those planted categories — currently 100% (30/30).
  Caveat: that's recall on planted bugs, not precision on real PRs. No
  hand-labeled ground truth for precision yet.
- **Live two-repo demo loop** with `rahulilla/python-simple-webapp`: user
  opens a PR → watcher detects within one poll cycle → agents review →
  comment posted → fixed code committed to a sibling branch → follow-up
  PR opened only after the demo app's `health-check.yml` workflow passes.
- **OpenAI Structured Outputs** verified end-to-end against PR #48 on the
  airflow fork: 0 parse errors across 240 LLM calls in the load-test data.

---

## 11. Known open question (for future maintainers)

**Bot identity** — agent-generated comments and follow-up PRs are
attributed to whichever account owns the `GITHUB_TOKEN` in `.env`, because
GitHub doesn't allow setting an arbitrary author in REST API calls. Three
levels of fix were considered, none implemented yet:

1. Cosmetic prefix in the comment body — zero code change, doesn't fix PR
   author for follow-up PRs.
2. Dedicated `code-review-agent` GitHub user — new account + collaborator
   + swap the PAT. Zero code change, full attribution fix. Recommended
   path if pursued.
3. GitHub App registration — most professional ("Code Review Agent (bot)"
   badge, what Dependabot does). Requires rewriting `GitHubPRClient` auth
   to use App-installation-token flow.

Not blocking the capstone; revisit if the system goes beyond demo use.

---

## 12. Where to look first when…

- **Adding a new agent** → `agents/`, then wire it into `graph/pipeline.py`
  and apply `_instrumented()` so it gets telemetry for free.
- **Changing event shape** → `metrics/recorder.py` (Pydantic schemas) →
  update the dashboard reader at `dashboard/app.py`.
- **Touching the LLM backend** → `llm/backend.py`. Keep the
  OpenAI/CodeLlama abstraction so `call_llm[/_structured]` callers stay
  backend-agnostic.
- **Editing slides** → `docs/index.html` + `docs/style.css`. Pages
  auto-deploys on push to main.
- **Debugging a missing PR review** → check the watcher's stdout; check
  `runs/events.jsonl` for a matching `poll_cycle` event; check the
  watcher's dedup state at `.pr_watch_state.json`.

---

## 13. Style + conventions

- **Python 3.10+**. PEP 8. Type hints on public functions.
- **Pydantic v2** for every cross-agent shape. No free-form text parsing
  between agents.
- **LLM temperature 0.1–0.3** for deterministic analysis.
- **Retry with exponential backoff** in `call_llm` (3 attempts max).
- **Don't commit:** `.env`, model weights, `runs/events.jsonl`,
  `load_test/status.json`, `logs/`, per-PR review artifacts (already in
  `.gitignore`).
- **Public docs** — never include personal local paths like `/Users/...`.
  Use `path/to/MultiAgentCodeReview` or instruct "from the repo root."
