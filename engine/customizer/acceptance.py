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


def recover_sync_acceptance(repository: str | Path, candidate_report_path: str | Path,
                            *, approved: bool = False) -> dict[str, Any]:
    """Finish an interrupted fast-forward after the candidate provenance commit exists."""
    if not approved:
        raise SyncPlanError("Acceptance recovery requires explicit --approve confirmation.")
    repo = Path(repository).expanduser().resolve()
    try:
        report = json.loads(Path(candidate_report_path).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncPlanError(f"Candidate report is unreadable: {exc}") from exc
    if not isinstance(report, dict) or report.get("operation") != "upstream_sync_candidate":
        raise SyncPlanError("A valid upstream candidate report is required.")
    candidate_value = report.get("candidate_path")
    if not isinstance(candidate_value, str) or not candidate_value.strip():
        raise SyncPlanError("Candidate report has no candidate workspace.")
    candidate = Path(candidate_value).expanduser().resolve()
    if not repo.is_dir() or not (repo / ".git").exists() or not candidate.is_dir() or not (candidate / ".git").exists():
        raise SyncPlanError("Original and candidate repositories must both exist.")
    if candidate == repo or repo in candidate.parents or candidate in repo.parents:
        raise SyncPlanError("Original and candidate repositories must be separate directories.")
    _assert_no_custom_git_drivers(repo)
    _assert_no_custom_git_drivers(candidate)
    target = str(report.get("upstream_target_sha", "")).lower()
    base = str(report.get("base_sha", "")).lower()
    customized = str(report.get("customized_sha", "")).lower()
    original_branch = report.get("original_branch")
    candidate_branch = report.get("candidate_branch")
    if not all((target, base, customized, original_branch, candidate_branch)):
        raise SyncPlanError("Candidate report is missing required branch or SHA identities.")
    if _git(candidate, "branch", "--show-current").stdout.strip() != candidate_branch:
        raise SyncPlanError("Candidate branch changed; recovery is blocked.")
    usc = candidate / ".usc"
    baseline_path = usc / "upstream-baseline.json"
    provenance_path = usc / "provenance" / f"sync-{target}.json"
    if usc.is_symlink() or baseline_path.is_symlink() or provenance_path.is_symlink():
        raise SyncPlanError("Candidate provenance paths are unsafe.")
    if not baseline_path.is_file() or not provenance_path.is_file():
        raise SyncPlanError("Candidate provenance is incomplete. If interrupted before provenance commit, discard the candidate and recreate it; original branch remains unchanged.")
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncPlanError(f"Candidate provenance or baseline is unreadable: {exc}") from exc
    if baseline.get("upstream_repository_url") != provenance.get("upstream_repository_url"):
        raise SyncPlanError("Candidate baseline and provenance upstream URLs do not match.")
    if str(baseline.get("last_imported_upstream_sha", "")).lower() != target:
        raise SyncPlanError("Candidate baseline does not point to the selected upstream target.")
    if str(provenance.get("base_sha", "")).lower() != base or str(provenance.get("upstream_target_sha", "")).lower() != target:
        raise SyncPlanError("Candidate provenance does not match candidate base/target.")
    if str(provenance.get("customized_sha_before_sync", "")).lower() != customized:
        raise SyncPlanError("Candidate provenance does not match the original customized SHA.")
    if provenance.get("candidate_branch") != candidate_branch or provenance.get("original_branch") != original_branch:
        raise SyncPlanError("Candidate provenance branch identities do not match the candidate report.")
    merge_sha = str(provenance.get("merge_commit_sha", "")).lower()
    final_tip = _git(candidate, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    merge_parents = _git(candidate, "rev-list", "--parents", "-n", "1", merge_sha).stdout.split()
    if len(merge_parents) != 3 or merge_parents[1].lower() != customized or merge_parents[2].lower() != target:
        raise SyncPlanError("Recorded upstream merge commit has unexpected parents.")
    tip_parents = _git(candidate, "rev-list", "--parents", "-n", "1", final_tip).stdout.split()
    if len(tip_parents) != 2 or tip_parents[1].lower() != merge_sha:
        raise SyncPlanError("Candidate tip is not the expected provenance commit.")
    merge_tree = _git(candidate, "rev-parse", "--verify", f"{merge_sha}^{{tree}}").stdout.strip().lower()
    if merge_tree != str(provenance.get("candidate_tree_sha", "")).lower():
        raise SyncPlanError("Provenance candidate tree does not match the upstream merge commit tree.")
    _git(candidate, "show", f"{final_tip}:.usc/upstream-baseline.json")
    _git(candidate, "show", f"{final_tip}:.usc/provenance/sync-{target}.json")

    head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if branch.returncode != 0 or branch.stdout.strip() != original_branch or status:
        raise SyncPlanError("Original branch identity changed or working tree is dirty; recovery will not update it.")
    if head == final_tip:
        return {"schema_version": "1.0", "operation": "upstream_sync_recovery",
                "status": "already_applied", "original_branch": original_branch,
                "accepted_commit_sha": final_tip, "upstream_target_sha": target,
                "baseline_advanced_to": target, "original_repository_updated": True}
    if head != customized:
        raise SyncPlanError("Original HEAD is neither the recorded customized SHA nor accepted commit; recovery is blocked.")
    if _git(repo, "merge-base", head, target).stdout.strip().lower() != base:
        raise SyncPlanError("Original repository no longer has the expected upstream merge base.")
    _git(repo, "-c", "protocol.file.allow=always", "fetch", "--no-tags", "--no-recurse-submodules", "--", str(candidate), final_tip)
    if _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower() != customized:
        raise SyncPlanError("Original HEAD changed during recovery; fast-forward was not attempted.")
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout:
        raise SyncPlanError("Original working tree changed during recovery; fast-forward was not attempted.")
    _git(repo, "merge", "--ff-only", "--no-edit", final_tip)
    if _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower() != final_tip:
        raise SyncPlanError("Recovery fast-forward did not reach the recorded provenance commit.")
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout:
        raise SyncPlanError("Recovery reached accepted commit but working tree is not clean; inspect manually.")
    return {"schema_version": "1.0", "operation": "upstream_sync_recovery",
            "status": "recovered", "original_branch": original_branch,
            "accepted_commit_sha": final_tip, "merge_commit_sha": merge_sha,
            "upstream_target_sha": target, "baseline_advanced_to": target,
            "original_repository_updated": True,
            "note": "Recovery fast-forwarded the original branch to the already committed candidate provenance tip."}
