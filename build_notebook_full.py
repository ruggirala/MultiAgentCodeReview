"""
Generates the Phase 2 final-deliverable Colab notebook.

Run:
    python3 build_notebook_full.py
        -> writes multi_agent_code_review.ipynb

The notebook itself clones the MultiAgentCodeReview repo at a pinned commit and
imports the agents/graph/integrations modules from there — this keeps a single
source of truth for the agent code and keeps the notebook readable.
"""

import json

# Pin to a known-good commit so the notebook is reproducible. Bump this when
# the repo gets meaningful improvements you want the deliverable to include.
PINNED_COMMIT = "cbccd82df5f00f0e5d0e3ff1dd8ae92cd8b44bac"
REPO_URL = "https://github.com/rahulilla/MultiAgentCodeReview"


def md(*lines):
    return {"cell_type": "markdown", "metadata": {}, "source": _src(lines)}


def code(*lines):
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": _src(lines),
    }


def _src(lines):
    out = []
    for i, line in enumerate(lines):
        if i < len(lines) - 1:
            out.append(line + "\n")
        else:
            out.append(line)
    return out


# ---------------------------------------------------------------------------
# Phase A — skeleton + multi-agent pipeline
# ---------------------------------------------------------------------------

cells = [
    md(
        "# 🤖 Multi-Agent Code Review & Auto-Debugging System",
        "",
        "**Capstone deliverable** — a LangGraph-orchestrated multi-agent pipeline that "
        "reviews Python code from multiple angles (security, bugs, style, "
        "performance), grounds its findings in the OWASP Top 10 + curated CWEs via "
        "RAG, suggests fixes, and generates pytest test cases.",
        "",
        "**Reproducible:** select **Runtime → Run all** (Colab T4 GPU recommended).",
        "",
        "**Live infrastructure beyond this notebook:** a polling watcher and a CI-gated "
        "PR-fix proposer that operate against real GitHub PRs. Architecture and live "
        "evidence are documented in the final section — they are not started from "
        "this notebook because their value is in continuous operation.",
        "",
        f"**Source repo:** [{REPO_URL}]({REPO_URL}) · pinned to commit "
        f"`{PINNED_COMMIT[:10]}`",
        "",
        "---",
        "",
        "## Table of contents",
        "",
        "1. [Setup](#scrollTo=setup) — install deps, load secrets, clone the repo",
        "2. [The agents](#scrollTo=agents) — what each one does",
        "3. [Run the pipeline on a sample file](#scrollTo=runlocal)",
        "4. [Review a real GitHub PR](#scrollTo=runpr)",
        "5. [RAG layer](#scrollTo=rag) — ChromaDB + OWASP/CWE",
        "6. [Gradio UI](#scrollTo=gradio)",
        "7. [Architecture beyond this notebook](#scrollTo=arch) — watcher, "
        "agent-proposer, CI gate",
        "8. [Future work](#scrollTo=future)",
    ),

    md(
        '<a name="setup"></a>',
        "## 1. Setup",
        "",
        "**One-time:** add your API keys to Colab Secrets (🔑 icon, left sidebar):",
        "",
        "- `OPENAI_API_KEY` — required (the agents call GPT-4o)",
        "- `GITHUB_TOKEN` — optional, only needed for the *Review a real GitHub PR* "
        "section. A classic PAT with `public_repo` (or a fine-grained PAT with "
        "*Pull requests: Read*) is enough; **no write scope needed for this "
        "notebook** since we never post comments from here.",
        "",
        "Toggle **Notebook access ON** for whichever secrets you set.",
    ),

    md("### 1a. Install dependencies"),
    code(
        "!pip install -q \\",
        "  'openai>=1.0.0' 'python-dotenv>=1.0.0' 'pydantic>=2.0.0' \\",
        "  'langgraph>=0.2.0' 'langchain>=0.2.0' \\",
        "  'tree-sitter>=0.21.0' 'tree-sitter-languages>=1.10.0' \\",
        "  'pylint>=3.0.0' 'radon>=6.0.0' \\",
        "  'requests>=2.31.0' \\",
        "  'chromadb>=0.5.0' 'sentence-transformers>=2.7.0' \\",
        "  'gradio>=4.0.0'",
        "print('deps installed')",
    ),

    md("### 1b. Clone the project repo (pinned)"),
    code(
        "import os, subprocess, sys",
        "",
        f"REPO = {REPO_URL!r}",
        f"PINNED = {PINNED_COMMIT!r}",
        "TARGET = '/content/MultiAgentCodeReview'",
        "",
        "if not os.path.isdir(TARGET):",
        "    subprocess.run(['git', 'clone', '--quiet', REPO, TARGET], check=True)",
        "subprocess.run(['git', '-C', TARGET, 'fetch', '--quiet'], check=True)",
        "subprocess.run(['git', '-C', TARGET, 'checkout', '--quiet', PINNED], check=True)",
        "",
        "# Put the repo on sys.path so we can `import` the agents/graph/etc.",
        "if TARGET not in sys.path:",
        "    sys.path.insert(0, TARGET)",
        "",
        "print(f'cloned and pinned to {PINNED[:10]}')",
    ),

    md("### 1c. Load secrets and verify the LLM backend"),
    code(
        "from google.colab import userdata",
        "import os",
        "",
        "for key in ('OPENAI_API_KEY', 'GITHUB_TOKEN'):",
        "    try:",
        "        v = userdata.get(key)",
        "        if v:",
        "            os.environ[key] = v",
        "            print(f'{key}: set (len={len(v)})')",
        "        else:",
        "            print(f'{key}: NOT set (skip if not needed)')",
        "    except Exception:",
        "        print(f'{key}: NOT set (skip if not needed)')",
        "",
        "from llm.backend import get_backend",
        "backend = get_backend()",
        "print(f'\\nLLM backend: {backend.kind} ({backend.detail})')",
        "assert backend.kind == 'openai', \\",
        "    'This notebook expects GPT-4o. Add OPENAI_API_KEY to Colab Secrets.'",
    ),

    md(
        '<a name="agents"></a>',
        "## 2. The agents",
        "",
        "Each agent is a pure function `ReviewState → ReviewState`. The `ReviewState` "
        "(a Pydantic v2 model) is the single source of truth: agents read what earlier "
        "agents wrote and append their own findings. No agent talks directly to "
        "another — control flow is the **LangGraph state machine**.",
        "",
        "| # | Agent | Role |",
        "|---|---|---|",
        "| 1 | **Orchestrator** | parses code into chunks (tree-sitter, with stdlib `ast` fallback) |",
        "| 2 | **Security** | OWASP Top-10 / CWE vulnerabilities — grounded by the RAG layer (§5) |",
        "| 3 | **Bug** | logic + runtime errors via chain-of-thought |",
        "| 4 | **Style & Perf** | pylint + radon + LLM perf pass |",
        "| 5 | **Triage** | routes Critical/High security findings to a human-review checkpoint |",
        "| 6 | **Patch** | full corrected file |",
        "| 7 | **Tests** | pytest suite for the patched code |",
        "",
        "```",
        "START → orchestrate → security → bug → style → triage ─┬→ human_review →┐",
        "                                                        └─────────────── patch → tests → END",
        "```",
        "",
        "All agent + graph source lives in the cloned repo at `agents/`, `graph/`, "
        "`models/`. We just import it.",
    ),

    code(
        "# Quick sanity check that the imports resolve",
        "from models.schemas import ReviewState, Finding, Category, Severity",
        "from graph.pipeline import run_pipeline, build_graph",
        "from run_pipeline import build_report",
        "",
        "graph = build_graph()",
        "print('graph compiled:', graph)",
        "print('node names:', sorted(graph.get_graph().nodes))",
    ),

    md(
        '<a name="runlocal"></a>',
        "## 3. Run the pipeline on a sample file",
        "",
        "We ship a deliberately-buggy sample (`sample_bad_code.py`) in the repo "
        "with planted issues across all four review dimensions. Running it once "
        "exercises every agent end-to-end.",
    ),

    code(
        "with open('/content/MultiAgentCodeReview/sample_bad_code.py') as f:",
        "    sample = f.read()",
        "print(sample)",
    ),

    code(
        "# Run all 6 agents on the sample. Takes ~30-60s end-to-end.",
        "state = run_pipeline('sample_bad_code.py', sample)",
        "print(f'\\nFindings: {len(state.findings)} '",
        "      f'(Critical={sum(1 for f in state.findings if f.severity.value==\"Critical\")}, '",
        "      f'High={sum(1 for f in state.findings if f.severity.value==\"High\")}, '",
        "      f'Medium={sum(1 for f in state.findings if f.severity.value==\"Medium\")}, '",
        "      f'Low={sum(1 for f in state.findings if f.severity.value==\"Low\")})')",
        "print(f'Triage flagged for human review: {state.needs_human_review}')",
        "print(f'Patch generated: {state.patch is not None}')",
        "print(f'Tests generated: {state.tests is not None}')",
    ),

    md("### 3a. The full review report"),
    code(
        "from IPython.display import Markdown, display",
        "display(Markdown(build_report(state)))",
    ),

    md("### 3b. The agent's proposed fixed code"),
    code(
        "if state.patch:",
        "    print(state.patch.fixed_code)",
        "else:",
        "    print('(no patch was produced)')",
    ),

    md("### 3c. The auto-generated pytest suite"),
    code(
        "if state.tests:",
        "    print(state.tests.test_code)",
        "else:",
        "    print('(no tests were produced)')",
    ),

    md(
        '<a name="runpr"></a>',
        "## 4. Review a real GitHub PR",
        "",
        "Same pipeline, but the input is whatever Python files a PR touched. This is "
        "**read-only** — we fetch the PR, run the agents, and render the report. No "
        "comment is posted from this notebook (the live posting is done by the "
        "watcher described in §7).",
        "",
        "Public PRs work without a token (rate-limited). With `GITHUB_TOKEN` set in "
        "Colab Secrets, the rate limit is 5,000 req/hr.",
    ),

    code(
        "from integrations.github_pr import GitHubPRClient, parse_pr_url",
        "from pr_review_core import handle_pr",
        "",
        "# Try one of the demo PRs from the project's own demo app:",
        "PR_URL = 'https://github.com/rahulilla/python-simple-webapp/pull/1'",
        "",
        "owner, repo, number = parse_pr_url(PR_URL)",
        "client = GitHubPRClient()",
        "print(f'reviewing {owner}/{repo} #{number} (auth: {client.authenticated})')",
        "",
        "result = handle_pr(client, owner, repo, number,",
        "                   post_comment=False,  # never post from the notebook",
        "                   require_confirm=False, max_files=5)",
        "",
        "print(f'\\nReviewed {len(result.reviews)} file(s); '",
        "      f'{result.total_findings} total finding(s).')",
    ),

    code(
        "# Render the per-PR aggregated report.",
        "from pr_review_core import build_pr_report",
        "display(Markdown(build_pr_report(result)))",
    ),

    # -----------------------------------------------------------------
    # Phase C — RAG layer
    # -----------------------------------------------------------------
    md(
        '<a name="rag"></a>',
        "## 5. RAG layer — ChromaDB grounded in OWASP / CWE",
        "",
        "The security agent is **optionally grounded** by a small ChromaDB index of "
        "the OWASP Top 10 (2021) plus a curated set of ~37 CWE entries that match "
        "the kinds of issues this pipeline frequently flags (SQL injection, "
        "hardcoded credentials, path traversal, deserialization, etc.).",
        "",
        "Corpus and retriever live at `rag/` in the repo. The security agent reads "
        "`USE_RAG=1` from the environment to opt in — kept off by default so the "
        "watcher and CLI don't need ChromaDB / sentence-transformers installed.",
        "",
        "**Why retrieve at all?** Without grounding, the LLM occasionally invents "
        "CWE numbers or misclassifies issues. Retrieval pulls the closest 4 entries "
        "from a real catalogue and splices them into the prompt as a 'use these "
        "labels' hint. Output gets more consistent and citable.",
    ),

    md("### 5a. Inspect the corpus"),
    code(
        "from rag.corpus import OWASP_TOP_10, CWE_ENTRIES, all_documents",
        "",
        "docs = all_documents()",
        "print(f'OWASP entries: {len(OWASP_TOP_10)}')",
        "print(f'CWE entries:   {len(CWE_ENTRIES)}')",
        "print(f'Total docs:    {len(docs)}\\n')",
        "",
        "# Show one entry as a sample",
        "sample = OWASP_TOP_10[2]   # OWASP-A03 Injection",
        "print(f\"{sample['id']} — {sample['title']}\")",
        "print(sample['text'])",
    ),

    md(
        "### 5b. Build the index and inspect a query",
        "",
        "First call to `get_retriever().query(...)` lazily builds the ChromaDB "
        "collection — downloads the `all-MiniLM-L6-v2` embedder (~80 MB) on first "
        "use, then embeds all 47 corpus entries. ~10–20 s on Colab, faster on "
        "subsequent queries.",
    ),
    code(
        "from rag.retriever import get_retriever, format_context",
        "",
        "retriever = get_retriever()",
        "",
        "# Query with the same kind of code snippet the security agent sees.",
        "snippet = '''",
        "import sqlite3",
        "def get_user(uid):",
        "    conn = sqlite3.connect('users.db')",
        "    return conn.execute('SELECT * FROM users WHERE id = ' + str(uid)).fetchone()",
        "API_KEY = 'sk_live_HARDCODED'",
        "'''",
        "",
        "hits = retriever.query(snippet, k=4)",
        "for h in hits:",
        "    print(f'{h.score:.3f}  {h.id:10} {h.title}')",
    ),

    md("### 5c. The same snippet, formatted as the prompt context the agent sees"),
    code(
        "print(format_context(hits))",
    ),

    md(
        "### 5d. Re-run the security agent with RAG ON",
        "",
        "We compare the same input file with `USE_RAG` off vs on. Expectation: with "
        "RAG on, every security finding's `cwe` field is a real ID drawn from our "
        "corpus, not a guessed number; descriptions reference OWASP categories.",
    ),
    code(
        "import os",
        "from agents.security_agent import analyze as security_analyze",
        "from models.schemas import ReviewState",
        "",
        "# Same sample as section 3 — small, fast, has multiple known CWEs.",
        "sample_state_no_rag = ReviewState(file_name='sample_bad_code.py', source_code=sample)",
        "os.environ.pop('USE_RAG', None)",
        "_ = security_analyze(sample_state_no_rag)",
        "",
        "sample_state_rag = ReviewState(file_name='sample_bad_code.py', source_code=sample)",
        "os.environ['USE_RAG'] = '1'",
        "_ = security_analyze(sample_state_rag)",
        "",
        "print('\\n--- without RAG ---')",
        "for f in sample_state_no_rag.findings:",
        "    print(f'  [{f.severity.value}] {f.title} (cwe={f.cwe})')",
        "print('\\n--- with RAG ---')",
        "for f in sample_state_rag.findings:",
        "    print(f'  [{f.severity.value}] {f.title} (cwe={f.cwe})')",
    ),

    # -----------------------------------------------------------------
    # Phase D — Gradio UI
    # -----------------------------------------------------------------
    md(
        '<a name="gradio"></a>',
        "## 6. Gradio UI",
        "",
        "A small Gradio app that lets a non-technical reviewer drop in a Python "
        "file and get the same multi-agent review output as the cells above — "
        "without writing any code.",
        "",
        "Running the cell launches the UI inline below the notebook. Upload a "
        "`.py` file, click **Run review**, and the report renders. A second "
        "button packages the report + fixed code + tests into a downloadable "
        "ZIP.",
        "",
        "**Note on Colab:** Gradio in Colab serves the UI via a tunnel — the "
        "first launch can take ~5 s. Closing the tab does NOT stop the server; "
        "use `demo.close()` in the cell below to release the port.",
    ),

    code(
        "import gradio as gr",
        "import zipfile, tempfile, os",
        "from pathlib import Path",
        "from graph.pipeline import run_pipeline",
        "from run_pipeline import build_report",
        "",
        "",
        "def _review_uploaded_file(file_obj):",
        "    \"\"\"Gradio handler: read the upload, run the pipeline, return outputs.\"\"\"",
        "    if file_obj is None:",
        "        return '⚠️ Please upload a Python file first.', None, None, None",
        "",
        "    # gradio 4.x can hand us either a filesystem path string (default",
        "    # type='filepath') or a NamedString-like object with .name. Handle both.",
        "    file_path = file_obj if isinstance(file_obj, str) else getattr(file_obj, 'name', None)",
        "    if not file_path:",
        "        return '⚠️ Could not read uploaded file.', None, None, None",
        "    path = Path(file_path)",
        "    if path.suffix != '.py':",
        "        return f'⚠️ Expected a .py file, got {path.suffix!r}.', None, None, None",
        "",
        "    source = path.read_text(encoding='utf-8')",
        "    state = run_pipeline(path.name, source)",
        "",
        "    report = build_report(state)",
        "    fixed = state.patch.fixed_code if state.patch else '# (no patch generated)\\n'",
        "    tests = state.tests.test_code if state.tests else '# (no tests generated)\\n'",
        "",
        "    # Bundle everything into a ZIP for download.",
        "    tmp_dir = tempfile.mkdtemp()",
        "    stem = path.stem",
        "    report_path = Path(tmp_dir) / f'{stem}_review.md'",
        "    fixed_path  = Path(tmp_dir) / f'{stem}_fixed.py'",
        "    tests_path  = Path(tmp_dir) / f'test_{stem}.py'",
        "    zip_path    = Path(tmp_dir) / f'{stem}_review.zip'",
        "    report_path.write_text(report, encoding='utf-8')",
        "    fixed_path.write_text(fixed, encoding='utf-8')",
        "    tests_path.write_text(tests, encoding='utf-8')",
        "    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:",
        "        for p in (report_path, fixed_path, tests_path):",
        "            zf.write(p, arcname=p.name)",
        "    return report, fixed, tests, str(zip_path)",
        "",
        "",
        "with gr.Blocks(title='Multi-Agent Code Review') as demo:",
        "    gr.Markdown('# 🤖 Multi-Agent Code Review\\nUpload a Python file to "
        "review it with the full 6-agent pipeline.')",
        "    with gr.Row():",
        "        upload = gr.File(label='Python file (.py)', file_types=['.py'])",
        "        run_btn = gr.Button('Run review', variant='primary')",
        "    report_md = gr.Markdown(label='Report')",
        "    with gr.Accordion('Fixed code', open=False):",
        "        fixed_box = gr.Code(language='python')",
        "    with gr.Accordion('Generated pytest suite', open=False):",
        "        tests_box = gr.Code(language='python')",
        "    bundle_dl = gr.File(label='Download ZIP bundle', interactive=False)",
        "",
        "    run_btn.click(",
        "        _review_uploaded_file,",
        "        inputs=upload,",
        "        outputs=[report_md, fixed_box, tests_box, bundle_dl],",
        "    )",
        "",
        "demo.launch(inline=True, debug=False, share=False)",
    ),

    # -----------------------------------------------------------------
    # Phase E — Architecture writeup
    # -----------------------------------------------------------------
    md(
        '<a name="arch"></a>',
        "## 7. Architecture beyond this notebook",
        "",
        "The notebook demonstrates the **review pipeline** end-to-end. Around it "
        "sits a small piece of *live infrastructure* that turns the pipeline into "
        "a continuous code reviewer for real GitHub repos. Those parts are not "
        "started from this notebook — they need to run continuously, which is a "
        "poor fit for a notebook lifetime — but they share the same pipeline code "
        "and the same `pr_review_core.handle_pr` entrypoint we used in §4.",
        "",
        "### 7.1 The two-repo loop",
        "",
        "```",
        "┌──────────────────────────────────┐         ┌──────────────────────────────────┐",
        "│  rahulilla/MultiAgentCodeReview  │         │  rahulilla/python-simple-webapp   │",
        "│  (the reviewer)                  │         │  (the target — Flask + /health)   │",
        "│                                  │         │                                   │",
        "│  • watch_prs.py polls every 20s  │ reviews │  • Open a PR                      │",
        "│  • 6-agent LangGraph pipeline    │  + posts│  • CI runs:                       │",
        "│  • RAG-grounded security agent   │  comment│      pytest + boot + curl /health │",
        "│  • Patch + test generation       │ ──────► │      → assert HTTP 200            │",
        "│  • agent_pr_proposer:            │         │                                   │",
        "│      push fixes branch           │         │  • Apply suggested fixes          │",
        "│      ↳ workflow_dispatch CI      │         │  • Merge                          │",
        "│      ↳ open follow-up PR ONLY    │         │  • CI re-validates → green ✅     │",
        "│        if CI is green            │         │                                   │",
        "└──────────────────────────────────┘         └──────────────────────────────────┘",
        "```",
        "",
        "### 7.2 Polling watcher (`watch_prs.py`)",
        "",
        "A long-running local process polls a target repo every 20 s. When it sees "
        "a PR it hasn't reviewed yet (keyed by `(pr_number, head_sha)`, persisted "
        "across restarts), it calls the same `handle_pr` we used in §4 — but with "
        "`post_comment=True` so the findings land on the PR.",
        "",
        "```bash",
        "export GITHUB_TOKEN=...      # PAT with write to the target repo",
        "python watch_prs.py rahulilla/python-simple-webapp",
        "```",
        "",
        "Resilient to flaky networks (catches `requests.RequestException` with "
        "exponential backoff). Pre-seeds existing PRs on startup so it only "
        "reacts to *new* ones.",
        "",
        "### 7.3 Agent-PR proposer (`agent_pr_proposer.py`) — the CI-gated follow-up PR",
        "",
        "After the findings comment posts, the proposer:",
        "",
        "1. Branches `<user-branch>-agent-suggested` off the PR's head SHA",
        "2. Commits the agent's fixed files",
        "3. Triggers CI on that branch via `workflow_dispatch`",
        "4. Polls the workflow run for up to 5 minutes",
        "5. **Green** → opens a follow-up PR (base = user's branch). Comment on the "
        "   original PR linking it.",
        "6. **Red / timeout** → does **NOT** open the PR. Comment on the original "
        "   PR with the failed run URL so the human stays in the loop.",
        "",
        "### 7.4 Live evidence",
        "",
        "All three demo paths are working in the wild on `rahulilla/python-simple-webapp`:",
        "",
        "| Demo PR | Path | Result |",
        "|---------|------|--------|",
        "| [PR #1](https://github.com/rahulilla/python-simple-webapp/pull/1) — Add /echo endpoint (4 planted issues) | review + propose-fixes (CI green) | findings comment + [follow-up PR #2](https://github.com/rahulilla/python-simple-webapp/pull/2) opened |",
        "| [PR #3](https://github.com/rahulilla/python-simple-webapp/pull/3) — Bump version (forced bad fix) | propose-fixes with `AGENT_FIX_INJECT_BAD=1` | [CI run #6](https://github.com/rahulilla/python-simple-webapp/actions/runs/27474531416) failed; **no** follow-up PR opened, failure-link comment posted |",
        "",
        "PR #3 in particular proves the gate is real, not decorative — when the "
        "agent's fixes break the app, CI catches it and the bad PR is never "
        "exposed for review.",
    ),

    # -----------------------------------------------------------------
    # Phase F — Future work + close
    # -----------------------------------------------------------------
    md(
        '<a name="future"></a>',
        "## 8. Future work",
        "",
        "Concrete extensions beyond this deliverable, in priority order:",
        "",
        "1. **CodeBERT security classifier** — drop-in replacement for the "
        "   LLM-based security agent (already designed for this — same `analyze` "
        "   interface). Faster and more deterministic for the security pass.",
        "2. **Confidence-filter for the bug agent** — at temperature 0.2 the bug "
        "   agent occasionally emits self-hedging findings (\"this could fail "
        "   *if* the function is later called…\"). A confidence field plus a "
        "   threshold filter would cut these.",
        "3. **Inline GitHub `suggestion` blocks** — replace the summary comment "
        "   with line-anchored review comments using GitHub's `\\`\\`\\`suggestion`"
        " blocks so reviewers click \"Commit suggestion\" and the fix lands "
        "directly on the PR branch.",
        "4. **CodeLlama fallback in Colab** — `llm/backend.py` already supports "
        "   it; this notebook always uses GPT-4o. Adding a `LLM_BACKEND=codellama` "
        "   demo cell would prove the keyless reproducibility claim end-to-end.",
        "5. **Bot identity** — comments and follow-up PRs are currently attributed "
        "   to the token owner. A dedicated GitHub App named `code-review-agent` "
        "   would surface them with a `bot` badge.",
        "",
        "---",
        "",
        "✅ End of notebook. To go deeper, every module is on the repo: "
        f"[{REPO_URL}]({REPO_URL}).",
    ),
]


notebook = {
    "nbformat": 4,
    "nbformat_minor": 0,
    "metadata": {
        "colab": {
            "provenance": [],
            "toc_visible": True,
            "name": "multi_agent_code_review.ipynb",
        },
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
    },
    "cells": cells,
}

OUT = "multi_agent_code_review.ipynb"
with open(OUT, "w") as f:
    json.dump(notebook, f, indent=1)

print(f"Built {OUT} with {len(cells)} cells.")
