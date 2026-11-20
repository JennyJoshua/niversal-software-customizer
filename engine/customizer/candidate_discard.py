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


def _contains_symlink_component(path: Path) -> bool:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


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
    if _contains_symlink_component(repo_arg):
        raise SyncPlanError("Original repository path must not contain symlink components.")
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
    if _contains_symlink_component(candidate_arg):
        raise SyncPlanError("Candidate workspace path must not contain symlink components.")
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
    if not candidate_arg.is_absolute() or ".." in candidate_arg.parts or candidate_arg != candidate:
        raise SyncPlanError("Candidate path must be an absolute, normalized path without traversal components.")

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
    merge_head = _git(candidate, "rev-parse", "--verify", "MERGE_HEAD^{commit}", check=False)
    candidate_state = "uncommitted_merge"
    if candidate_head == customized:
        if merge_head.returncode != 0 or merge_head.stdout.strip().lower() != target:
            raise SyncPlanError("Candidate is not in the expected uncommitted merge state; refusing to discard.")
    else:
        # Acceptance commits the candidate merge before writing provenance. If
        # interrupted at that boundary, permit discard only for the exact
        # two-parent merge commit USC would have created, with no later edits.
        parents = _git(candidate, "rev-list", "--parents", "-n", "1", candidate_head).stdout.strip().split()
        if parents != [candidate_head, customized, target] or merge_head.returncode == 0:
            raise SyncPlanError("Candidate HEAD is not the exact pre-provenance USC merge commit; refusing to discard.")
        if _git(candidate, "status", "--porcelain=v1", "--untracked-files=all").stdout:
            raise SyncPlanError("Pre-provenance candidate has uncommitted changes; inspect it manually instead of discarding.")
        usc_dir = candidate / ".usc"
        provenance_dir = usc_dir / "provenance"
        provenance_path = provenance_dir / ("sync-" + target + ".json")
        baseline_path = usc_dir / "upstream-baseline.json"
        if usc_dir.is_symlink() or provenance_dir.is_symlink() or provenance_path.is_symlink() or provenance_path.exists():
            raise SyncPlanError("Pre-provenance candidate contains unexpected provenance state; refusing to discard.")
        baseline_in_parent = _git(candidate, "cat-file", "-e", customized + ":.usc/upstream-baseline.json", check=False).returncode == 0
        if baseline_in_parent:
            expected_baseline = _git(candidate, "show", customized + ":.usc/upstream-baseline.json").stdout
            if baseline_path.is_symlink() or not baseline_path.is_file() or baseline_path.read_text(encoding="utf-8") != expected_baseline:
                raise SyncPlanError("Pre-provenance candidate baseline differs from the customized parent; refusing to discard.")
        elif baseline_path.exists() or baseline_path.is_symlink():
            raise SyncPlanError("Pre-provenance candidate has an unexpected new baseline; refusing to discard.")
        candidate_state = "merge_committed_before_provenance"

    origin = _git(candidate, "remote", "get-url", "origin").stdout.strip()
    origin_path = Path(origin).expanduser()
    if not origin or not origin_path.is_absolute() or origin_path.resolve() != repo:
        raise SyncPlanError("Candidate origin does not identify the supplied original repository.")

    actual_base = _git(candidate, "merge-base", customized, target).stdout.strip().lower()
    if actual_base != base:
        raise SyncPlanError("Candidate base/target ancestry does not match the recorded candidate report.")

    # Recheck candidate identity immediately before removal.
    final_candidate_head = _git(candidate, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    final_candidate_branch = _git(candidate, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if final_candidate_head != candidate_head or final_candidate_branch.returncode != 0 or final_candidate_branch.stdout.strip() != candidate_branch:
        raise SyncPlanError("Candidate identity changed immediately before discard; candidate was retained.")
    if candidate_state == "merge_committed_before_provenance":
        final_parents = _git(candidate, "rev-list", "--parents", "-n", "1", final_candidate_head).stdout.strip().split()
        if final_parents != [final_candidate_head, customized, target] or _git(candidate, "status", "--porcelain=v1", "--untracked-files=all").stdout:
            raise SyncPlanError("Pre-provenance candidate changed immediately before discard; candidate was retained.")

    # Recheck the original immediately before the only destructive operation.
    final_branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if (
        final_branch.returncode != 0
        or final_branch.stdout.strip() != original_branch
        or _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower() != customized
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
        "candidate_state": candidate_state,
        "original_repository_updated": False,
        "candidate_workspace_removed": True,
        "note": "Only the validated USC candidate workspace was removed. The original customized repository was not modified.",
    }
