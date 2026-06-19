"""
Push the multi-agent system's suggested fixes to a sibling branch and open a
follow-up PR — but only after CI on the agent branch passes.

Sits on top of `pr_review_core.handle_pr`. After the review pipeline produces
fixed code per file, this module:

  1. branches off the user's PR head SHA (named `<user-branch>-agent-suggested`),
  2. commits the agent's fixed files,
  3. closes any prior open follow-up PR for the same branch (avoids duplicates),
  4. dispatches the demo repo's CI workflow on that branch via `workflow_dispatch`,
  5. polls the resulting workflow run for up to 5 minutes,
  6. on green → opens a follow-up PR (base = user's branch, head = agent branch)
     and posts a small comment on the original PR linking it,
  7. on red/timeout → does NOT open the PR; comments on the original PR with a
     link to the failed run so the human stays in the loop.

The whole thing is wrapped defensively at the call site so any failure in here
just degrades to "review comment posted but no follow-up PR" instead of breaking
the watcher.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from integrations.github_pr import GitHubError, GitHubPRClient

if TYPE_CHECKING:
    from pr_review_core import PRReviewResult

DEFAULT_WORKFLOW_FILE = "health-check.yml"
DEFAULT_POLL_INTERVAL_S = 10
DEFAULT_POLL_TIMEOUT_S = 300  # matches `timeout-minutes: 5` in the workflow
RUN_DISCOVERY_TIMEOUT_S = 60  # how long to wait for the dispatched run to appear
RUN_DISCOVERY_INTERVAL_S = 5


@dataclass
class AgentProposalOutcome:
    """What `propose_agent_fixes` did (or chose not to do)."""

    status: str  # "opened" | "ci_failed" | "no_changes" | "skipped" | "error"
    agent_branch: Optional[str] = None
    agent_commit_sha: Optional[str] = None
    workflow_run_id: Optional[int] = None
    workflow_run_url: Optional[str] = None
    workflow_conclusion: Optional[str] = None
    proposed_pr_url: Optional[str] = None
    detail: str = ""
    closed_pr_numbers: list[int] = field(default_factory=list)


def propose_agent_fixes(
    client: GitHubPRClient,
    result: "PRReviewResult",
    *,
    workflow_file: str = DEFAULT_WORKFLOW_FILE,
    poll_interval_s: int = DEFAULT_POLL_INTERVAL_S,
    poll_timeout_s: int = DEFAULT_POLL_TIMEOUT_S,
) -> AgentProposalOutcome:
    """Run the full propose-fixes-then-open-PR-if-CI-green flow."""
    # --- 1. fast-skip guards -----------------------------------------------
    if not result.reviews:
        return AgentProposalOutcome(status="no_changes", detail="no reviews ran")

    proposed_files: dict[str, str] = {}
    for review in result.reviews:
        patch = review.state.patch
        if not patch or not patch.fixed_code:
            continue
        # Skip files where the "fix" is byte-identical to the input — agents
        # sometimes return the original code when nothing actionable was found.
        if patch.fixed_code.strip() == review.state.source_code.strip():
            continue
        proposed_files[review.filename] = patch.fixed_code

    if not proposed_files:
        return AgentProposalOutcome(
            status="no_changes",
            detail="no agent patches differed from the original code",
        )

    if not client.authenticated:
        return AgentProposalOutcome(
            status="skipped",
            detail="GitHubPRClient is not authenticated — cannot push fixes",
        )

    # --- DEMO HOOK: force a CI failure on the agent branch -----------------
    # When `AGENT_FIX_INJECT_BAD=1` is set in the environment, replace the
    # agent's `app.py` fix with a known-broken version (bad import) so the
    # demo app fails to boot in CI. Used to demonstrate that the CI gate
    # below correctly REFUSES to open a follow-up PR when the agent's
    # suggestions break the app.
    #
    # Off by default. Never set this in production / normal demos.
    import os as _os
    if _os.environ.get("AGENT_FIX_INJECT_BAD") == "1":
        for path in list(proposed_files):
            if path.endswith("app.py"):
                proposed_files[path] = (
                    '"""DEMO: deliberately broken agent fix to exercise the CI gate."""\n'
                    "from flask import Flask, _this_does_not_exist  # boot will fail\n\n"
                    "app = Flask(__name__)\n"
                )
                print(
                    f"[propose] AGENT_FIX_INJECT_BAD=1 — replaced {path} with a "
                    "known-broken version to exercise the CI-fails path."
                )

    owner, repo, number = result.owner, result.repo, result.number

    # --- 2. resolve user PR head ref + sha ---------------------------------
    pr = client.get_pr(owner, repo, number)
    user_branch = pr["head"]["ref"]
    user_head_sha = pr["head"]["sha"]
    agent_branch = f"{user_branch}-agent-suggested"
    print(
        f"[propose] PR #{number}: agent branch '{agent_branch}' "
        f"based on user head {user_head_sha[:10]}"
    )

    outcome = AgentProposalOutcome(status="error", agent_branch=agent_branch)

    # --- 3. close any prior open follow-up PR for this agent branch -------
    # Done BEFORE we force-push so we don't briefly have an open PR pointing
    # at a stale tree.
    try:
        prior = client.list_open_prs_for_head(owner, repo, agent_branch)
        for prev_pr in prior:
            client.close_pr(owner, repo, prev_pr["number"])
            outcome.closed_pr_numbers.append(prev_pr["number"])
            print(f"[propose] closed prior follow-up PR #{prev_pr['number']}")
    except GitHubError as exc:
        print(f"[propose] WARN: could not list/close prior PRs: {exc}")

    # --- 4. reset the agent branch to the user's head sha -----------------
    client.create_or_update_ref(owner, repo, agent_branch, user_head_sha, force=True)

    # --- 5. commit the fixes ----------------------------------------------
    commit_message = (
        f"agent: suggested fixes for #{number}\n\n"
        f"Auto-generated patch from the multi-agent code review pipeline.\n"
        f"Addresses {sum(len(r.state.findings) for r in result.reviews)} "
        f"finding(s) across {len(proposed_files)} file(s)."
    )
    new_sha = client.commit_files(
        owner, repo, agent_branch, proposed_files, commit_message, user_head_sha
    )
    outcome.agent_commit_sha = new_sha
    print(f"[propose] committed fixes -> {new_sha[:10]} on {agent_branch}")

    # --- 6. dispatch CI on the agent branch -------------------------------
    # SKIP_CI_GATE=1 bypasses the entire dispatch+poll path. Use this on repos
    # without a `workflow_dispatch`-able CI workflow (e.g. the airflow fork);
    # the follow-up PR is opened straight from the committed fixes.
    if os.environ.get("SKIP_CI_GATE") == "1":
        print("[propose] SKIP_CI_GATE=1 — skipping CI dispatch/poll, opening "
              "follow-up PR directly.")
        pr_body = _build_followup_pr_body(result, outcome, user_branch)
        new_pr = client.open_pr(
            owner, repo,
            title=f"Suggested fixes for #{number}: {result.title}",
            head=agent_branch,
            base=user_branch,
            body=pr_body,
            draft=False,
        )
        outcome.proposed_pr_url = new_pr["html_url"]
        outcome.status = "opened"
        outcome.workflow_conclusion = "skipped"
        print(f"[propose] follow-up PR opened: {outcome.proposed_pr_url}")
        _post_success_comment(client, result, outcome)
        return outcome

    try:
        client.dispatch_workflow(owner, repo, workflow_file, ref=agent_branch)
    except GitHubError as exc:
        # Most common cause: workflow file missing / lacks `workflow_dispatch:`.
        msg = (
            f"could not dispatch workflow '{workflow_file}' on {agent_branch}: "
            f"{exc}"
        )
        print(f"[propose] {msg}")
        _post_failure_comment(client, result, agent_branch, run_url=None, reason=msg)
        outcome.status = "ci_failed"
        outcome.detail = msg
        return outcome

    # Capture dispatch time so we don't pick up an older run on the same branch.
    dispatched_at = time.time()
    print(f"[propose] dispatched '{workflow_file}' on {agent_branch}; finding the run…")

    # --- 7. discover the run that the dispatch produced -------------------
    run = _wait_for_run(client, owner, repo, workflow_file, agent_branch,
                        dispatched_after=dispatched_at)
    if run is None:
        msg = (
            f"dispatched workflow but no run appeared on {agent_branch} within "
            f"{RUN_DISCOVERY_TIMEOUT_S}s"
        )
        print(f"[propose] {msg}")
        _post_failure_comment(client, result, agent_branch, run_url=None, reason=msg)
        outcome.status = "ci_failed"
        outcome.detail = msg
        return outcome

    outcome.workflow_run_id = run["id"]
    outcome.workflow_run_url = run["html_url"]

    # --- 8. poll until completion or timeout ------------------------------
    print(f"[propose] watching run #{run['run_number']} -> {run['html_url']}")
    final = _poll_run(client, owner, repo, run["id"],
                      interval_s=poll_interval_s, timeout_s=poll_timeout_s)
    if final is None:
        msg = f"workflow run did not complete within {poll_timeout_s}s"
        print(f"[propose] {msg}")
        _post_failure_comment(client, result, agent_branch,
                              run_url=outcome.workflow_run_url, reason=msg)
        outcome.status = "ci_failed"
        outcome.detail = msg
        outcome.workflow_conclusion = "timeout"
        return outcome

    outcome.workflow_conclusion = final.get("conclusion") or "unknown"
    print(f"[propose] run completed: conclusion={outcome.workflow_conclusion}")

    # --- 9. branch on outcome ---------------------------------------------
    if outcome.workflow_conclusion != "success":
        msg = f"CI conclusion was '{outcome.workflow_conclusion}'"
        _post_failure_comment(client, result, agent_branch,
                              run_url=outcome.workflow_run_url, reason=msg)
        outcome.status = "ci_failed"
        outcome.detail = msg
        return outcome

    # CI green → open the follow-up PR.
    pr_body = _build_followup_pr_body(result, outcome, user_branch)
    new_pr = client.open_pr(
        owner, repo,
        title=f"Suggested fixes for #{number}: {result.title}",
        head=agent_branch,
        base=user_branch,
        body=pr_body,
        draft=False,
    )
    outcome.proposed_pr_url = new_pr["html_url"]
    outcome.status = "opened"
    print(f"[propose] follow-up PR opened: {outcome.proposed_pr_url}")

    # Small note on the original PR linking the follow-up.
    _post_success_comment(client, result, outcome)
    return outcome


# --- helpers --------------------------------------------------------------


def _wait_for_run(
    client: GitHubPRClient,
    owner: str,
    repo: str,
    workflow_file: str,
    branch: str,
    dispatched_after: float,
) -> Optional[dict]:
    """Poll until a run for this workflow on this branch appears (or give up)."""
    deadline = time.time() + RUN_DISCOVERY_TIMEOUT_S
    while time.time() < deadline:
        runs = client.list_workflow_runs(owner, repo, workflow_file, branch=branch)
        # Pick the newest run that started AFTER our dispatch. GitHub returns
        # `created_at` as ISO-8601 UTC; compare via a stable epoch parse.
        for r in runs:
            created_epoch = _iso_to_epoch(r.get("created_at", ""))
            # Allow ~5s clock skew between the dispatch call and the run record.
            if created_epoch >= dispatched_after - 5:
                return r
        time.sleep(RUN_DISCOVERY_INTERVAL_S)
    return None


def _poll_run(
    client: GitHubPRClient,
    owner: str,
    repo: str,
    run_id: int,
    *,
    interval_s: int,
    timeout_s: int,
) -> Optional[dict]:
    """Return the completed run dict, or None on timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        run = client.get_workflow_run(owner, repo, run_id)
        status = run.get("status")
        if status == "completed":
            return run
        print(f"[propose]   …status={status}, sleeping {interval_s}s")
        time.sleep(interval_s)
    return None


def _iso_to_epoch(iso: str) -> float:
    """Parse a GitHub-style ISO-8601 timestamp to epoch seconds. Returns 0 on fail."""
    if not iso:
        return 0.0
    # GitHub uses 'Z' suffix; Python's fromisoformat tolerates '+00:00'.
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _build_followup_pr_body(
    result: "PRReviewResult",
    outcome: AgentProposalOutcome,
    user_branch: str,
) -> str:
    total_findings = sum(len(r.state.findings) for r in result.reviews)
    files_list = "\n".join(f"- `{r.filename}`" for r in result.reviews if r.state.patch)
    return (
        f"## 🤖 Multi-Agent Code Review — suggested fixes\n\n"
        f"This PR proposes fixes for #{result.number} based on **{total_findings}** "
        f"finding(s) the multi-agent reviewer surfaced.\n\n"
        f"**Files changed by the agent:**\n{files_list}\n\n"
        f"**CI status (verified before opening this PR):** "
        f"✅ green — [{outcome.workflow_conclusion}]({outcome.workflow_run_url})\n\n"
        f"This PR targets `{user_branch}` (the original PR's branch). Merging it "
        f"applies the agent's suggestions to that branch; the original PR can "
        f"then be reviewed and merged as usual.\n\n"
        f"<sub>Automated proposal — review the diff before merging.</sub>"
    )


def _post_success_comment(
    client: GitHubPRClient,
    result: "PRReviewResult",
    outcome: AgentProposalOutcome,
) -> None:
    body = (
        f"🤖 **Suggested fixes proposed in {outcome.proposed_pr_url}** "
        f"(CI passed: [{outcome.workflow_conclusion}]({outcome.workflow_run_url})).\n\n"
        f"Branch `{outcome.agent_branch}` was created with the agent's patches "
        f"and verified by the demo app's health-check workflow before opening "
        f"the follow-up PR."
    )
    try:
        client.post_pr_comment(result.owner, result.repo, result.number, body)
    except GitHubError as exc:
        print(f"[propose] WARN: could not post success comment: {exc}")


def _post_failure_comment(
    client: GitHubPRClient,
    result: "PRReviewResult",
    agent_branch: str,
    run_url: Optional[str],
    reason: str,
) -> None:
    """Tell the human CI didn't pass, link the run, leave the branch in place."""
    run_link = f"[CI run]({run_url})" if run_url else "(no run url)"
    body = (
        f"🤖 **Agent fixes pushed to `{agent_branch}` but CI did not pass.**\n\n"
        f"Reason: {reason}\n\n"
        f"{run_link}\n\n"
        f"The follow-up PR was **not** opened. Inspect the branch and the run "
        f"to see what went wrong; the agent's review comment above still applies."
    )
    try:
        client.post_pr_comment(result.owner, result.repo, result.number, body)
    except GitHubError as exc:
        print(f"[propose] WARN: could not post failure comment: {exc}")
