"""Prepare a non-product verification commit for the exact uncommitted candidate tree."""
from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from urllib.parse import urlparse

from .sync import SyncPlanError, _assert_no_custom_git_drivers, _git


_REPO_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _canonical_push_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(parts) != 2
    ):
        raise SyncPlanError("push-url must be a canonical HTTPS GitHub OWNER/REPOSITORY URL.")
    owner = parts[0]
    repository = parts[1].removesuffix(".git")
    if not _REPO_PART_RE.fullmatch(owner) or not _REPO_PART_RE.fullmatch(repository):
        raise SyncPlanError("push-url contains an invalid GitHub owner or repository name.")
    canonical = f"https://github.com/{owner}/{repository}.git"
    return canonical, f"{owner}/{repository}"


def create_sync_verification_snapshot(
    repository: str | Path,
    candidate_report_path: str | Path,
    *,
    push_url: str,
) -> dict:
    """Create a one-parent commit/ref for CI without changing the candidate or product branch."""
    repo = Path(repository).expanduser().resolve()
    report_file = Path(candidate_report_path).expanduser().resolve()
    if not report_file.is_file():
        raise SyncPlanError("Candidate report must be an existing JSON file.")
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncPlanError(f"Candidate report is not valid readable JSON: {exc}") from exc
    if not isinstance(report, dict) or report.get("operation") != "upstream_sync_candidate":
        raise SyncPlanError("The supplied report is not an upstream sync candidate report.")
    if report.get("status") != "candidate_ready_for_review" or report.get("integration_committed") is not False:
        raise SyncPlanError("Only an uncommitted, conflict-free candidate can receive a verification snapshot.")

    canonical_url, remote_repository = _canonical_push_url(push_url)
    candidate_value = report.get("candidate_path")
    if not isinstance(candidate_value, str) or not candidate_value.strip():
        raise SyncPlanError("Candidate report has no valid candidate_path.")
    candidate = Path(candidate_value).expanduser().resolve()
    if (
        not repo.is_dir() or not (repo / ".git").exists()
        or not candidate.is_dir() or not (candidate / ".git").exists()
        or candidate == repo or candidate in repo.parents or repo in candidate.parents
    ):
        raise SyncPlanError("Original and candidate must be separate existing Git working repositories.")

    _assert_no_custom_git_drivers(repo)
    _assert_no_custom_git_drivers(candidate)
    original_head = str(report.get("customized_sha", "")).lower()
    original_branch = report.get("original_branch")
    if not isinstance(original_branch, str) or not original_branch:
        raise SyncPlanError("Candidate report has no original branch identity.")

    def original_unchanged() -> bool:
        return (
            _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower() == original_head
            and _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() == original_branch
            and not _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
        )

    if not original_unchanged():
        raise SyncPlanError("Original customized branch or working tree changed; verification snapshot is blocked.")

    candidate_head = _git(candidate, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    candidate_branch = _git(candidate, "branch", "--show-current").stdout.strip()
    if candidate_head != original_head or candidate_branch != report.get("candidate_branch"):
        raise SyncPlanError("Candidate HEAD or branch changed; recreate the candidate before snapshotting.")
    target = str(report.get("upstream_target_sha", "")).lower()
    merge_head = _git(candidate, "rev-parse", "--verify", "MERGE_HEAD^{commit}", check=False)
    if merge_head.returncode or merge_head.stdout.strip().lower() != target:
        raise SyncPlanError("Candidate is no longer in the expected uncommitted merge state.")
    if _git(candidate, "diff", "--name-only", "--diff-filter=U", "-z").stdout.strip("\0"):
        raise SyncPlanError("Candidate contains unresolved merge conflicts.")
    if _git(candidate, "diff", "--quiet", check=False).returncode:
        raise SyncPlanError("Candidate has unstaged file changes; snapshotting is blocked.")
    status_lines = _git(candidate, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
    if any(line.startswith("??") or (len(line) > 1 and line[1] != " ") for line in status_lines):
        raise SyncPlanError("Candidate has untracked or unstaged changes; snapshotting is blocked.")

    tree_sha = _git(candidate, "write-tree").stdout.strip().lower()
    branch_name = f"usc-verify/{target[:12]}-{tree_sha[:12]}"
    ref_name = f"refs/heads/{branch_name}"
    existing = _git(candidate, "show-ref", "--verify", "--quiet", ref_name, check=False)
    if existing.returncode == 0:
        snapshot_sha = _git(candidate, "rev-parse", "--verify", ref_name).stdout.strip().lower()
    elif existing.returncode == 1:
        snapshot_sha = _git(
            candidate,
            "-c", "user.name=USC Verification Snapshot",
            "-c", "user.email=usc-verification@invalid",
            "-c", "commit.gpgSign=false",
            "commit-tree", tree_sha, "-p", original_head,
            "-m", f"USC verification snapshot for upstream {target}",
        ).stdout.strip().lower()
        _git(candidate, "update-ref", ref_name, snapshot_sha)
    else:
        raise SyncPlanError("Git could not safely check the verification snapshot branch.")
    snapshot_tree = _git(candidate, "rev-parse", "--verify", f"{snapshot_sha}^{{tree}}").stdout.strip().lower()
    parents = _git(candidate, "rev-list", "--parents", "-n", "1", snapshot_sha).stdout.strip().split()
    if snapshot_tree != tree_sha or parents != [snapshot_sha, original_head]:
        raise SyncPlanError("Created verification snapshot does not match the expected candidate tree and parent.")
    if _git(candidate, "rev-parse", "--verify", ref_name).stdout.strip().lower() != snapshot_sha:
        raise SyncPlanError("Verification snapshot branch does not point to the created snapshot commit.")
    if not original_unchanged():
        raise SyncPlanError("Original customized repository changed during snapshot preparation.")
    if (
        _git(candidate, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower() != original_head
        or _git(candidate, "branch", "--show-current").stdout.strip() != candidate_branch
        or _git(candidate, "rev-parse", "--verify", "MERGE_HEAD^{commit}").stdout.strip().lower() != target
        or _git(candidate, "write-tree").stdout.strip().lower() != tree_sha
    ):
        raise SyncPlanError("Candidate merge state changed while creating the verification snapshot.")

    push_command = (
        f"git -C {shlex.quote(str(candidate))} push {shlex.quote(canonical_url)} "
        f"{snapshot_sha}:refs/heads/{branch_name}"
    )
    return {
        "schema_version": "1.0",
        "operation": "upstream_sync_verification_snapshot",
        "status": "snapshot_ready_to_publish",
        "repository": remote_repository,
        "push_url": canonical_url,
        "candidate_path": str(candidate),
        "candidate_branch": candidate_branch,
        "snapshot_branch": branch_name,
        "snapshot_commit_sha": snapshot_sha,
        "candidate_tree_sha": tree_sha,
        "parent_sha": original_head,
        "upstream_target_sha": target,
        "push_command": push_command,
        "push_performed": False,
        "original_repository_unchanged": True,
        "candidate_merge_state_unchanged": True,
        "note": (
            "This is a temporary verification-only commit with the exact candidate tree and customized commit as its sole parent. "
            "It does not change the product branch, candidate branch, upstream baseline, or provenance. "
            "Review the report, then run push_command manually using your normal GitHub authentication."
        ),
    }
