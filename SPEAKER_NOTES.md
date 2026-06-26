# Speaker notes — Multi-Agent Code Review capstone

This file is for the six team members presenting the deck. Each slide
gets a short brief: what to say (90 seconds at normal pace), what to
point at on screen, the one judge question most likely on that slide,
and the overclaims to avoid.

You don't have to read the **What to say** verbatim — it's a floor,
not a script. Paraphrase, but stay inside the boundaries set by
**Don't say**.

## Slide 1 — Title

**Big idea.** Set the room. Introduce the team, the project, and
where it lives. Get the audience curious enough to want slide 2.

**Opening — say this as one connected story, not a list.**

"Good morning, everyone. Thank you for being here.

Before we tell you what we built, let me tell you why we built it.

Every engineering team has the same hidden bottleneck. It isn't
writing code — teams have gotten very good at that. It's reviewing
the code. Pull requests sit for hours. Bugs slip through. The senior
engineers who should be designing systems end up spending their day
reading other people's code, line by line. And as the team grows,
the problem gets worse, not better.

So we asked a simple question. What if the first pass on every pull
request didn't have to be a tired human at the end of their day?
What if it could be five specialized AI agents — one for security,
one for bugs, one for performance, one for style — each focused on
the one thing it does best? And what if those agents didn't just
complain, but actually proposed the fix as a follow-up pull request
the human could merge or reject?

That is what we built. It's called the Multi-Agent Code Review
system. The whole project is open-source, the repository link is at
the bottom of the slide, and the slide deck you are watching right
now is served from that same repository.

We're a team of six. Over the next fifteen minutes we'll walk you
through the system, the design choices, the real numbers we measured
on a 30-PR load test, and a live demo of an actual pull request
getting reviewed in under a minute. My name is <name>, and I'll be
handing over to <next speaker> in a moment to take you through why
this problem matters."

**What to point at.** The project title at the top, the team
members listed underneath, the repository link.

**Likely judge question.** *"Six people on one project — how did
you split the work?"* Honest answer: each member owned a different
slice — pipeline + LangGraph plumbing, agent prompts + the RAG
layer, telemetry + dashboard, GitHub integration + the watcher,
load testing + evaluation, slides + design. Pick the split that
matches reality when answering.

**Don't say.** "Production-ready." This is a capstone, not a
product. Lead with what we measured, not what we promise.

---

## Slide 2 — Why this exists

**Big idea.** Hook the room with the value proposition, not the
problem. Two concrete numbers — speed and cost — from our own load
test.

**Opening — say this as one connected story, not a list.**

"Let me start with a question. Picture the last pull request you
opened. How long did it sit there before someone reviewed it? Hours?
A day? For most teams, the answer is at least one of those — and
across an entire engineering organization, that delay compounds
into weeks of lost shipping velocity every quarter.

And when the review finally happens, it's inconsistent. It depends
on who looked, how tired they were, and what they happened to
notice that day. Security issues slip through. Performance
regressions slip through. Style debates eat half the comments.

That is the gap we set out to close.

What we built is right here on the slide. Five specialized AI
agents that do the first pass on every pull request, before a human
opens it. One for security. One for bugs. One for performance. One
for style. Each one is an expert in just the one thing — and that
focus is what makes them consistent.

The numbers on the screen are real. On our 30-PR load test, every
pull request was reviewed in about a minute, at fourteen cents each.
A 100-PR-per-week team would spend roughly fourteen dollars a week
on this — less than one engineer-hour. And the agent doesn't just
complain. It commits its suggested fix as a follow-up pull request
the reviewer can merge or reject.

The human still decides. We've just made sure they're not the first
line of defense — we are."

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
animated 5-agents stamp in the top-right corner.

**Likely judge question.** *"How is this different from Copilot's PR
review or other LLM code reviewers?"* Honest answer: three concrete
differences. One — multi-agent pipeline, not one prompt; each agent
has a single mental frame (security, bugs, performance, style) and
the cross-agent contract is typed Pydantic, validated server-side by
OpenAI Structured Outputs. Two — every security finding cites a real
CWE because we RAG-ground against the actual CWE database, not the
model's recollection. Three — we commit the suggested fix as a
follow-up PR with a generated pytest suite, not just a comment. Plus
real telemetry on a live dashboard — 30 PRs, $4.56 total, 100%
recall on planted bugs. Slide 6 covers the design choices; slide 7
covers the RAG layer.

**Don't say.** "Replaces human reviewers." It augments them — the
human still has to merge.

---

## Slide 3 — System architecture

**Big idea.** Show the LangGraph state machine end-to-end. One
typed object flows through every node. This is the deepest
architectural slide — plan to spend two and a half minutes here.

**Opening — say this as one connected story, not a list.**

"This is the most important architectural slide in the deck, so I'm
going to take a couple of minutes to walk you through it carefully.
Everything we say later — about agents, RAG, telemetry, the
follow-up PR — assumes you understand this picture.

Let me start with the boundaries. At the top of the slide, a pull
request gets opened on GitHub. That's our input. At the bottom, two
things appear back on that pull request — a structured review
comment, and a follow-up pull request that contains the suggested
fix and a generated pytest suite. That's our output. Everything in
between is the system itself.

The system is a state machine built on LangGraph. There are eight
nodes, arranged in a directed graph with one conditional branch.
The framework gives us three things that mattered to us — explicit
edges between nodes, retry logic built in, and the ability to
declare a conditional edge that pauses the pipeline for human
input. That last point becomes important in a moment.

Now, the most important piece on this slide isn't any of the nodes.
It's the object in the center — the ReviewState. This is a single
Pydantic model that gets passed to every node in sequence. It
carries the file name, the source code, the chunks the orchestrator
produced, the findings each agent added, the patch, the generated
tests, and any errors. Every node receives this state object, does
its work, mutates the state, and returns it. No node talks to any
other node directly — they only communicate through this shared
typed object. That single design choice is what makes the whole
system testable and debuggable.

Let me walk through what each node does.

The orchestrator parses the source code into logical chunks —
functions and classes — using tree-sitter, which is the same parser
GitHub uses for code navigation. It's language-agnostic, which
matters because we want to extend beyond Python. If tree-sitter
isn't available, we fall back to Python's standard library ast
module.

Then we hit the three analysis agents. Security comes first — it
looks for vulnerabilities and, if RAG is enabled, cites real CWE
numbers from the database. Bug runs next, looking for logic errors,
edge cases, mutable defaults, and unhandled exceptions. Style runs
third — it's actually a hybrid that combines pylint and radon
locally with an LLM pass for performance anti-patterns. All three
agents read the same chunks and append their findings to the same
shared list on the state.

Once analysis is done, we hit triage. This node is plain Python —
no LLM. It looks at all the findings collected so far and asks one
question — are there any Critical or High severity security
findings? If yes, the conditional edge routes through a
human_review node, which logs the situation and currently passes
through. The hook is wired so we can extend it to actually pause
the pipeline for a human in the loop, but in today's implementation
it logs and continues.

After that comes patch — the agent that generates the fixed code.
It reads all the findings, takes the original source, and produces
a patched version. Then tests — which reads the patched code and
writes a pytest suite to verify that the fix doesn't regress
anything.

When all eight nodes finish, the state object is fully populated.
We serialize it into a GitHub comment, push the patched code to a
sibling branch named with an 'agent-suggested' suffix, and open a
follow-up pull request. The whole flow — from input to output — is
one function call: app dot invoke of the initial state.

The reason this architecture matters is that every contract between
agents is a Pydantic field, validated at runtime. We never pass JSON
strings between agents and parse them defensively. If an agent
returns the wrong shape, Pydantic raises immediately. That's the
foundation that makes the rest of the system reliable."

**What to point at.** Start at the top of the diagram (PR opens),
then trace down through the orchestrator, the three analysis
agents, the triage diamond, the human-review branch, patch and
tests, and finally the two outputs at the bottom. Pause briefly
on the ReviewState orb in the center — that's the slide's
single most important element.

**Likely judge question.** *"What if one agent fails — does the
whole pipeline crash?"* Honest answer: each node is wrapped in
try/except. A failed agent records its error to `state.errors`
and the pipeline continues. The dashboard's agent-error-rate KPI
tracks this; in our load test it's been zero across 240-plus LLM
calls. If you want a concrete example: if the security agent's
LLM call times out, it returns the state with an error logged,
and the bug and style agents still run normally. The reviewer
gets a partial review instead of no review.

**Other likely follow-ups to be ready for.**
- *"Why eight nodes and not fewer?"* Because each node has one
  responsibility. Mixing security and bug into one prompt makes
  findings shallower — we tested it.
- *"What does the orchestrator actually do?"* It parses the file
  into chunks using tree-sitter so the analysis agents can review
  function-by-function rather than swallowing a giant file.
- *"Why is patch separate from tests?"* Because tests reads the
  patched code as input. They must run sequentially, not in
  parallel. That's the bottleneck on slide 4.
- *"Is the human_review node ever actually used?"* Today it's a
  logged-only pass-through. The hook is wired for a future
  blocking implementation.

**Don't say.** "Every agent is an LLM call." Only five of them
are — orchestrator and triage are deterministic Python with no
LLM, and human_review is just a logging pass-through today.

---

## Slide 4 — Per-PR pipeline flow

**Big idea.** Same flow as slide 3, but with real timing numbers
attached to each node.

**Opening — say this as one connected story, not a list.**

"The previous slide showed you the shape of the system. This one
shows you how long each step actually takes. Every number on this
slide comes from our 30-PR load test — these are median timings, in
seconds, measured on real pull requests.

Let me walk it left to right.

The orchestrator runs in milliseconds. It's just tree-sitter parsing
the source code — no LLM call, no network. The security and bug
agents are the first LLM calls — they each take three to six
seconds, depending on file size. The style agent takes about three
seconds total: it runs pylint and radon locally first, then a short
LLM pass for performance anti-patterns.

Triage and human-review are instant. They're plain Python
conditionals — no LLM involved. They just check whether the
findings count and severity warrant pausing for a human.

Then we hit the bottleneck. The patch agent and the tests agent
each take around 21 seconds, because they generate the longest
outputs — the patched code, and a complete pytest suite. These two
have to run sequentially, not in parallel, because the tests agent
reads the patched code as its input.

So when someone asks 'how can you make this faster?' — patch and
tests is the answer. That's the half of the pipeline worth
parallelizing, and we'll come back to that on slide 14."

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

**Opening — say this as one connected story, not a list.**

"Now we get to the question every audience asks at this point — so
what's actually under the hood?

The rule we set for ourselves was simple. Every tool we picked had
to earn its place. If it wasn't solving a specific problem we had,
it didn't get in. That's why the stack on this slide is
deliberately boring — every logo on the screen is doing one
specific job.

Let me walk you through it.

LangGraph runs the state machine. We picked it for explicit
conditional edges and built-in retry logic. Pydantic v2 enforces
the shape of every piece of data passed between agents. Tree-sitter
parses source code at the AST level — and it's language-agnostic,
which matters when we extend beyond Python. ChromaDB stores our RAG
corpus — the CWE database and OWASP Top-10 entries — embedded with
all-MiniLM-L6-v2, a small, fast, CPU-friendly model.

For the LLM itself, we run a hybrid backend. GPT-4o is the primary,
on OpenAI's structured-outputs path. CodeLlama 7B in 4-bit
quantization is the keyless fallback — it runs on a Colab T4 with
no API key, which means anyone can run this end-to-end without
paying for an OpenAI account.

The dashboard is built on Streamlit and Plotly. It tails our JSONL
telemetry file and refreshes every ten seconds. And for GitHub
integration, we use the raw REST API directly — no PyGithub
wrapper, no extra dependency. Boring, on purpose."

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

**Opening — say this as one connected story, not a list.**

"Every project has decisions you can defend, and decisions you just
made because you had to pick something. This slide is the first
kind. Six places where we made a real architectural bet, with a
clear alternative we rejected.

Let me walk through them.

We picked LangGraph over raw LangChain because we needed explicit
conditional edges and real interrupt points — not just a chain of
prompts. We picked Pydantic state between agents instead of passing
JSON strings, because the schema gets enforced server-side by
OpenAI's Structured Outputs API. The model literally cannot return
malformed JSON.

We kept the agents sequential, not parallel, because they share one
mutable findings list. Parallelizing would mean lock contention and
race conditions for a savings of about six seconds out of a
fifty-seven-second run — not worth the complexity. We picked
append-only JSONL telemetry over a real database, because there's
nothing to operate and Streamlit can tail the file directly.

We picked a hybrid LLM backend — GPT-4o for the dev path, CodeLlama
for the keyless fallback — so the system runs end-to-end without
an OpenAI account. And finally, we picked a hand-curated 30-bug
load test over LLM-generated bugs, because we need deterministic
re-runs to actually grade the pipeline.

The strongest single bet on this slide is the second wedge —
structured outputs. The contract between the model and our code is
now server-side enforced. That one decision changed everything
downstream — no defensive parsing, no JSON-schema drift, no
hallucinated field names. Just typed objects in, typed objects
out."

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

**Opening — say this as one connected story, not a list.**

"Let me tell you about a failure mode we hit early in development —
because the solution is the entire reason this slide exists.

We asked an LLM 'is this code vulnerable to SQL injection?' The
model said yes, with high confidence, and cited a CWE number to
back it up. The problem was, when we actually looked up that CWE
number, it didn't exist. The model had fabricated it.

That's the security agent's biggest enemy — a finding that is
plausible, well-formatted, and completely wrong. A reviewer reading
it would have no easy way to know.

So we grounded it. We took the actual CWE database — the public
MITRE catalog — and the OWASP Top-10 entries, and we embedded them
into ChromaDB using a small sentence-transformers model called
all-MiniLM-L6-v2.

Now, before the security agent generates a finding, it does
something different. It first embeds the code chunk it's looking
at, retrieves the top matching CWE descriptions from the database
— the real text, verbatim — and injects that text directly into
the prompt. The model is no longer recalling vulnerability
categories from training data. It's reading the actual source
material.

This is gated by a single environment variable, USE_RAG=1, so we
can A/B-test the difference live. And the result is exactly what
we hoped for. Every Critical-severity security finding now cites a
real CWE number, with descriptions that match the catalog. No more
hallucinated category numbers."

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

**Opening — say this as one connected story, not a list.**

"What you're looking at on this slide is not a mockup. This is the
actual comment the agent posted on a real pull request, on a real
GitHub repository. I want to walk you through the structure,
because every section of this comment is intentional.

At the top, you see the file name and the total finding count.
Right below it, there's a severity table grouped by file —
Critical, High, Medium, Low. A reviewer can scan that table in
under five seconds and decide whether the rest of the comment is
worth their attention.

Underneath the table, you see the findings themselves. Each one has
a severity, a category, an exact line number, a CWE identifier
when it's a security issue, and a one-line suggested fix. The
format is identical from finding to finding because every finding
is a typed Pydantic object underneath, and the comment renderer is
just a template over typed data. No string concatenation. No
free-form prose.

Look at the CWE-89 chip on the first finding. That label isn't a
guess by the model — it's grounded in the CWE database via the RAG
layer we just covered on slide 7. And the recommendation is not
'consider improving this.' It's actionable — parameterize the
query, use prepared statements. A reviewer can act on it without
having to interpret what the agent meant.

There's more behind the scenes too. We save a Markdown report and
a zip of the fixed code locally. And critically — we open a
follow-up pull request containing the patch. So the human reviewer
doesn't just see a comment. They see a clean starting point they
can merge or reject."

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

**Opening — say this as one connected story, not a list.**

"There's a principle we kept coming back to during this project —
you can't trust what you can't measure. So we instrumented
everything.

Every pull request review emits four kinds of structured events to
a single JSONL file. There's one pr_review event per pull request —
with counts, severities, and total duration. There's one agent
event per LangGraph node — with per-node timing, findings added,
and any errors. There's one llm_call event per API call — with
backend, model name, tokens, retries, and cost. And there's one
poll_cycle event per watcher tick — what was open, what was new,
what failed.

Every event is itself a Pydantic model, and the schema is enforced
the moment we write the line. So if our schema ever drifts, we
catch it immediately when the dashboard tries to re-validate.

The Streamlit dashboard you see on the right tails that JSONL file
and auto-refreshes every ten seconds. Everything on this screen —
the KPI cards, the agent-flow Sankey diagram, the LLM cost
histogram — is computed from real load-test data. None of it is
mocked, none of it is hard-coded.

That's how we know the system works. Not because we wrote a
confident README. Because we have the receipts."

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

**Opening — say this as one connected story, not a list.**

"Enough slides. Let's see it actually run.

What you're watching on the screen right now is an unedited
recording from yesterday. No retakes, no cuts, no clever editing.
A real pull request, on a real GitHub repository, reviewed by the
real system.

I'm opening a buggy pull request on python-simple-webapp — that's
our demo target, a small Flask app we maintain specifically so we
can throw bad code at it.

Watch the terminal in the middle of the screen. That's the watcher
detecting the new pull request within about twenty seconds of it
being opened. Once it detects it, the pipeline kicks off, and you
can see each node logging as it runs — orchestrator, security,
bug, style, triage, patch, tests.

On the left side of the screen, the agent's review comment appears
on the pull request. Notice the CWE numbers cited, the severity
grouping, the actionable recommendations. On the bottom right, a
second pull request gets opened automatically — that's the agent
committing its suggested fix to a sibling branch.

GitHub Actions then kicks in and runs our health-check workflow on
the patched code, verifying the fix doesn't break anything. And in
the dashboard on the right, you can see the PR count, the findings
count, and the cost number all tick up in real time.

Total elapsed time, from opening the buggy PR to the follow-up PR
being ready to merge — about ninety seconds."

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

**Opening — say this as one connected story, not a list.**

"Anyone can build a demo that works once. The harder question is —
does it still work the thirtieth time in a row? So we built a load
test to answer that question for ourselves.

The setup is straightforward. We wrote a driver that opens thirty
deliberately-buggy pull requests, sequentially, against a real
Airflow fork on GitHub. Ten of those PRs plant security issues,
ten plant bugs, five plant performance problems, and five plant
style issues. Every template is hand-curated, which means we know
in advance exactly what kind of finding each one should produce.

We hit go. We walked away. We came back about fifty minutes later.

The results are on the screen. Thirty out of thirty pull requests
were reviewed. Zero failures. Zero crashes. The median review took
59.5 seconds — well under our one-minute target. The slowest
single PR took 92 seconds.

The pipeline produced 627 total findings across the run — an
average of 21 issues spotted per pull request. Twenty-four of the
thirty PRs correctly triggered the human-review branch, because
they contained Critical or High severity security findings. And
the total OpenAI cost for the entire load test was four dollars
and fifty-six cents.

That's the receipt. Not a projection, not a marketing figure — the
actual number from runs/events.jsonl, which is in the repo and
queryable right now."

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

**Opening — say this as one connected story, not a list.**

"Anyone can claim their system catches bugs. We wanted a measured
answer to that question, not a confident one.

Here's how the evaluation works. Each of our thirty load-test
templates plants a specific kind of bug, in a specific category,
and we know in advance which category it should fall into. SQL
injection should be flagged as Security. A mutable default
argument should be flagged as Bug. A quadratic string concatenation
should be flagged as Performance.

We ask one simple question of every run — did the pipeline produce
at least one finding in the expected category?

Across all thirty templates, the answer was yes. Every single one.
That's 100 percent recall — ten of ten Security caught, ten of ten
Bug caught, five of five Performance, and six of six Style. The
numbers on the slide come straight from our eval scorer.

Now, I want to be honest about what this measures and what it
doesn't. We deliberately don't measure precision in this benchmark.
The reason is that each pull request also touches real Airflow
code, which has its own legitimate findings — and we don't have
ground truth on those. So we can't compute false-positive rates
without a labeled corpus, which is a separate study.

Hand spot-checks on eight templates confirm that seven out of
eight cited the exact correct CWE. That's a sample, not a full
measurement.

So when you see the '100 percent recall' claim on this slide, what
it actually means is — on a benchmark we designed, the pipeline
catches every textbook bug pattern. It's a floor, not a ceiling.
Real-world precision is the next study."

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

**Opening — say this as one connected story, not a list.**

"It's one thing to claim the system works. It's another to show
you what it actually caught. So this slide is five real bugs,
caught on a real Airflow fork, with verbatim agent comments in the
repo if you want to read them.

Let me walk through them.

The first one is SQL injection. The agent flagged a
string-concatenated query in a Python file, cited CWE-89, and
recommended switching to parameterized binding. The second is a
hardcoded API key. The agent recognized the 'sk_live_' prefix as a
real-looking Stripe key, cited CWE-798, and recommended moving the
secret to environment variables. Not a placeholder — it could pass
a casual code review.

The third is a mutable default argument — that classic
Python-specific footgun where a function defaults a parameter to
an empty list, and the same list gets shared across every call.
The agent caught it and explained why it's a bug, not just an
anti-pattern.

The fourth is a quadratic string concatenation in a loop. This is
the case we covered in detail earlier — a function that works
correctly but does five hundred times more work than necessary,
because of how Python handles string immutability. The agent
flagged it as a performance issue and suggested the one-line fix.

The fifth one is the most interesting. It's a function with
pathological cyclomatic complexity. Radon — our static analyzer —
flagged the structural metric, with a complexity score of 14, way
over the threshold. And on the same function, GPT-4o independently
flagged a semantic gap in the region-check logic. Two different
agents looking at the same code through different lenses, both
flagging it as worth attention.

Every card on this slide links to a full write-up in the
case_studies folder of the repo. None of these are curated demos.
They're what the agent actually produced."

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

**Opening — say this as one connected story, not a list.**

"If this were a real product instead of a capstone project, here's
what we'd ship next. Three goals — all measurable, no vague
aspirations. Each one has a number we measured today and a target
we'd chase.

The first goal is speed. Today, our 95th-percentile latency is 93
seconds. The target is to get that under 30. The path is twofold —
parallelize across pull requests, so multiple PRs can be reviewed
at the same time, and route the lighter agents like style and
performance through GPT-4o-mini instead of full GPT-4o.

The second goal is languages. Right now the pipeline reads Python
only. But tree-sitter — the parser we use — already supports Java,
JavaScript, Go, and Rust out of the box. What's needed is
language-specific prompt tuning, not a full rewrite. We could add
Java support, for instance, in a couple of weeks.

The third goal is cost. Today, each pull request costs about
fourteen cents to review. The target is to get that under a
nickel. The same idea applies — use a cheaper model for low-severity
findings, and reserve GPT-4o for security and Critical or High
severity bugs where quality matters most.

None of these are research problems. They're engineering work we'd
ship in a real product release.

One thing you'll notice is not on this list — precision. And
that's deliberate. We haven't measured precision yet, and we're
not going to claim a target for a number we don't have. The right
next step there is a labeled real-world PR corpus, which is a
separate study entirely."

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

**Opening — say this as one connected story, not a list.**

"That's the whole system, end to end. Let me close with a quick
recap before we open the floor.

Six engineers, one open-source repository, five AI agents, and one
typed contract holding them together. Thirty pull requests reviewed
in our load test. Zero failures. Four dollars and fifty-six cents in
total OpenAI spend. A real follow-up pull request for every fix
suggested. A real dashboard with real telemetry. Real receipts for
every number we showed you tonight.

The repository link is on this slide. The deck you just watched is
in that repository, served via GitHub Pages. Every number we
quoted comes from either runs/events.jsonl or load_test/status.json
— both of which are in the repo, and both of which you can verify.
No hand-waving.

If you want to see exactly what the agent produced on a specific
case, the case studies linked from slide 13 each have a verbatim
agent comment alongside the buggy code and the suggested fix.

We're happy to take questions on any agent, any of the design
decisions, the load test, the dashboard — anything we covered. And
if a question goes deeper than this deck, we'll tell you the honest
limit. What we measured, what we didn't, and what would change our
answer.

The floor is yours."

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
