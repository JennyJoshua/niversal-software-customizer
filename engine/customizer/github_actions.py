"""Independently authenticate a GitHub Actions run for an exact candidate tree."""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
from typing import Any

from .sync import SyncPlanError


_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$", re.IGNORECASE)
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _api_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Universal-Software-Customizer",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyncPlanError(f"GitHub Actions evidence could not be retrieved: {exc}") from exc
    if not isinstance(payload, dict):
        raise SyncPlanError("GitHub API returned an unexpected non-object response.")
    return payload


def authenticate_github_actions_run(
    run_url: str,
    *,
    expected_repository: str,
    expected_tree_sha: str,
    expected_workflow_id: int,
    expected_workflow_path: str,
    expected_workflow_blob_sha: str,
) -> dict[str, Any]:
    """Verify a public GitHub Actions run and pin it to a trusted workflow and exact Git tree.

    The run must be a successful push on an isolated usc-verify/* branch. Its commit
    tree and workflow-file blob must match the caller's trusted values.
    """
    if not isinstance(expected_repository, str) or not _REPO_RE.fullmatch(expected_repository):
        raise SyncPlanError("Expected GitHub repository must use OWNER/REPOSITORY form.")
    if not isinstance(expected_tree_sha, str) or not _SHA_RE.fullmatch(expected_tree_sha):
        raise SyncPlanError("Expected candidate tree SHA must be a full Git object SHA.")
    if not isinstance(expected_workflow_blob_sha, str) or not _SHA_RE.fullmatch(expected_workflow_blob_sha):
        raise SyncPlanError("Trusted workflow blob SHA must be a full Git object SHA.")
    if isinstance(expected_workflow_id, bool) or not isinstance(expected_workflow_id, int) or expected_workflow_id <= 0:
        raise SyncPlanError("Trusted GitHub Actions workflow ID must be a positive integer.")
    if (
        not isinstance(expected_workflow_path, str)
        or not expected_workflow_path
        or expected_workflow_path.startswith("/")
        or any(part in ("", ".", "..") for part in expected_workflow_path.split("/"))
    ):
        raise SyncPlanError("Trusted workflow path must be a safe repository-relative path.")

    parsed = urlparse(run_url)
    match = re.fullmatch(r"/([^/]+)/([^/]+)/actions/runs/([0-9]+)/?", parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not match
    ):
        raise SyncPlanError("GitHub run URL must be a canonical https://github.com/OWNER/REPOSITORY/actions/runs/ID URL.")

    owner, repository, run_id_text = match.groups()
    actual_repository = f"{owner}/{repository}"
    if actual_repository.lower() != expected_repository.lower():
        raise SyncPlanError("GitHub run URL repository does not match the trusted repository.")
    api_root = f"https://api.github.com/repos/{owner}/{repository}"
    run_id = int(run_id_text)
    run = _api_json(f"{api_root}/actions/runs/{run_id}")

    if run.get("id") != run_id:
        raise SyncPlanError("GitHub Actions API returned a different run ID.")
    repository_data = run.get("repository")
    if not isinstance(repository_data, dict) or str(repository_data.get("full_name", "")).lower() != expected_repository.lower():
        raise SyncPlanError("GitHub Actions run belongs to a different repository.")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise SyncPlanError("GitHub Actions run must be completed with conclusion=success.")
    if run.get("event") != "push":
        raise SyncPlanError("Trusted candidate verification requires a push-triggered GitHub Actions run.")
    branch = run.get("head_branch")
    if not isinstance(branch, str) or not branch.startswith("usc-verify/"):
        raise SyncPlanError("GitHub Actions run must use an isolated usc-verify/ branch.")
    if run.get("workflow_id") != expected_workflow_id or run.get("path") != expected_workflow_path:
        raise SyncPlanError("GitHub Actions run does not match the pinned workflow identity.")

    head_sha = run.get("head_sha")
    if not isinstance(head_sha, str) or not _SHA_RE.fullmatch(head_sha):
        raise SyncPlanError("GitHub Actions run does not contain a valid head commit SHA.")
    commit = _api_json(f"{api_root}/git/commits/{head_sha}")
    tree = commit.get("tree")
    if not isinstance(tree, dict) or str(tree.get("sha", "")).lower() != expected_tree_sha.lower():
        raise SyncPlanError("GitHub Actions head commit tree does not match the exact candidate tree.")

    content_path = quote(expected_workflow_path, safe="/")
    content_url = f"{api_root}/contents/{content_path}?{urlencode({'ref': head_sha})}"
    workflow_file = _api_json(content_url)
    if str(workflow_file.get("sha", "")).lower() != expected_workflow_blob_sha.lower():
        raise SyncPlanError("Workflow file differs from the independently pinned trusted workflow blob.")

    jobs_response = _api_json(f"{api_root}/actions/runs/{run_id}/jobs?per_page=100")
    jobs = jobs_response.get("jobs")
    total_count = jobs_response.get("total_count")
    if not isinstance(jobs, list) or not jobs or total_count != len(jobs):
        raise SyncPlanError("GitHub Actions job list is empty or incomplete; verification is blocked.")
    for job in jobs:
        if not isinstance(job, dict) or job.get("status") != "completed" or job.get("conclusion") != "success":
            raise SyncPlanError("Every job in the trusted GitHub Actions run must complete successfully.")

    return {
        "provider": "github_actions",
        "authenticated": True,
        "repository": actual_repository,
        "run_id": run_id,
        "run_url": run_url,
        "event": "push",
        "branch": branch,
        "head_sha": head_sha.lower(),
        "candidate_tree_sha": expected_tree_sha.lower(),
        "workflow_id": expected_workflow_id,
        "workflow_path": expected_workflow_path,
        "workflow_blob_sha": expected_workflow_blob_sha.lower(),
        "job_count": len(jobs),
        "conclusion": "success",
    }
