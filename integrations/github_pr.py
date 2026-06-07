"""
GitHub REST client for fetching pull-request contents and posting comments.

Uses `requests` against the GitHub REST API (v3) — no PyGithub dependency. Token
resolution mirrors `llm/backend.py`: env var first, then Colab Secrets, so the
same code path works locally and in a notebook.

Reading public PRs works without a token (subject to a low anonymous rate
limit). Posting comments always requires a token with write access to the repo.

Token scopes for the demo (PRs on the user's own fork `rahulilla/airflow`):
a fine-grained PAT with *Pull requests: Read and write* + *Contents: Read*, or a
classic PAT with `public_repo`.
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

import requests

API_ROOT = "https://api.github.com"
DEFAULT_TIMEOUT = 30
# Skip files larger than this (bytes) — too big for a useful single-shot review.
MAX_FILE_BYTES = 50_000

_PR_URL_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)


@dataclass
class PRFile:
    """A file changed in a pull request."""

    filename: str
    status: str  # added | modified | removed | renamed
    additions: int
    deletions: int


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """
    Parse a PR URL into (owner, repo, number).

    Accepts the canonical form and the `/files` (and other) suffix variants:
      https://github.com/{owner}/{repo}/pull/{n}
      https://github.com/{owner}/{repo}/pull/{n}/files
    Raises ValueError for anything that isn't a PR URL.
    """
    match = _PR_URL_RE.search(url.strip())
    if not match:
        raise ValueError(
            f"Not a GitHub pull-request URL: {url!r}. "
            "Expected https://github.com/<owner>/<repo>/pull/<number>"
        )
    return match.group("owner"), match.group("repo"), int(match.group("number"))


def resolve_github_token() -> Optional[str]:
    """Find a GitHub token from env (GITHUB_TOKEN/GH_TOKEN) or Colab Secrets."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        token = os.getenv(var)
        if token:
            return token
    try:  # pragma: no cover - Colab-only
        from google.colab import userdata  # type: ignore

        return userdata.get("GITHUB_TOKEN")
    except Exception:
        return None


class GitHubError(RuntimeError):
    """Raised for non-success GitHub API responses, with a readable message."""


class GitHubPRClient:
    """Thin GitHub REST client scoped to the calls this project needs."""

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token if token is not None else resolve_github_token()
        self.session = requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers.update(headers)

    @property
    def authenticated(self) -> bool:
        return bool(self.token)

    # --- low-level ------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> requests.Response:
        resp = self.session.get(
            f"{API_ROOT}{path}", params=params, timeout=DEFAULT_TIMEOUT
        )
        self._raise_for_status(resp)
        return resp

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code < 400:
            return
        # Surface a useful message rather than a raw traceback.
        detail = ""
        try:
            detail = resp.json().get("message", "")
        except Exception:
            detail = resp.text[:200]
        remaining = resp.headers.get("X-RateLimit-Remaining")
        hint = ""
        if resp.status_code in (403, 429) and remaining == "0":
            hint = (
                " (rate limit exhausted — set GITHUB_TOKEN to raise the limit)"
            )
        elif resp.status_code == 404 and not self.authenticated:
            hint = " (404 may mean a private repo; set GITHUB_TOKEN)"
        raise GitHubError(
            f"GitHub API {resp.status_code} for {resp.url}: {detail}{hint}"
        )

    # --- pull requests --------------------------------------------------

    def get_pr(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        """Fetch PR metadata. Includes head.sha, title, user.login, etc."""
        return self._get(f"/repos/{owner}/{repo}/pulls/{number}").json()

    def list_open_prs(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """List open PRs (newest first). Used by the watcher."""
        return self._get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "open", "sort": "created", "direction": "desc",
                    "per_page": 100},
        ).json()

    def list_changed_files(
        self, owner: str, repo: str, number: int
    ) -> list[PRFile]:
        """List files changed in a PR, following pagination."""
        files: list[PRFile] = []
        page = 1
        while True:
            batch = self._get(
                f"/repos/{owner}/{repo}/pulls/{number}/files",
                params={"per_page": 100, "page": page},
            ).json()
            if not batch:
                break
            for f in batch:
                files.append(
                    PRFile(
                        filename=f.get("filename", ""),
                        status=f.get("status", ""),
                        additions=f.get("additions", 0),
                        deletions=f.get("deletions", 0),
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return files

    def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str:
        """Fetch a file's text at a given ref (PR head SHA). UTF-8 decoded."""
        resp = self._get(
            f"/repos/{owner}/{repo}/contents/{path}", params={"ref": ref}
        )
        payload = resp.json()
        if payload.get("encoding") == "base64" and "content" in payload:
            raw = base64.b64decode(payload["content"])
            return raw.decode("utf-8", errors="replace")
        # Fallback: some responses use download_url for large files.
        download_url = payload.get("download_url")
        if download_url:
            r2 = self.session.get(download_url, timeout=DEFAULT_TIMEOUT)
            self._raise_for_status(r2)
            return r2.text
        raise GitHubError(f"Could not decode content for {path}@{ref}")

    def post_pr_comment(
        self, owner: str, repo: str, number: int, body: str
    ) -> dict[str, Any]:
        """Post a conversation comment on a PR (PRs are issues for comments)."""
        if not self.authenticated:
            raise GitHubError(
                "Posting a comment requires a token. Set GITHUB_TOKEN with "
                "write access to the repo."
            )
        resp = self.session.post(
            f"{API_ROOT}/repos/{owner}/{repo}/issues/{number}/comments",
            json={"body": body},
            timeout=DEFAULT_TIMEOUT,
        )
        self._raise_for_status(resp)
        return resp.json()


def python_files(files: list[PRFile]) -> list[PRFile]:
    """Filter changed files to reviewable Python sources (not deleted)."""
    return [
        f
        for f in files
        if f.status != "removed" and f.filename.endswith(".py")
    ]
