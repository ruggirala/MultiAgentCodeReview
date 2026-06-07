"""
Live PR watcher — the local auto-trigger for the demo.

Polls a GitHub repo for open pull requests on an interval. When it sees a PR it
hasn't reviewed yet (keyed by PR number + head commit SHA), it runs the
multi-agent pipeline and posts the analysis as a PR comment — automatically.

Everything runs locally; no webhook, tunnel, or inbound networking required.

Usage:
    export GITHUB_TOKEN=<PAT with PR read/write on the repo>
    python watch_prs.py rahulilla/airflow
    python watch_prs.py rahulilla/airflow --interval 15
    python watch_prs.py rahulilla/airflow --review-existing   # also do open PRs
    python watch_prs.py rahulilla/airflow --no-comment        # review, don't post

Demo flow:
    1. Start the watcher (it pre-seeds currently-open PRs so it only reacts to
       NEW ones).
    2. Open a PR on the fork with a buggy .py change.
    3. Within ~one interval, the watcher detects it, reviews it, and comments.

Dedup state persists to a JSON file so restarts don't double-comment. New commits
pushed to a PR (new head SHA) trigger exactly one re-review.

Stop with Ctrl-C (state is saved).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from integrations.github_pr import GitHubError, GitHubPRClient
from pr_review_core import handle_pr

# Backoff applied after an errored poll cycle, capped.
_ERROR_BACKOFF_START = 5
_ERROR_BACKOFF_MAX = 120


def _pr_key(number: int, head_sha: str) -> str:
    return f"{number}:{head_sha}"


def _load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        print(f"[watch] could not parse {path}; starting with empty state.")
        return set()


def _save_state(path: Path, seen: set[str]) -> None:
    try:
        path.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"[watch] warning: could not save state: {exc}")


def _parse_repo(arg: str) -> tuple[str, str]:
    """Accept 'owner/repo' or a full repo URL."""
    cleaned = arg.strip().rstrip("/")
    if cleaned.startswith("http"):
        parts = cleaned.split("github.com/", 1)[-1].split("/")
    else:
        parts = cleaned.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Expected 'owner/repo', got {arg!r}")
    return parts[0], parts[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch a repo and auto-review new PRs.")
    parser.add_argument("repo", help="Repo as 'owner/repo' (e.g. rahulilla/airflow)")
    parser.add_argument("--interval", type=int, default=20, help="Poll seconds (default 20).")
    parser.add_argument(
        "--state-file",
        default=".pr_watch_state.json",
        help="Where to persist seen PR/commit keys.",
    )
    parser.add_argument(
        "--no-comment",
        action="store_true",
        help="Review and write artifacts but do NOT post a PR comment.",
    )
    parser.add_argument(
        "--review-existing",
        action="store_true",
        help="Also review PRs already open when the watcher starts.",
    )
    parser.add_argument(
        "--max-files", type=int, default=10, help="Max Python files per PR."
    )
    args = parser.parse_args()

    try:
        owner, repo = _parse_repo(args.repo)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    client = GitHubPRClient()
    post_comment = not args.no_comment

    if post_comment and not client.authenticated:
        print(
            "Error: posting comments needs GITHUB_TOKEN with write access.\n"
            "Set it, or run with --no-comment to review without posting."
        )
        sys.exit(1)

    state_path = Path(args.state_file)
    seen = _load_state(state_path)

    print(
        f"\n{'=' * 60}\n  PR WATCHER\n"
        f"  repo:     {owner}/{repo}\n"
        f"  interval: {args.interval}s\n"
        f"  comment:  {'yes' if post_comment else 'no (review only)'}\n"
        f"  state:    {state_path} ({len(seen)} key(s) loaded)\n"
        f"{'=' * 60}\n"
    )

    # Pre-seed currently-open PRs so we only react to PRs opened AFTER start,
    # unless the user explicitly wants existing ones reviewed.
    if not args.review_existing:
        try:
            for pr in client.list_open_prs(owner, repo):
                seen.add(_pr_key(pr["number"], pr["head"]["sha"]))
            _save_state(state_path, seen)
            print(f"[watch] pre-seeded {len(seen)} open PR(s); waiting for new ones.\n")
        except GitHubError as exc:
            print(f"[watch] could not pre-seed (will retry in loop): {exc}\n")

    backoff = _ERROR_BACKOFF_START
    poll = 0
    try:
        while True:
            poll += 1
            try:
                open_prs = client.list_open_prs(owner, repo)
                backoff = _ERROR_BACKOFF_START  # reset after a good cycle
                new_prs = [
                    pr
                    for pr in open_prs
                    if _pr_key(pr["number"], pr["head"]["sha"]) not in seen
                ]
                print(
                    f"[watch] poll #{poll}: {len(open_prs)} open, "
                    f"{len(new_prs)} new."
                )

                for pr in new_prs:
                    number = pr["number"]
                    key = _pr_key(number, pr["head"]["sha"])
                    print(f"\n[watch] >>> new PR #{number} detected — reviewing.")
                    try:
                        handle_pr(
                            client,
                            owner,
                            repo,
                            number,
                            post_comment=post_comment,
                            require_confirm=False,  # watcher is non-interactive
                            max_files=args.max_files,
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"[watch] review of #{number} failed: {exc}")
                    # Mark seen regardless, so a persistently-failing PR doesn't
                    # loop forever; a new commit (new SHA) will retry.
                    seen.add(key)
                    _save_state(state_path, seen)

                time.sleep(args.interval)

            except GitHubError as exc:
                print(f"[watch] poll error: {exc}; backing off {backoff}s.")
                time.sleep(backoff)
                backoff = min(backoff * 2, _ERROR_BACKOFF_MAX)

    except KeyboardInterrupt:
        _save_state(state_path, seen)
        print("\n[watch] stopped (state saved). Bye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
