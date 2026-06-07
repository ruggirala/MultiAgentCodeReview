"""
Shared "review one PR" logic used by both the manual CLI (`review_pr.py`) and
the polling watcher (`watch_prs.py`), so their behavior is identical.

Reuses the existing pipeline (`graph.pipeline.run_pipeline`) and report renderer
(`run_pipeline.build_report`) unchanged — this is a thin orchestration layer over
the multi-agent system, fetching a PR's changed Python files and looping the
pipeline over each.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from graph.pipeline import run_pipeline
from integrations.github_pr import (
    GitHubPRClient,
    MAX_FILE_BYTES,
    PRFile,
    python_files,
)
from models.schemas import ReviewState, Severity
from run_pipeline import build_report

# GitHub rejects comment bodies longer than this.
GITHUB_COMMENT_LIMIT = 65_536
_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


@dataclass
class FileReview:
    """The pipeline result for one reviewed file, plus its path."""

    filename: str
    state: ReviewState


@dataclass
class PRReviewResult:
    """Everything produced by reviewing a PR."""

    owner: str
    repo: str
    number: int
    title: str
    author: str
    head_sha: str
    reviews: list[FileReview] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    comment_url: Optional[str] = None

    @property
    def total_findings(self) -> int:
        return sum(len(r.state.findings) for r in self.reviews)


# --- report / comment rendering ----------------------------------------


def _slug(owner: str, repo: str, number: int) -> str:
    return f"pr_{owner}_{repo}_{number}"


def build_pr_report(result: PRReviewResult) -> str:
    """Full multi-file Markdown report for the whole PR (saved locally)."""
    lines: list[str] = []
    lines.append(f"# PR Review — {result.owner}/{result.repo} #{result.number}\n")
    lines.append(f"**{result.title}** — by @{result.author}\n")
    lines.append(f"Head commit: `{result.head_sha[:10]}`\n")
    lines.append(
        f"Reviewed **{len(result.reviews)}** Python file(s); "
        f"**{result.total_findings}** total finding(s).\n"
    )
    if result.skipped:
        lines.append("\n_Skipped:_ " + ", ".join(result.skipped) + "\n")

    for review in result.reviews:
        lines.append("\n---\n")
        lines.append(f"## `{review.filename}`\n")
        lines.append(build_report(review.state))

    return "\n".join(lines) + "\n"


def format_pr_comment(result: PRReviewResult) -> str:
    """
    Condensed comment body for posting on the PR.

    A summary, not the full report: a per-file findings table plus the
    Critical/High items spelled out. Truncated to GitHub's size limit.
    """
    lines: list[str] = []
    lines.append("## 🤖 Multi-Agent Code Review\n")
    lines.append(
        f"Reviewed **{len(result.reviews)}** changed Python file(s) at "
        f"`{result.head_sha[:10]}` — **{result.total_findings}** finding(s).\n"
    )

    # Per-file summary table.
    lines.append("| File | 🔴 Critical | 🟠 High | 🟡 Medium | ⚪ Low |")
    lines.append("|------|------------|--------|----------|-------|")
    for review in result.reviews:
        counts = {s.value: 0 for s in Severity}
        for f in review.state.findings:
            counts[f.severity.value] += 1
        lines.append(
            f"| `{review.filename}` | {counts['Critical']} | {counts['High']} "
            f"| {counts['Medium']} | {counts['Low']} |"
        )

    # Spell out the most important findings.
    important = []
    for review in result.reviews:
        for f in review.state.findings:
            if f.severity in (Severity.CRITICAL, Severity.HIGH):
                important.append((review.filename, f))
    important.sort(key=lambda t: _SEVERITY_ORDER.get(t[1].severity.value, 9))

    if important:
        lines.append("\n### Top issues\n")
        for filename, f in important:
            loc = f"line {f.line}" if f.line else "general"
            cwe = f" · {f.cwe}" if f.cwe else ""
            lines.append(
                f"- **[{f.severity.value}]** `{filename}` ({loc}){cwe} — "
                f"{f.title}. {f.description}"
            )

    flagged = any(r.state.needs_human_review for r in result.reviews)
    if flagged:
        lines.append(
            "\n> ⚠️ Critical/High **security** findings were flagged for human "
            "review."
        )

    lines.append(
        "\n_Full report, fixed code, and generated tests were produced locally "
        "by the agent pipeline._"
    )
    lines.append("\n<sub>Automated review — verify before acting on suggestions.</sub>")

    body = "\n".join(lines)
    if len(body) > GITHUB_COMMENT_LIMIT:
        marker = "\n\n…(truncated)…"
        body = body[: GITHUB_COMMENT_LIMIT - len(marker)] + marker
    return body


# --- artifact writing ---------------------------------------------------


def _write_artifacts(result: PRReviewResult) -> dict[str, str]:
    """Write the PR report, each file's fixed code, and a combined ZIP."""
    slug = _slug(result.owner, result.repo, result.number)
    outputs: dict[str, str] = {}

    report_path = f"{slug}_review.md"
    Path(report_path).write_text(build_pr_report(result), encoding="utf-8")
    outputs["report"] = report_path

    for review in result.reviews:
        if review.state.patch:
            # Flatten nested paths so files don't collide / need dirs.
            stem = Path(review.filename).stem
            fixed_path = f"{slug}__{stem}_fixed.py"
            Path(fixed_path).write_text(
                review.state.patch.fixed_code, encoding="utf-8"
            )
            outputs[f"fixed:{review.filename}"] = fixed_path

    zip_path = f"{slug}_review.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in outputs.values():
            zf.write(p)
    outputs["zip"] = zip_path
    return outputs


# --- the shared entrypoint ----------------------------------------------


def handle_pr(
    client: GitHubPRClient,
    owner: str,
    repo: str,
    number: int,
    *,
    post_comment: bool = False,
    require_confirm: bool = True,
    max_files: int = 10,
) -> PRReviewResult:
    """
    Review one PR end to end.

    Fetches changed .py files at the PR head, runs the multi-agent pipeline on
    each, writes local artifacts, and (optionally) posts a summary comment.

    `require_confirm=True` prompts before posting (manual CLI); the watcher passes
    False to post non-interactively.
    """
    pr = client.get_pr(owner, repo, number)
    head_sha = pr["head"]["sha"]
    result = PRReviewResult(
        owner=owner,
        repo=repo,
        number=number,
        title=pr.get("title", ""),
        author=pr.get("user", {}).get("login", "unknown"),
        head_sha=head_sha,
    )

    all_files = client.list_changed_files(owner, repo, number)
    py = python_files(all_files)
    print(
        f"[pr] #{number} '{result.title}': {len(all_files)} changed file(s), "
        f"{len(py)} Python file(s)."
    )

    if not py:
        print("[pr] No reviewable Python files — nothing to do.")
        return result

    if len(py) > max_files:
        print(f"[pr] Capping review to {max_files} of {len(py)} Python files.")
        for extra in py[max_files:]:
            result.skipped.append(f"{extra.filename} (over --max-files cap)")
        py = py[:max_files]

    for f in py:
        try:
            source = client.get_file_content(owner, repo, f.filename, head_sha)
        except Exception as exc:  # noqa: BLE001
            print(f"[pr] could not fetch {f.filename}: {exc}")
            result.skipped.append(f"{f.filename} (fetch failed)")
            continue

        if len(source.encode("utf-8")) > MAX_FILE_BYTES:
            print(f"[pr] skipping {f.filename} (>{MAX_FILE_BYTES} bytes).")
            result.skipped.append(f"{f.filename} (too large)")
            continue

        print(f"[pr] reviewing {f.filename}…")
        state = run_pipeline(f.filename, source)
        result.reviews.append(FileReview(filename=f.filename, state=state))

    result.artifacts = _write_artifacts(result)

    if post_comment:
        _maybe_post_comment(client, result, require_confirm)

    return result


def _maybe_post_comment(
    client: GitHubPRClient, result: PRReviewResult, require_confirm: bool
) -> None:
    """Build the comment, optionally confirm, then post it."""
    if not result.reviews:
        print("[pr] no reviews to comment on; skipping comment.")
        return

    body = format_pr_comment(result)

    if require_confirm:
        print("\n" + "=" * 60)
        print("  COMMENT PREVIEW (will be posted to the PR)")
        print("=" * 60)
        print(body)
        print("=" * 60)
        answer = input("Post this comment to the PR? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("[pr] comment NOT posted (user declined).")
            return

    try:
        posted = client.post_pr_comment(
            result.owner, result.repo, result.number, body
        )
        result.comment_url = posted.get("html_url")
        print(f"[pr] comment posted: {result.comment_url}")
    except Exception as exc:  # noqa: BLE001
        print(f"[pr] failed to post comment: {exc}")
