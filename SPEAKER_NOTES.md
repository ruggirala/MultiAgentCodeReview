# Speaker notes — Multi-Agent Code Review capstone

This file is for the six team members presenting the deck. Each slide
gets a short brief: what to say (90 seconds at normal pace), what to
point at on screen, the one judge question most likely on that slide,
and the overclaims to avoid.

You don't have to read the **What to say** verbatim — it's a floor,
not a script. Paraphrase, but stay inside the boundaries set by
**Don't say**.

## Slide 1 — Title

**Big idea.** Set the room. Six-person team, one project, open-source
repo.

**Killer opener (10 lines — say this first, look up, smile).**
1. "Every engineering team in this room has the same bottleneck.
2.  It isn't writing code. It's reviewing it.
3.  Pull requests sit for hours. Bugs slip through. Senior reviewers burn out.
4.  And the slowest, most expensive humans on the team are the ones holding the queue.
5.  So we built something different.
6.  Five specialized AI agents that review every pull request before a human even opens it.
7.  Security. Bugs. Performance. Style. Each one an expert in one thing.
8.  We're six engineers. The project is open-source. The deck you're seeing is served from the same repo.
9.  In the next fifteen minutes we'll show you the system, the numbers, and a real PR getting reviewed in under a minute.
10. I'm <name>. Let's begin."

**What to say.** "Our capstone is a Multi-Agent Code Review system —
a LangGraph pipeline of five AI agents that reviews every GitHub
pull request for security, bugs, performance, and style. We built it
because code review is the slowest, most error-prone step in any
team's PR flow, and it scales worst at exactly the moment teams need
it most. Everything is open-source — the repo URL is at the bottom.
The deck itself is served from that repo on GitHub Pages. I'll hand
off to <next speaker> to walk through the problem."

**What to point at.** Title hero, team-member list at the bottom,
repo link.

**Likely judge question.** *"Six people on one project — how did you
split the work?"* Honest answer: pipeline architecture and LangGraph
plumbing (X), agent prompts + RAG (Y), telemetry + dashboard (Z),
GitHub integration + watcher (W), load test + evaluation (V), slides
+ design (U). Pick your own split when answering.

**Don't say.** "Production-ready" — it's a capstone, not a product.

---

## Slide 2 — Why this exists

**Big idea.** Hook the room with the value proposition, not the
problem. Two concrete numbers — speed and cost — from our own load
test.

**Killer opener (10 lines — punch in, name the cost, then the win).**
1. "Picture the last pull request you opened. How long did it sit there before someone reviewed it?
2.  Hours? A day? Across a whole team, that delay compounds into weeks of lost shipping velocity every quarter.
3.  And when the review finally happens, it's inconsistent — depends on who looked, how tired they were, what they happened to notice.
4.  Security bugs slip through. Performance regressions slip through. Style debates eat the comments.
5.  That's the gap we set out to close.
6.  Five specialized AI agents do the first pass on every PR — before a human opens it.
7.  Security, bugs, performance, style — each agent is an expert in one thing.
8.  On our load test: every PR reviewed in about a minute. Fourteen cents each. Findings cite real CWE numbers.
9.  The agent doesn't just complain — it commits its suggested fix as a follow-up pull request the reviewer can merge or reject.
10. The human still decides. We just gave them a clean starting point."

**What to say.** "Code review at most companies is slow, inconsistent,
and bottlenecked on senior engineers. We built five specialized AI
agents that do the first pass on every PR before a human opens it.
Each one focuses on one dimension — security, bugs, performance, or
style — and produces structured findings, not freeform text. On our
load test we reviewed every PR in about a minute, at fourteen cents
each. Findings cite real CWE numbers, not hallucinated categories,
and the agent's suggested fix shows up as a follow-up PR a reviewer
can merge or reject."

**What to point at.** The "~1 min" tile, the "$0.14" tile, the
animated 6-agents stamp in the top-right corner.

**Likely judge question.** *"How is this different from Copilot's PR
review or other LLM code reviewers?"* Honest answer: most are a
single big prompt against the diff. We use multiple specialized
agents over typed Pydantic state, RAG-grounded security findings,
and a real telemetry dashboard. Slide 6 covers our design choices
in detail.

**Don't say.** "Replaces human reviewers." It augments them — the
human still has to merge.

---

## Slide 3 — System architecture

**Big idea.** Show the LangGraph state machine end-to-end. One
typed object flows through every node.

**What to say.** "The system is a LangGraph state machine. A
`ReviewState` Pydantic object enters at the top — file name, source
code — and walks through eight nodes in order. The orchestrator
parses the file into chunks using tree-sitter. Then security, bug,
and style agents each add findings to the shared state. Triage
checks if any are Critical or High security — if yes, the flow
routes through a `human_review` checkpoint. Patch generates the
fixed code. Tests generate a pytest suite. The final state is
serialized and posted back to GitHub as a comment, plus a follow-up
PR with the fix. The whole thing is one function call:
`app.invoke(initial_state)`."

**What to point at.** The animated SVG flow paths, the central
shared-state node, the conditional `human_review` branch.

**Likely judge question.** *"What if one agent fails — does the
whole pipeline crash?"* Honest answer: each node is wrapped in
try/except. A failed agent records its error to `state.errors` and
the pipeline continues. The dashboard's agent-error-rate KPI tracks
this; in our load test it's been zero across 240+ LLM calls.

**Don't say.** "Every agent is an LLM call." Only five of them are
— orchestrator and triage are deterministic Python.

---

## Slide 4 — Per-PR pipeline flow

**Big idea.** Same flow as slide 3, but with real timing numbers
attached to each node.

**What to say.** "This is the same pipeline, but timed. Median
durations from our 30-PR load test: orchestrator parses in
milliseconds. Security and bug agents each take three-to-six
seconds — they're LLM calls. Style takes about three seconds —
it runs pylint and radon locally before the LLM perf pass. Triage
and human_review are instant; they're Python conditionals. Patch
and tests dominate at around 21 seconds each — they're generating
longer outputs. Total: under a minute median. Patch and tests are
the bottleneck, and they're sequential because tests reads the
patched code."

**What to point at.** The 8-node row across the slide, the timing
under each box, the patch + tests pair at the right (the bottleneck).

**Likely judge question.** *"Why not parallelize security, bug, and
style? They're independent."* Honest answer: they share one
mutable `ReviewState`. Parallelizing means lock contention on
`findings.extend()`. We chose sequential because patch+tests
dominate the total time anyway — parallelizing the analysis trio
saves about six seconds out of ninety.

**Don't say.** "Human review pauses the pipeline." It's a
logged-only checkpoint today — see slide 6.

---

## Slide 5 — Under the hood

**Big idea.** Concrete tech stack. Ten logo pills the judges
recognize.

**What to say.** "The stack is intentionally boring. LangGraph for
the state machine. Pydantic v2 for every cross-agent data shape.
tree-sitter for code parsing, with a stdlib `ast` fallback. ChromaDB
for the RAG corpus with all-MiniLM-L6-v2 embeddings. GPT-4o on the
OpenAI API for the analysis and generation agents, with CodeLlama
7B 4-bit as a keyless fallback for Colab. pylint and radon for
static analysis. Streamlit and Plotly for the dashboard. GitHub
REST API for the watcher and PR comments. Each library here was
chosen to solve one specific problem — we'll cover the why on the
next slide."

**What to point at.** Each row of pills, briefly.

**Likely judge question.** *"Why all-MiniLM-L6-v2 for the
embeddings?"* Honest answer: small (80 MB), CPU-friendly, fits the
Colab T4 budget alongside CodeLlama. The CWE corpus is short
paragraphs — a bigger model would buy precision we don't need.

**Don't say.** "We use frontier models." GPT-4o is the OpenAI tier;
CodeLlama-7B is not a frontier model.

---

## Slide 6 — Design choices

**Big idea.** Show six pivot points where we made a real decision,
with the alternative we rejected.

**What to say.** "Six design decisions worth defending. We chose
LangGraph over raw LangChain chains for explicit conditional edges.
Pydantic state over free-form text between agents — the schema is
enforced server-side by OpenAI Structured Outputs. Sequential
agents over parallel because one shared `ReviewState` rules out
parallel writes to the findings list. JSONL append-only over a
real database because there's nothing to operate and Streamlit can
tail the file. A hybrid LLM backend so the system runs keyless on
Colab. And a hand-curated load-test corpus of 30 buggy templates
over LLM-generated bugs, because deterministic re-runs let us grade
the pipeline. Each card on the slide explains the why."

**What to point at.** The central orb (the brand mark), then the
six wedges in order. Pause on wedge 02 — Structured Outputs is the
strongest single technical bet.

**Likely judge question.** *"What if the LLM responds with malformed
JSON?"* Honest answer: it can't, in strict mode. We pass a
Pydantic-derived JSON Schema with `strict: true` to OpenAI's API.
The API guarantees schema-conformant output or returns a refusal.
We catch refusals and re-validate client-side as belt-and-suspenders.

**Don't say.** "Human review blocks merges." It doesn't yet — the
node is wired but doesn't gate.

---

## Slide 7 — Grounded with RAG

**Big idea.** Why our security findings cite real CWE numbers, not
hallucinated categories.

**What to say.** "Without grounding, an LLM asked 'is this SQL
injection?' will tell you yes and call it CWE-89 from memory — but
the explanation might cite a real CWE or invent one. We embedded
the actual CWE database and OWASP Top-10 entries into a ChromaDB
collection using all-MiniLM-L6-v2. When the security agent runs,
it embeds the source chunk, retrieves the top-K matching CWE
descriptions from Chroma, and includes them verbatim in the prompt.
The model then cites a real CWE because it's looking at the real
text. Toggle is one env var, `USE_RAG=1`. The architecture extends
to OWASP-specific findings later."

**What to point at.** The corpus box, the retrieve arrow into the
security agent, an example finding with `CWE-89` highlighted.

**Likely judge question.** *"Does RAG prevent the model from
hallucinating?"* Honest answer: no — it grounds the answer in
retrievable text, which sharply reduces hallucinations, but the
model can still fabricate a line number or paraphrase the CWE
text wrong. RAG is a strong mitigation, not a guarantee.

**Don't say.** "RAG is always on" — it's off by default; the
watcher runs without it unless `USE_RAG=1`.

---

## Slide 8 — What the agent posts

**Big idea.** Show the agent's actual GitHub comment, not a mockup.

**What to say.** "This is the real comment the agent posted on a
load-test PR. Header has the file name and findings count. Then a
severity table grouped by file — Critical, High, Medium, Low — so a
human can scan it in five seconds. Then every finding with its
severity, category, location, CWE if applicable, and a one-line
suggested fix. The format is deterministic because every finding
is a Pydantic `Finding` object — the comment renderer is just a
template over typed data. There's also a markdown report and a
zip of fixed code stored locally, plus the agent's suggested
patch on a sibling branch as a follow-up PR."

**What to point at.** The severity table, the CWE-22 chip in the
first finding, the recommendation line.

**Likely judge question.** *"What stops the comment from being
spammy on a PR with hundreds of findings?"* Honest answer:
the comment is capped at 65,536 characters (GitHub's limit) and
truncates with a marker if exceeded. Per-PR file count is also
capped at 10 with `--max-files`. We've never hit either limit
in practice but the safety net is there.

**Don't say.** "Always cites a CWE." Only the security agent cites
CWEs; bug, style, and performance findings don't.

---

## Slide 9 — Telemetry & dashboard

**Big idea.** Every run emits structured events. The dashboard
makes them legible.

**What to say.** "Every PR review emits four event types to a JSONL
file: one `pr_review` event per PR with counts and severities, one
`agent` event per LangGraph node with timing and findings-added,
one `llm_call` event per API call with backend, model, tokens, and
retries, and one `poll_cycle` event per watcher iteration. The
Streamlit dashboard tails that file and auto-refreshes every ten
seconds. The screenshot shows the Overview tab — KPI cards with
sparklines, recent activity table with clickable PR links. The
LLM telemetry tab on the right shows cost per PR. Everything you
see is computed from real load-test data, not mocked."

**What to point at.** The KPI strip (PRs, findings, cost), the
recent-activity table, the live indicator.

**Likely judge question.** *"How does the dashboard know about a
new event without polling everything?"* Honest answer: it polls.
Streamlit's `@cache_data(ttl=10)` re-reads the JSONL every ten
seconds. The file is small enough — about 500 events from the
load test totals 150 KB. We'd switch to incremental reads or
DuckDB if it grew to a million events.

**Don't say.** "Real-time." Ten-second cache makes it near-real-
time, but not real-time.

---

## Slide 10 — Live demo

**Big idea.** Show the system actually working. 2:38 of recording
already plays muted on loop on the slide.

**What to say.** "What you're seeing is a real recording from
yesterday. I'm opening a buggy PR on a real GitHub repo —
python-simple-webapp, our demo target. The watcher polls the repo
every 20 seconds and detects the new PR. The pipeline runs each
agent — you can see the terminal log in the middle: orchestrator,
security, bug, style, triage, patch, tests. The agent posts its
review comment on the PR — there on the left. Then the
agent_pr_proposer opens a follow-up PR with the suggested fix on
a sibling branch. GitHub Actions runs the health check workflow.
The dashboard on the right ticks up — PR count, finding count,
cost. No edits, no retakes. Total elapsed time about 90 seconds."

**What to point at.** Let the video play; gesture at the terminal
log, the PR comment, the dashboard KPI ticking up — in that
order, matching the video.

**Likely judge question.** *"What if I open ten PRs at once?"*
Honest answer: the watcher reviews them sequentially. Each one
takes about a minute, so ten PRs would take ten minutes. We could
parallelize across PRs (not agents within a PR) but haven't — it
hasn't been the bottleneck in practice.

**Don't say.** "Production-grade reliability." It's a capstone
demo; we haven't run it for weeks unattended.

---

## Slide 11 — Load-test results

**Big idea.** 30 PRs, 0 failures, real numbers.

**What to say.** "We built a load test to validate the pipeline
under realistic conditions. The load_test driver opens 30
deliberately-buggy PRs sequentially against a real Airflow fork
on GitHub — ten security templates, ten bug templates, five
performance, five style. Each one is hand-curated so we know
exactly what the agents should catch. The pipeline reviewed all
30 in under 50 minutes total, with zero failures. Median review
took 59.5 seconds. Total findings: 627 across all four categories.
Twenty-four out of thirty PRs were correctly flagged for human
review because they contained Critical or High security findings.
Total OpenAI cost was $4.56."

**What to point at.** The KPI tiles in order, the
findings-by-category bar chart, the "0 failures" claim.

**Likely judge question.** *"Why only 30 PRs?"* Honest answer:
the load test is meant to validate the pipeline under sequential
load, not to exhaust the model. 30 is enough to see steady-state
behavior — latency, cost-per-PR, error rate — without burning
through token budget. We could run 300 if the question is "does
it still work at that scale."

**Don't say.** "Production-scale." Thirty PRs sequentially is a
floor, not a ceiling.

---

## Slide 12 — Evaluation

**Big idea.** Honest measurement. We measure recall on planted
bugs, not precision.

**What to say.** "Each load-test template plants a bug we know the
category of — SQL injection is Security, mutable default arg is
Bug, etc. The eval scorer asks: did the pipeline produce at least
one finding in every expected category? On all 30 templates, the
answer is yes — 100% recall. Per-category: 10 of 10 Security,
10 of 10 Bug, 5 of 5 Performance, 6 of 6 Style. We deliberately
don't measure precision here, because each PR also touches real
Airflow code with its own legitimate findings — and we don't have
ground truth on those. Hand-spot-checks on 8 templates confirm
7 of 8 cited the precise CWE."

**What to point at.** The four per-category bars, the recall
KPI tiles, the "what this measures (and what it doesn't)" panel.

**Likely judge question.** *"100% recall on a benchmark you
designed yourself isn't a strong claim."* Honest answer: agreed.
It's the floor — it proves the pipeline catches textbook bug
patterns reliably. The next step would be a labeled real-world PR
corpus for precision and recall together, which is a separate
project we scoped out of capstone.

**Don't say.** "Achieves 100% recall." Achieves 100% on a benchmark
we designed — phrasing matters.

---

## Slide 13 — Case studies

**Big idea.** Five concrete bugs from the load test, not curated
demos. Receipts for the claims on earlier slides.

**What to say.** "Five real bugs the pipeline caught on a real
Airflow fork. SQL injection — CWE-89, agent flagged the string
concat. Hardcoded API key — CWE-798, recognized the `sk_live_…`
prefix as a real-looking Stripe key. Mutable default argument —
the Python-specific footgun where a list default is shared across
calls. Quadratic string concat in a loop — performance category,
the agent caught the algorithmic anti-pattern. And pathological
cyclomatic complexity — this last one is the most interesting,
because radon caught it as a structural metric and GPT-4o caught
a semantic gap in the same function from a different angle. Two
agents agreeing on the same function. Each card on the slide
links to a full write-up in the case_studies folder of the repo."

**What to point at.** Each card briefly, lingering on the
pathological-complexity one. The summary panel.

**Likely judge question.** *"Did the two agents really agree on
the same line, or different aspects of the same function?"*
Honest answer: different aspects. Radon flagged the function-level
complexity metric (CC=14). GPT-4o flagged a semantic gap in the
region check. Same function, different findings — but two
agents independently identified that this function was worth
attention.

**Don't say.** "Two agents triangulated on the same bug." They
agreed the function had a problem — not the exact same bug.

---

## Slide 14 — What we'd improve next

**Big idea.** Three measurable goals we'd chase if this were
ongoing. Honest about gaps.

**What to say.** "Three goals worth pursuing. Speed — get the p95
latency from 93 seconds today to under 30, by parallelizing across
PRs and switching the lighter agents to GPT-4o-mini. Languages —
the pipeline only reads Python today; tree-sitter already supports
Java, JavaScript, and Go, but each language needs lang-specific
prompts. Cost — currently 14 cents per PR, target 5 cents by
routing simple diffs to the cheaper model and only reaching for
GPT-4o on high-severity findings. None of these are research
problems — they're engineering work we'd ship in a real product."

**What to point at.** Each of the three measured-today cards, the
today→target arrow on each.

**Likely judge question.** *"Why isn't there a goal about
precision?"* Honest answer: because we haven't measured precision
yet — it'd be intellectually dishonest to set a target for a
number we don't currently have. The right next step there is a
labeled real-PR corpus, which is a separate project.

**Don't say.** "We'll be production-ready by Q3." We have no
operational commitment.

---

## Slide 15 — Q&A / Links

**Big idea.** Open the floor. Show the repo URL prominently so the
judges can click through.

**What to say.** "That's everything we built. Repo URL is at the
top — slide deck is in there too, served via GitHub Pages.
Happy to take questions on any agent, any design decision, the
load test, or the dashboard. The case studies linked from
slide 13 each have a verbatim agent comment if you want to see
exactly what the agents produced."

**What to point at.** The repo link, the live URL.

**Likely judge question.** *"What surprised you while building
this?"* Pick one honestly — examples: how often the LLM produces
plausible-but-wrong findings on real code; how much the
structured-outputs API improved reliability; how much faster than
expected the median review came in.

**Don't say.** Anything that sounds like you're winding down before
the questions are over. Answer until the moderator stops you.
