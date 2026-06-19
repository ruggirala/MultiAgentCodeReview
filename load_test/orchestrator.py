"""
Sequential PR-creation driver for load-testing the multi-agent pipeline.

Opens N deliberately-bad PRs against `rahulilla/airflow` (the user's fork —
NEVER the public apache/airflow), one at a time with a configurable gap, and
tails `runs/events.jsonl` to confirm the watcher reviews each one before
moving on. Results land in `load_test/status.json`.

Usage:
    # Terminal A — start the watcher (with proposer disabled for the test):
    SKIP_AGENT_PROPOSAL=1 python watch_prs.py rahulilla/airflow --interval 20

    # Terminal B — run the orchestrator:
    python -m load_test.orchestrator                 # all 30 PRs
    python -m load_test.orchestrator --count 5
    python -m load_test.orchestrator --dry-run       # plan only, no GitHub calls
    python -m load_test.orchestrator --start-index 5 # resume from template index 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Resolve .env relative to the project so this works no matter the cwd.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from integrations.github_pr import GitHubError, GitHubPRClient  # noqa: E402
from load_test.buggy_templates import TEMPLATES, BuggyTemplate  # noqa: E402
from metrics.recorder import EVENTS_PATH  # noqa: E402

OWNER = "rahulilla"
REPO = "airflow"
BASE_BRANCH = "main"
STATUS_PATH = _PROJECT_ROOT / "load_test" / "status.json"

# Hard guard: this script must never target the public apache/airflow.
_DISALLOWED = {"apache", "Apache"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- status.json helpers ----------------------------------------------


def _load_status() -> dict[str, Any]:
    if STATUS_PATH.exists():
        try:
            return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"started_at": _now_iso(), "config": {}, "runs": []}


def _save_status(status: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")


# --- GitHub: open one PR ----------------------------------------------


def _branch_for(idx: int, template: BuggyTemplate) -> str:
    return f"loadtest/{idx:02d}-{template.name}"


def _pr_body(idx: int, template: BuggyTemplate) -> str:
    return (
        f"**Load test PR {idx}/30** — `{template.name}`\n\n"
        f"_Auto-generated for multi-agent pipeline load testing._\n\n"
        f"Adds a deliberately-buggy `{template.function_name}()` to "
        f"`{template.target_file}`.\n\n"
        f"Expected agent finding categories: "
        f"{', '.join(template.expected_findings)}.\n\n"
        f"Rationale: {template.rationale}\n"
    )


def _open_one_pr(
    client: GitHubPRClient, idx: int, template: BuggyTemplate
) -> dict[str, Any]:
    """Append the template's bug to its target file on a fresh branch + open PR."""
    branch = _branch_for(idx, template)

    # 1. Resolve main's head SHA fresh — don't assume it hasn't moved.
    main = client.get_branch(OWNER, REPO, BASE_BRANCH)
    if main is None:
        raise RuntimeError(f"Base branch {BASE_BRANCH} not found on {OWNER}/{REPO}.")
    parent_sha = main["commit"]["sha"]

    # 2. Read the target file at main, append the bug.
    original = client.get_file_content(OWNER, REPO, template.target_file, BASE_BRANCH)
    new_content = original.rstrip("\n") + "\n\n" + template.source.lstrip("\n")

    # 3. Create the branch (idempotent — if it exists, advance later).
    client.create_or_update_ref(OWNER, REPO, branch, parent_sha)

    # 4. Commit on the branch.
    head_sha = client.commit_files(
        OWNER,
        REPO,
        branch,
        files={template.target_file: new_content},
        message=f"loadtest: add buggy {template.function_name} ({template.name})",
        parent_sha=parent_sha,
    )

    # 5. Open the PR.
    pr = client.open_pr(
        OWNER,
        REPO,
        title=f"[loadtest {idx}/30] {template.name}",
        head=branch,
        base=BASE_BRANCH,
        body=_pr_body(idx, template),
    )
    return {
        "pr_number": pr["number"],
        "pr_url": pr.get("html_url"),
        "head_sha": head_sha,
        "branch": branch,
    }


# --- watcher event tailing --------------------------------------------


def _wait_for_review(
    pr_number: int, *, since_byte_offset: int, timeout_sec: int
) -> Optional[dict[str, Any]]:
    """Poll runs/events.jsonl for a `pr_review` event matching `pr_number`.

    Reads only bytes appended after `since_byte_offset` so we don't re-match
    events from prior runs. Returns the event dict, or None on timeout.
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not EVENTS_PATH.exists():
            time.sleep(2)
            continue
        try:
            with EVENTS_PATH.open("rb") as fh:
                fh.seek(since_byte_offset)
                tail = fh.read().decode("utf-8", errors="replace")
        except Exception:
            time.sleep(2)
            continue
        for line in tail.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                event.get("type") == "pr_review"
                and event.get("pr_number") == pr_number
                and event.get("owner") == OWNER
                and event.get("repo") == REPO
            ):
                return event
        time.sleep(2)
    return None


def _events_jsonl_size() -> int:
    try:
        return EVENTS_PATH.stat().st_size
    except FileNotFoundError:
        return 0


# --- per-PR run -------------------------------------------------------


def run_one(
    client: GitHubPRClient,
    idx: int,
    template: BuggyTemplate,
    *,
    pr_timeout: int,
    dry_run: bool,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "idx": idx,
        "name": template.name,
        "target_file": template.target_file,
        "expected_findings": template.expected_findings,
        "opened_at": _now_iso(),
    }

    if dry_run:
        record["status"] = "dry-run"
        record["branch"] = _branch_for(idx, template)
        return record

    try:
        offset = _events_jsonl_size()
        info = _open_one_pr(client, idx, template)
        record.update(info)
        print(
            f"[load] [{idx:>2}/30] opened PR #{info['pr_number']} "
            f"({template.name}) → {info['pr_url']}"
        )
    except Exception as exc:
        record["status"] = "open-failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[load] [{idx:>2}/30] FAILED to open PR: {exc}")
        return record

    print(
        f"[load] [{idx:>2}/30] waiting up to {pr_timeout}s for watcher to "
        f"review PR #{record['pr_number']}…"
    )
    event = _wait_for_review(
        record["pr_number"], since_byte_offset=offset, timeout_sec=pr_timeout
    )
    if event is None:
        record["status"] = "review-timeout"
        record["reviewed_at"] = None
        print(f"[load] [{idx:>2}/30] TIMEOUT — no pr_review event in {pr_timeout}s.")
        return record

    record["status"] = "ok"
    record["reviewed_at"] = event.get("timestamp_utc")
    record["duration_sec"] = event.get("duration_sec")
    record["total_findings"] = event.get("total_findings")
    record["findings_by_severity"] = event.get("findings_by_severity")
    record["findings_by_category"] = event.get("findings_by_category")
    record["needs_human_review"] = event.get("needs_human_review")
    print(
        f"[load] [{idx:>2}/30] reviewed in {event.get('duration_sec', 0):.1f}s — "
        f"{event.get('total_findings')} findings."
    )
    return record


# --- driver ------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        description="Open N buggy PRs sequentially; tail events.jsonl per PR."
    )
    p.add_argument("--count", type=int, default=30, help="How many PRs to open (max 30).")
    p.add_argument("--start-index", type=int, default=1, help="Template index to start at (1-based).")
    p.add_argument(
        "--gap-seconds",
        type=int,
        default=75,
        help="Time between successive PR-opens; review wait counts toward this.",
    )
    p.add_argument(
        "--pr-timeout",
        type=int,
        default=180,
        help="Max seconds to wait for a per-PR review event.",
    )
    p.add_argument("--dry-run", action="store_true", help="Plan only — no GitHub calls.")
    args = p.parse_args()

    if OWNER in _DISALLOWED:
        print("ERROR: target owner is on the disallowed list. Refusing to run.")
        return 2

    if args.count < 1 or args.count > 30:
        print("ERROR: --count must be between 1 and 30.")
        return 2
    if args.start_index < 1 or args.start_index > 30:
        print("ERROR: --start-index must be between 1 and 30.")
        return 2

    end = min(args.start_index + args.count - 1, len(TEMPLATES))
    selected = list(enumerate(TEMPLATES, start=1))[args.start_index - 1 : end]

    print("=" * 64)
    print("  LOAD TEST — multi-agent pipeline")
    print(f"  target:        github.com/{OWNER}/{REPO}")
    print(f"  base branch:   {BASE_BRANCH}")
    print(f"  PRs to open:   {len(selected)} (templates {args.start_index}..{end})")
    print(f"  gap:           {args.gap_seconds}s (PR-open to PR-open)")
    print(f"  per-PR cap:    {args.pr_timeout}s")
    print(f"  dry-run:       {args.dry_run}")
    print(f"  status file:   {STATUS_PATH}")
    print("=" * 64)

    client: Optional[GitHubPRClient] = None if args.dry_run else GitHubPRClient()
    if not args.dry_run and (client is None or not client.authenticated):
        print("ERROR: GitHubPRClient is not authenticated. Set GITHUB_TOKEN in .env.")
        return 2

    status = _load_status()
    status["config"] = {
        "count": args.count,
        "start_index": args.start_index,
        "gap_seconds": args.gap_seconds,
        "pr_timeout": args.pr_timeout,
        "dry_run": args.dry_run,
    }

    for i, (idx, template) in enumerate(selected, start=1):
        loop_start = time.time()
        try:
            rec = run_one(
                client, idx, template,
                pr_timeout=args.pr_timeout,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            rec = {
                "idx": idx,
                "name": template.name,
                "status": "orchestrator-error",
                "error": f"{type(exc).__name__}: {exc}",
                "opened_at": _now_iso(),
            }
            print(f"[load] [{idx:>2}/30] orchestrator caught: {exc}")

        status["runs"].append(rec)
        _save_status(status)

        if i == len(selected):
            break  # no gap after last

        elapsed = time.time() - loop_start
        sleep = max(0.0, args.gap_seconds - elapsed)
        if sleep > 0 and not args.dry_run:
            print(f"[load] sleeping {sleep:.0f}s before next PR…")
            time.sleep(sleep)

    print("\n" + "=" * 64)
    print("  LOAD TEST DONE")
    counts: dict[str, int] = {}
    for r in status["runs"][-len(selected):]:
        counts[r.get("status", "?")] = counts.get(r.get("status", "?"), 0) + 1
    for k, v in counts.items():
        print(f"  {k:20} {v}")
    print(f"  full results:   {STATUS_PATH}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
