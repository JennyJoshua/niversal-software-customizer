"""Explicit acceptance of a verified upstream candidate."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from . import __version__
from .sync import SyncPlanError, _assert_no_custom_git_drivers, _git, create_sync_plan


def accept_sync_candidate(
    repository: str | Path,
    candidate_report_path: str | Path,
    verification_report_path: str | Path,
    *,
    upstream_url: str,
    approved: bool = False,
    evidence_reviewed: bool = False,
) -> dict[str, Any]:
    """Prepare merge/provenance commits in the candidate, then fast-forward original."""
    if not approved:
        raise SyncPlanError("Candidate acceptance requires explicit --approve confirmation.")
    if not evidence_reviewed:
        raise SyncPlanError("Acceptance requires --evidence-reviewed because external CI evidence is not independently authenticated.")
    parsed = urlparse(upstream_url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or len(parts) != 2:
        raise SyncPlanError("upstream-url must be an HTTPS GitHub owner/repository URL.")
    upstream_url = f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}"

    repo = Path(repository).expanduser().resolve()
    try:
        report = json.loads(Path(candidate_report_path).expanduser().read_text(encoding="utf-8"))
        verification = json.loads(Path(verification_report_path).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncPlanError(f"Candidate or verification report is unreadable: {exc}") from exc
    if not isinstance(report, dict) or not isinstance(verification, dict):
        raise SyncPlanError("Candidate and verification reports must be JSON objects.")
    if report.get("operation") != "upstream_sync_candidate" or report.get("status") != "candidate_ready_for_review":
        raise SyncPlanError("Only a conflict-free candidate can be accepted.")
    if report.get("integration_committed") is not False or report.get("original_repository_unchanged") is not True:
        raise SyncPlanError("Candidate report does not prove an isolated, uncommitted candidate.")
    if verification.get("operation") != "upstream_sync_verification" or verification.get("status") != "verification_passed":
        raise SyncPlanError("A successful sync-verify report is required.")
    for key in ("base_sha", "upstream_target_sha", "customized_sha", "candidate_branch"):
        if verification.get(key) != report.get(key):
            raise SyncPlanError(f"Verification report does not match candidate field: {key}.")
    if verification.get("rights_reviewed") is not report.get("rights_reviewed"):
        raise SyncPlanError("Verification rights acknowledgement does not match candidate report.")

    candidate_value = report.get("candidate_path")
    if not isinstance(candidate_value, str) or not candidate_value.strip():
        raise SyncPlanError("Candidate report has no candidate_path.")
    candidate = Path(candidate_value).expanduser().resolve()
    if not repo.is_dir() or not (repo / ".git").exists() or not candidate.is_dir() or not (candidate / ".git").exists():
        raise SyncPlanError("Original and candidate paths must both be Git working repositories.")
    if candidate == repo or repo in candidate.parents or candidate in repo.parents:
        raise SyncPlanError("Original and candidate repositories must be separate directories.")

    _assert_no_custom_git_drivers(repo)
    _assert_no_custom_git_drivers(candidate)
    original_head = str(report.get("customized_sha", "")).lower()
    original_branch = report.get("original_branch")
    if not isinstance(original_branch, str) or not original_branch:
        raise SyncPlanError("Candidate report has no original branch identity; recreate the candidate.")
    def original_is_unchanged() -> bool:
        return (
            _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower() == original_head
            and _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() == original_branch
            and not _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
        )
    if not original_is_unchanged():
        raise SyncPlanError("Original customized branch or working tree changed after candidate creation; acceptance is blocked.")

    plan = create_sync_plan(repo, report["base_sha"], report["upstream_target_sha"])
    if plan["status"] != "ready_for_review":
        raise SyncPlanError("Fresh upstream sync preflight is blocked.")
    if plan["rights_review_required"] and report.get("rights_reviewed") is not True:
        raise SyncPlanError("Changed upstream rights evidence has not been acknowledged.")

    if _git(candidate, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower() != original_head:
        raise SyncPlanError("Candidate HEAD changed after verification.")
    if _git(candidate, "branch", "--show-current").stdout.strip() != report.get("candidate_branch"):
        raise SyncPlanError("Candidate branch changed after verification.")
    merge_head = _git(candidate, "rev-parse", "--verify", "MERGE_HEAD^{commit}", check=False)
    if merge_head.returncode or merge_head.stdout.strip().lower() != str(report["upstream_target_sha"]).lower():
        raise SyncPlanError("Candidate is no longer in the expected uncommitted merge state.")
    if _git(candidate, "diff", "--quiet", check=False).returncode:
        raise SyncPlanError("Candidate working files changed after verification.")
    state = _git(candidate, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
    if any(line.startswith("??") or (len(line) > 1 and line[1] != " ") for line in state):
        raise SyncPlanError("Candidate has untracked or unstaged changes.")
    tree_sha = _git(candidate, "write-tree").stdout.strip().lower()
    if tree_sha != str(verification["candidate_tree_sha"]).lower():
        raise SyncPlanError("Candidate tree no longer matches the verified tree SHA.")

    name = _git(repo, "config", "--local", "--get", "user.name", check=False).stdout.strip()
    email = _git(repo, "config", "--local", "--get", "user.email", check=False).stdout.strip()
    if not name or not email:
        raise SyncPlanError("Configure local Git user.name and user.email in the original repository before acceptance.")

    usc = candidate / ".usc"
    provenance_dir = usc / "provenance"
    baseline_path = usc / "upstream-baseline.json"
    provenance_path = provenance_dir / f"sync-{report['upstream_target_sha']}.json"
    if usc.is_symlink() or (usc.exists() and not usc.is_dir()) or provenance_dir.is_symlink() or (provenance_dir.exists() and not provenance_dir.is_dir()):
        raise SyncPlanError("The .usc provenance directory is unsafe.")
    if baseline_path.is_symlink() or provenance_path.is_symlink() or provenance_path.exists():
        raise SyncPlanError("The baseline/provenance path is unsafe or this target was already recorded.")
    if baseline_path.exists():
        try:
            old_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncPlanError(f"Existing upstream baseline is unreadable: {exc}") from exc
        if old_baseline.get("upstream_repository_url") != upstream_url or str(old_baseline.get("last_imported_upstream_sha", "")).lower() != str(report["base_sha"]).lower():
            raise SyncPlanError("Existing upstream baseline does not match this candidate's repository and base SHA.")

    _git(candidate, "-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "commit.gpgSign=false", "commit", "--no-edit")
    merge_sha = _git(candidate, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    accepted_at = datetime.now().astimezone().isoformat()
    provenance_dir.mkdir(parents=True, exist_ok=True)
    provenance = {
        "schema_version": "1.0",
        "operation": "accepted_upstream_sync",
        "upstream_repository_url": upstream_url,
        "base_sha": report["base_sha"],
        "upstream_target_sha": report["upstream_target_sha"],
        "customized_sha_before_sync": original_head,
        "candidate_tree_sha": tree_sha,
        "candidate_branch": report["candidate_branch"],
        "original_branch": original_branch,
        "upstream_changes": plan["upstream_changes"],
        "local_changes": plan["local_changes"],
        "rights_reviewed": report.get("rights_reviewed", False),
        "reviewer": verification.get("reviewer"),
        "verified_at": verification.get("verified_at"),
        "verification_source": verification.get("verification_source"),
        "test_results": verification.get("test_results", []),
        "verification_evidence_authenticated": verification.get("evidence_authenticated", False),
        "evidence_reviewed_by_acceptor": True,
        "accepted_at": accepted_at,
        "merge_commit_sha": merge_sha,
        "tool_version": __version__,
    }
    baseline = {
        "schema_version": "1.0",
        "upstream_repository_url": upstream_url,
        "last_imported_upstream_sha": report["upstream_target_sha"],
        "last_customized_merge_commit_sha": merge_sha,
        "accepted_at": accepted_at,
        "provenance_path": provenance_path.relative_to(candidate).as_posix(),
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    baseline_path.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _git(candidate, "add", "--", provenance_path.relative_to(candidate).as_posix(), baseline_path.relative_to(candidate).as_posix())
    _git(candidate, "-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "commit.gpgSign=false",
         "commit", "-m", "chore: record accepted upstream synchronization")
    final_tip = _git(candidate, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()

    if not original_is_unchanged():
        raise SyncPlanError("Original repository changed during acceptance preparation; original branch was not advanced.")
    _git(repo, "-c", "protocol.file.allow=always", "fetch", "--no-tags", "--no-recurse-submodules", "--", str(candidate), final_tip)
    if not original_is_unchanged():
        raise SyncPlanError("Original repository changed before fast-forward; its branch was not intentionally advanced.")
    _git(repo, "merge", "--ff-only", "--no-edit", final_tip)
    if _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower() != final_tip:
        raise SyncPlanError("Fast-forward acceptance did not reach the verified provenance commit.")
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout:
        raise SyncPlanError("Acceptance reached the new commit but the original working tree is not clean; inspect manually.")
    return {
        "schema_version": "1.0",
        "operation": "upstream_sync_acceptance",
        "status": "accepted",
        "original_branch": original_branch,
        "previous_customized_sha": original_head,
        "upstream_target_sha": report["upstream_target_sha"],
        "merge_commit_sha": merge_sha,
        "provenance_commit_sha": final_tip,
        "provenance_path": provenance_path.relative_to(candidate).as_posix(),
        "baseline_advanced_to": report["upstream_target_sha"],
        "original_repository_updated": True,
        "accepted_at": accepted_at,
        "note": "The original branch was fast-forwarded only after explicit approval, evidence acknowledgement, fresh HEAD/clean-tree checks, and verified candidate-tree matching.",
    }
