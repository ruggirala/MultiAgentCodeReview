# Multi-Agent Code Review & Auto-Debugging System

**Capstone Project — Architecture & Technical Implementation**

---

## 1. What this project is

An AI system that reads Python code, finds problems across **four dimensions** (security, bugs, style, performance), proposes fixes, and writes tests for the fixes. It runs in three increasingly capable forms:

- A **single-file local script** (Phase 1) — paste a `.py` file, get a report and a fixed version.
- A **multi-agent pipeline in a Colab notebook** (the deliverable) — six specialized agents working from a shared state, grounded in real OWASP/CWE knowledge via RAG, with a Gradio file-upload UI.
- A **live GitHub reviewer** — a polling watcher that auto-reviews any new PR on a target repo, posts findings as a PR comment, pushes its proposed fixes to a sibling branch, runs CI on those fixes, and **only opens a follow-up PR if CI is green**.

The capstone deliverable is the Colab notebook. The GitHub reviewer is built on top of the same pipeline as a real-world demonstration that the system works on production-shaped inputs, not just hand-picked examples.

---

## 2. High-level architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INPUT (any .py file or GitHub PR)                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
                  ┌────────────────────────────────────────┐
                  │       LangGraph state machine          │
                  │       (one shared ReviewState)         │
                  └────────────────────────────────────────┘
                                       │
   ┌───────────────────────────────────┼───────────────────────────────────┐
   ▼                                   ▼                                   ▼
┌──────────┐                   ┌─────────────┐                       ┌────────┐
│Orchestr. │  tree-sitter →    │  Security   │  RAG-grounded         │  Bug   │
│ chunks   │  function /       │   Agent     │  (top-4 CWE / OWASP   │  Agent │
│          │  class /module    │             │  hits in the prompt)  │        │
└──────────┘                   └─────────────┘                       └────────┘
                                                                          │
                                                                          ▼
                                                                    ┌────────┐
                                                                    │ Style  │
                                                                    │ + Perf │
                                                                    │ pylint │
                                                                    │ +radon │
                                                                    └────────┘
                                                                          │
                                                                          ▼
                                                                    ┌────────┐
                                                                    │ Triage │
                                                                    └────┬───┘
                                                                         │
                                                       ┌─────────────────┴─────────────────┐
                                       Critical/High security              everything else
                                                       │                                   │
                                                       ▼                                   │
                                                ┌────────────┐                              │
                                                │  Human     │                              │
                                                │  Review    │                              │
                                                │  pause     │                              │
                                                └─────┬──────┘                              │
                                                      └─────────────────┬───────────────────┘
                                                                        │
                                                                        ▼
                                                                  ┌──────────┐
                                                                  │  Patch   │  full corrected file
                                                                  │  Agent   │
                                                                  └────┬─────┘
                                                                       │
                                                                       ▼
                                                                  ┌──────────┐
                                                                  │  Tests   │  pytest suite
                                                                  │  Agent   │
                                                                  └────┬─────┘
                                                                       │
                                                                       ▼
                          OUTPUT: report + fixed code + tests + ZIP bundle
```

**The single most important design choice:** every agent is a pure function `ReviewState → ReviewState`. They never call each other. The shared `ReviewState` (a Pydantic v2 model) is the only thing flowing between them. LangGraph handles control flow via edges, not function calls. This makes the pipeline deterministic, testable, and trivially extensible.

---

## 3. Two-repo demo loop (the live system)

```
┌──────────────────────────────────────┐         ┌──────────────────────────────────────┐
│  rahulilla/MultiAgentCodeReview      │         │  rahulilla/python-simple-webapp      │
│  THE REVIEWER                        │         │  THE TARGET                          │
│                                      │         │                                      │
│  watch_prs.py polls every 20s        │ reviews │  • Flask app + /health endpoint      │
│  ↓                                   │ + posts │  • PR opens here                     │
│  6-agent LangGraph pipeline          │ comment │  • GitHub Actions runs:              │
│  ↓ (agent_pr_proposer.py)            │ ──────► │      pytest + boot + curl /health    │
│  push fixes branch                   │         │      → assert HTTP 200               │
│  ↓                                   │         │                                      │
│  workflow_dispatch CI on that branch │         │                                      │
│  ↓ (poll up to 5 min)                │         │                                      │
│  if green → open follow-up PR        │         │                                      │
│  if red   → comment failure-link,    │         │                                      │
│             NO PR opened             │         │                                      │
└──────────────────────────────────────┘         └──────────────────────────────────────┘
```

Why two repos: it mirrors real CI/CD topology — the reviewer and the reviewee don't share a deployment lifecycle. The reviewer can review **any** repo it has a token for.

---

## 4. The agents — one paragraph each

| # | Agent | What it does | Implementation |
|---|---|---|---|
| 1 | **Orchestrator** | Splits source into reviewable units (functions, classes, module-level). | tree-sitter for the rich case, stdlib `ast` as a graceful fallback so the system works even when tree-sitter wheels aren't available. |
| 2 | **Security** | Detects OWASP Top-10 / CWE vulnerabilities. | LLM call. **Optionally RAG-grounded** when `USE_RAG=1`: top-4 most similar OWASP/CWE entries from a ChromaDB index get spliced into the prompt as a "use these labels" hint. Off by default to keep the watcher runnable without ChromaDB. |
| 3 | **Bug** | Finds logic and runtime errors via chain-of-thought reasoning. | LLM, temperature 0.2, structured JSON output parsed into Pydantic `Finding` objects. |
| 4 | **Style & Performance** | PEP-8 + complexity + perf anti-patterns. | pylint (style), radon (cyclomatic complexity), plus an LLM perf pass for things static analysis misses (O(n²) loops etc.). |
| 5 | **Triage** | Decides whether human review is required. | Conditional edge: any **Critical/High security** finding routes to a `human_review` checkpoint node before patching. |
| 6 | **Patch** | Produces a corrected version of the entire file. | LLM, structured `PatchProposal` with `summary` + `fixed_code` + `addressed_findings`. |
| 7 | **Tests** | Generates a pytest suite for the patched code. | LLM, output is a runnable pytest module that imports the code as `solution`. |

---

## 5. RAG layer — what it actually does

The RAG layer's value is **consistency**, not knowledge. GPT-4o already knows CWE numbers; what it doesn't always do is cite them consistently.

- **Corpus:** 47 inlined entries — the **OWASP Top 10 (2021)** plus **37 hand-curated CWEs** chosen because the agents flag them in real PRs (CWE-89 SQL injection, CWE-798 hardcoded creds, CWE-22 path traversal, CWE-256 plaintext password, CWE-502 deserialization, CWE-369 divide-by-zero, CWE-710 mutable default args, CWE-775 resource leaks, etc.).
- **Index:** ChromaDB `EphemeralClient` (in-memory, rebuilt per process), embedded with `sentence-transformers/all-MiniLM-L6-v2` (384-dim, ~80 MB), cosine distance.
- **Lookup:** the *full source code itself* is the query — the embedder picks up idioms (`sqlite3.connect`, `pickle.loads`, `eval(`) that match CWE descriptions in semantic space. Top-4 hits are formatted with their IDs and prepended to the security agent's prompt.
- **Why inline the corpus:** keeps the notebook 100% reproducible. No first-run download, no upstream URL dependency, no flaky fetch. ~27 KB of text in `rag/corpus.py`.
- **Fail-soft:** if ChromaDB or sentence-transformers aren't installed, the security agent prints a warning and continues without RAG. Never crashes the pipeline.

---

## 6. Hybrid LLM backend

`llm/backend.py` provides a single `call_llm(prompt, system, temperature)` entrypoint. All five LLM-using agents are backend-agnostic.

- `LLM_BACKEND=auto` (default) → OpenAI if `OPENAI_API_KEY` present, else CodeLlama
- `LLM_BACKEND=openai` → GPT-4o via OpenAI chat-completions, temperature 0.2
- `LLM_BACKEND=codellama` → local 4-bit `codellama/CodeLlama-7b-Instruct-hf` via HuggingFace + BitsAndBytes (`load_in_4bit`, `nf4`, fp16 compute), runs on Colab T4
- **Retry with exponential backoff** (max 3, sleep `2^attempt`s) on transient failures
- **Token resolution:** env var first, then Colab `userdata.get(...)` — same pattern used by `GitHubPRClient` for `GITHUB_TOKEN`

Why hybrid: best quality for the demo (GPT-4o), keyless reproducibility for graders (CodeLlama runs offline on a T4).

---

## 7. The CI gate — `workflow_dispatch` over chicken-and-egg

The agent's "push fixes → open follow-up PR only if CI green" feature has a subtle problem: how do you run CI on a branch *before* opening a PR for it? `on: push: branches: [main]` rejects sibling branches; `on: pull_request` needs a PR to exist.

Solution: `on: workflow_dispatch` (already declared in the demo app's workflow as a manual-trigger affordance). The REST endpoint `POST /actions/workflows/health-check.yml/dispatches` accepts a `ref` parameter, letting the agent run CI on **any branch with no PR**. Zero workflow file changes.

```
agent fix → push to <branch>-agent-suggested
          → POST /actions/workflows/health-check.yml/dispatches { "ref": branch }
          → poll list_workflow_runs(branch=branch) until status=="completed"
              ┌─ conclusion=success → open follow-up PR + link comment on original PR
              └─ conclusion=failure → NO PR; comment failure-link; leave branch for inspection
```

PR #3 on the demo repo (deliberately broken fix injected via `AGENT_FIX_INJECT_BAD=1`) proves the gate works: CI failed → no follow-up PR opened → original PR got the failure-link comment. The gate is real, not decorative.

---

## 8. Live evidence — clickable in any demo

| Demo PR | Path | Outcome |
|---|---|---|
| [PR #1 — Add /echo endpoint](https://github.com/rahulilla/python-simple-webapp/pull/1) | review → propose-fixes → CI green | findings comment + [PR #2 (the agent's fixes)](https://github.com/rahulilla/python-simple-webapp/pull/2) opened |
| [PR #3 — Bump version (broken fix injected)](https://github.com/rahulilla/python-simple-webapp/pull/3) | review → broken fix → CI fails | [run #6 ❌](https://github.com/rahulilla/python-simple-webapp/actions/runs/27474531416) — **no follow-up PR**, failure comment posted |

---

## 9. Tech stack (mapped to where each piece lives)

| Component | Tool | File |
|---|---|---|
| State schema | Pydantic v2 | `models/schemas.py` |
| Orchestration | LangGraph StateGraph | `graph/pipeline.py` |
| LLM (primary) | OpenAI GPT-4o | `llm/backend.py` |
| LLM (fallback) | CodeLlama-7B-Instruct, 4-bit | `llm/backend.py` |
| Vector DB | ChromaDB | `rag/retriever.py` |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 | `rag/retriever.py` |
| Code parsing | tree-sitter (+ ast fallback) | `agents/orchestrator.py` |
| Static analysis | pylint, radon | `agents/style_agent.py` |
| GitHub REST | requests (no PyGithub) | `integrations/github_pr.py` |
| UI | Gradio 4.x | notebook §6 |
| CI | GitHub Actions | `demo_webapp/.github/workflows/health-check.yml` |
| Runtime target | Google Colab (T4 GPU) | `multi_agent_code_review.ipynb` |

---

## 10. Capstone rubric — coverage check

| Phase | Item | Status |
|---|---|---|
| 1 | Single agent with GPT-4o | ✅ `code_review_agent.py` |
| 1 | Pydantic structured output | ✅ `models/schemas.py` |
| 1 | Single-agent Colab port | ✅ `code_review_agent_colab.ipynb` |
| 2 | Pydantic state schema | ✅ `models/schemas.py::ReviewState` |
| 2 | Orchestrator with tree-sitter (+ ast fallback) | ✅ `agents/orchestrator.py` |
| 2 | Security Agent | ✅ `agents/security_agent.py` |
| 2 | Bug Agent (chain-of-thought) | ✅ `agents/bug_agent.py` |
| 2 | Style & Performance Agent (pylint + radon) | ✅ `agents/style_agent.py` |
| 2 | LangGraph StateGraph + conditional edges | ✅ `graph/pipeline.py` |
| 2 | Retry with exponential backoff | ✅ `llm/backend.py` |
| 3 | Patch Generation Agent | ✅ `agents/patch_agent.py` |
| 3 | Test Generation Agent | ✅ `agents/test_agent.py` |
| 3 | End-to-end pipeline validation | ✅ `run_pipeline.py` |
| 4 | CWE/OWASP corpus | ✅ `rag/corpus.py` (47 entries) |
| 4 | ChromaDB index + retrieval | ✅ `rag/retriever.py` |
| 4 | Security agent grounded by RAG | ✅ `USE_RAG=1` path in `agents/security_agent.py` |
| 5 | Gradio UI | ✅ notebook §6 |
| 5 | Single Colab notebook (Run All) | ✅ `multi_agent_code_review.ipynb` (35 cells) |
| 5 | Demo with synthetic buggy examples | ✅ `sample_bad_code.py` + notebook §3 |
| **Beyond rubric** | Live GitHub PR reviewer (watcher) | ✅ `watch_prs.py` |
| **Beyond rubric** | Agent-suggested follow-up PR | ✅ `agent_pr_proposer.py` |
| **Beyond rubric** | CI-gated follow-up PR (workflow_dispatch) | ✅ proven on PRs #1 + #3 |
| **Beyond rubric** | Demo target app + GitHub Actions health check | ✅ `rahulilla/python-simple-webapp` |

**All 19 rubric items + 4 beyond-rubric extensions: present and live.**

---

## 11. How to verify (5-minute reviewer test)

1. Open the Colab notebook → Runtime → Change runtime type → T4 GPU → Run all
2. Cells §3 produce 15 findings on `sample_bad_code.py`
3. Cell §4 reviews PR #1 on `python-simple-webapp` — 7 real findings
4. Cell §5d shows USE_RAG=on/off A/B — RAG-on findings cite consistent CWE IDs
5. Cell §6 launches the Gradio UI inline — drag a `.py` file, click Run, get a ZIP
6. Cell §7 documents the watcher + CI-gate live demo with [clickable PR URLs](https://github.com/rahulilla/python-simple-webapp/pulls)

---

## 11.5 Observability

Every PR review emits structured telemetry to `runs/events.jsonl` (append-only,
line-delimited JSON; one event per line; gitignored). Four event types share a
`type` discriminator:

- **`pr_review`** — one per PR reviewed: counts, severities, duration, run_id.
- **`agent`** — one per LangGraph node: agent name, duration, findings added,
  errors. Lets us reconstruct the *agent interaction* path for each file.
- **`llm_call`** — one per `call_llm()` attempt: backend, model, tokens, retry,
  errors. Attribution to the calling agent is via a `contextvars.ContextVar`
  set by the pipeline node wrapper.
- **`poll_cycle`** — one per `watch_prs.py` poll iteration: open/new/reviewed
  counts, error count, current backoff.

A Streamlit dashboard (`dashboard/app.py`) tails this file and visualizes:
- Overview KPIs (PRs reviewed, findings, throughput, error rate)
- Per-PR table with daily throughput
- Agent-interaction Sankey, per-agent duration box plot, findings-contribution bar
- LLM telemetry (calls per backend/model, token totals, retries, p95 latency)
- Watcher poll cadence

Launch:
```bash
streamlit run dashboard/app.py
```

Set `METRICS_DISABLED=1` to disable emission entirely (e.g. in tests).

## 12. Repository links

- **Reviewer (this project):** https://github.com/rahulilla/MultiAgentCodeReview
- **Demo target app:** https://github.com/rahulilla/python-simple-webapp
- **Final notebook (open in Colab):** https://colab.research.google.com/github/rahulilla/MultiAgentCodeReview/blob/main/multi_agent_code_review.ipynb
