"""
Review a GitHub pull request with the multi-agent pipeline (manual CLI).

Fetches the PR's changed Python files, runs the full review pipeline on each,
writes a combined report + fixed code + ZIP locally, and optionally posts a
summary comment back to the PR.

Usage:
    python review_pr.py https://github.com/rahulilla/airflow/pull/1
    python review_pr.py <pr_url> --comment            # also post a PR comment
    python review_pr.py <pr_url> --max-files 5

Auth:
    Reading public PRs works without a token (rate-limited). Posting a comment
    requires GITHUB_TOKEN (env) with write access to the repo.
"""

from __future__ import annotations

import argparse
import sys

from integrations.github_pr import GitHubPRClient, parse_pr_url
from pr_review_core import handle_pr


def main() -> None:
    parser = argparse.ArgumentParser(description="Review a GitHub PR.")
    parser.add_argument("pr_url", help="GitHub PR URL")
    parser.add_argument(
        "--comment",
        action="store_true",
        help="Post a summary comment to the PR (asks for confirmation first).",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=10,
        help="Maximum number of Python files to review (default 10).",
    )
    args = parser.parse_args()

    try:
        owner, repo, number = parse_pr_url(args.pr_url)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    client = GitHubPRClient()
    print(
        f"\n{'=' * 60}\n  MULTI-AGENT PR REVIEW\n"
        f"  {owner}/{repo} #{number}\n"
        f"  auth: {'token' if client.authenticated else 'anonymous (rate-limited)'}\n"
        f"{'=' * 60}\n"
    )

    if args.comment and not client.authenticated:
        print("Error: --comment requires GITHUB_TOKEN with write access.")
        sys.exit(1)

    try:
        result = handle_pr(
            client,
            owner,
            repo,
            number,
            post_comment=args.comment,
            require_confirm=True,
            max_files=args.max_files,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Error reviewing PR: {exc}")
        sys.exit(1)

    print("\nArtifacts written:")
    for label, path in result.artifacts.items():
        print(f"  {label:24} -> {path}")
    if result.comment_url:
        print(f"\nComment: {result.comment_url}")


if __name__ == "__main__":
    main()
