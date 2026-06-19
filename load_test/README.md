# Load test — 30 buggy PRs against the airflow fork

Drive the multi-agent code review pipeline at scale by opening 30 deliberately-bad
PRs against `rahulilla/airflow` (the user's fork — never `apache/airflow`)
sequentially, and let the watcher review each one live so the dashboard fills with
real telemetry.

## Files

- `buggy_templates.py` — 30 hand-curated `BuggyTemplate` entries (10 Security,
  10 Bug, 5 Performance, 5 Style). Deterministic; identical input each run.
- `orchestrator.py` — the driver. Opens PRs sequentially, tails
  `runs/events.jsonl` per PR, writes `load_test/status.json`.
- `status.json` — generated. One row per attempted PR.

## How to run

In **Terminal A**, start the watcher with the agent-proposer step disabled
(the airflow fork has no Actions workflows — without this flag, every review
would block for ~5 min waiting for CI):

```bash
cd path/to/MultiAgentCodeReview
SKIP_AGENT_PROPOSAL=1 .venv/bin/python watch_prs.py rahulilla/airflow --interval 20
```

In **Terminal B**, run the orchestrator:

```bash
cd path/to/MultiAgentCodeReview
# Plan only — no GitHub calls:
.venv/bin/python -m load_test.orchestrator --dry-run

# Single-PR pre-flight before the full run:
.venv/bin/python -m load_test.orchestrator --count 1

# Full 30-PR run (~38 minutes):
.venv/bin/python -m load_test.orchestrator

# Resume after a partial run (e.g. start at template 11):
.venv/bin/python -m load_test.orchestrator --start-index 11 --count 20
```

In **Terminal C**, watch the dashboard:

```bash
.venv/bin/streamlit run dashboard/app.py
```

## What `status.json` looks like

Each `runs[]` entry records the attempt:

```json
{
  "idx": 3,
  "name": "eval-on-input",
  "target_file": "airflow-core/src/airflow/utils/helpers.py",
  "expected_findings": ["Security"],
  "opened_at": "2026-06-17T...",
  "pr_number": 17,
  "pr_url": "https://github.com/rahulilla/airflow/pull/17",
  "head_sha": "...",
  "branch": "loadtest/03-eval-on-input",
  "status": "ok",
  "reviewed_at": "2026-06-17T...",
  "duration_sec": 41.2,
  "total_findings": 6,
  "findings_by_severity": {"Critical": 1, "High": 1, "Medium": 3, "Low": 1},
  "findings_by_category": {"Security": 4, "Bug": 1, "Style": 1, "Performance": 0},
  "needs_human_review": true
}
```

`status` is one of `ok` · `review-timeout` · `open-failed` · `orchestrator-error` · `dry-run`.

## Cleaning up afterward

The 30 `loadtest/*` branches and PRs stay open on the fork. To close them
(requires `gh` CLI authenticated against `rahulilla/airflow`):

```bash
gh pr list --repo rahulilla/airflow -L 100 --search "head:loadtest/" --json number \
  --jq '.[].number' | xargs -I{} gh pr close {} --repo rahulilla/airflow --delete-branch
```

Or via the Python client (no extra deps):

```bash
.venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv('.env')
from integrations.github_pr import GitHubPRClient
c = GitHubPRClient()
for pr in c.list_open_prs('rahulilla', 'airflow'):
    if pr['head']['ref'].startswith('loadtest/'):
        print('closing', pr['number'], pr['head']['ref'])
        c.close_pr('rahulilla', 'airflow', pr['number'])
"
```

## Safety notes

- `OWNER = 'rahulilla'` is hardcoded in `orchestrator.py`. The script also
  refuses to run if a member of `_DISALLOWED` (`apache`, `Apache`) ever lands
  in OWNER. There is no CLI flag to retarget — modify the source to change
  this, deliberately.
- The bug code is appended to real airflow utility files. Because the load
  test only *reviews* the diffs (it does not run airflow), the bugs never
  execute.
- Each PR is on its own branch off `main`; PRs do not chain or build on each
  other.
