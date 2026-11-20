"""Explicitly discard only a verified USC-created sync candidate workspace."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .sync import SyncPlanError, _assert_no_custom_git_drivers, _git


_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$", re.IGNORECASE)
_CANDIDATE_BRANCH_PREFIX = "usc-sync-candidate-"


def discard_sync_candidate(
    repository: str | Path,
    candidate_report_path: str | Path,
    *,
    approved: bool = False,
) -> dict[str, Any]:
    """Remove a USC-created uncommitted candidate after strict identity checks.

    The original customized repository is never removed or modified. Deletion
    requires explicit approval and is limited to the exact workspace recorded
    in a valid candidate report.
    """
    if not approved:
        raise SyncPlanError("Candidate discard requires explicit --approve confirmation.")

    repo_arg = Path(repository).expanduser()
    if repo_arg.is_symlink():
        raise SyncPlanError("Original repository path must not be a symlink.")
    try:
        repo = repo_arg.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SyncPlanError(f"Original repository path cannot be resolved: {exc}") from exc
    if not repo.is_dir() or (repo / ".git").is_symlink() or not (repo / ".git").exists():
        raise SyncPlanError("Original path must be an existing, non-symlink Git working repository.")

    try:
        report = json.loads(Path(candidate_report_path).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncPlanError(f"Candidate report is unreadable: {exc}") from exc
    if not isinstance(report, dict) or report.get("schema_version") != "1.0":
        raise SyncPlanError("A valid version 1.0 candidate report is required.")
    if report.get("operation") != "upstream_sync_candidate":
        raise SyncPlanError("Report does not describe a USC upstream sync candidate.")
    if report.get("status") not in {"candidate_ready_for_review", "blocked"}:
        raise SyncPlanError("Only an unaccepted candidate in review or blocked state can be discarded.")
    if report.get("integration_committed") is not False:
        raise SyncPlanError("Candidate report does not prove that integration remains uncommitted.")
    if report.get("original_repository_unchanged") is not True:
        raise SyncPlanError("Candidate report does not confirm original repository preservation.")

    candidate_value = report.get("candidate_path")
    if not isinstance(candidate_value, str) or not candidate_value.strip():
        raise SyncPlanError("Candidate report has no candidate_path.")
    candidate_arg = Path(candidate_value).expanduser()
    if candidate_arg.is_symlink():
        raise SyncPlanError("Candidate workspace must not be a symlink.")
    try:
        candidate = candidate_arg.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SyncPlanError(f"Candidate workspace cannot be resolved: {exc}") from exc
    if not candidate.is_dir() or (candidate / ".git").is_symlink() or not (candidate / ".git").exists():
        raise SyncPlanError("Candidate workspace must be an existing, non-symlink Git working repository.")
    if candidate == repo or repo in candidate.parents or candidate in repo.parents:
        raise SyncPlanError("Candidate and original repositories must be separate, non-nested directories.")

    # Require the report to identify this exact path, not merely a similarly
    # named directory supplied by an operator.
    if str(candidate) != str(Path(candidate_value).expanduser().absolute().resolve(strict=True)):
        raise SyncPlanError("Candidate path identity is ambiguous; recreate the candidate report.")

    candidate_branch = report.get("candidate_branch")
    original_branch = report.get("original_branch")
    base = str(report.get("base_sha", "")).lower()
    target = str(report.get("upstream_target_sha", "")).lower()
    customized = str(report.get("customized_sha", "")).lower()
    if (
        not isinstance(candidate_branch, str)
        or not candidate_branch.startswith(_CANDIDATE_BRANCH_PREFIX)
        or candidate_branch != f"{_CANDIDATE_BRANCH_PREFIX}{target[:12]}"
        or not isinstance(original_branch, str)
        or not original_branch
        or not all(_SHA_RE.fullmatch(value) for value in (base, target, customized))
    ):
        raise SyncPlanError("Candidate report has invalid branch or commit identities.")

    _assert_no_custom_git_drivers(repo)
    _assert_no_custom_git_drivers(candidate)

    original_head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    original_status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    original_branch_now = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if (
        original_branch_now.returncode != 0
        or original_branch_now.stdout.strip() != original_branch
        or original_head != customized
        or original_status
    ):
        raise SyncPlanError("Original repository identity or clean state changed; candidate discard is blocked.")

    candidate_root = Path(_git(candidate, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if candidate_root != candidate:
        raise SyncPlanError("Candidate Git worktree root does not match the recorded workspace.")
    current_branch = _git(candidate, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if current_branch.returncode != 0 or current_branch.stdout.strip() != candidate_branch:
        raise SyncPlanError("Candidate branch identity changed; refusing to discard.")
    candidate_head = _git(candidate, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    if candidate_head != customized:
        raise SyncPlanError("Candidate HEAD changed or was committed; refusing to discard.")
    merge_head = _git(candidate, "rev-parse", "--verify", "MERGE_HEAD^{commit}", check=False)
    if merge_head.returncode != 0 or merge_head.stdout.strip().lower() != target:
        raise SyncPlanError("Candidate is not in the expected uncommitted merge state; refusing to discard.")

    origin = _git(candidate, "remote", "get-url", "origin").stdout.strip()
    origin_path = Path(origin).expanduser()
    if not origin or not origin_path.is_absolute() or origin_path.resolve() != repo:
        raise SyncPlanError("Candidate origin does not identify the supplied original repository.")

    actual_base = _git(candidate, "merge-base", customized, target).stdout.strip().lower()
    if actual_base != base:
        raise SyncPlanError("Candidate base/target ancestry does not match the recorded candidate report.")

    # Recheck the original immediately before the only destructive operation.
    if (
        _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower() != customized
        or _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    ):
        raise SyncPlanError("Original repository changed immediately before discard; candidate was retained.")

    shutil.rmtree(candidate)
    if candidate.exists() or candidate.is_symlink():
        raise SyncPlanError("Candidate workspace could not be fully removed; inspect the candidate path manually.")

    return {
        "schema_version": "1.0",
        "operation": "upstream_sync_candidate_discard",
        "status": "discarded",
        "candidate_path": str(candidate),
        "candidate_branch": candidate_branch,
        "original_branch": original_branch,
        "original_customized_sha": customized,
        "upstream_target_sha": target,
        "original_repository_updated": False,
        "candidate_workspace_removed": True,
        "note": "Only the validated USC candidate workspace was removed. The original customized repository was not modified.",
    }
