"""Validate externally produced sync-candidate test evidence without executing project code."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .sync import SyncPlanError, _assert_no_custom_git_drivers, _git


def create_sync_verification(
    candidate_report_path: str | Path,
    evidence_path: str | Path,
) -> dict[str, Any]:
    """Bind reviewer-supplied test evidence to the exact current candidate tree."""
    report_file = Path(candidate_report_path).expanduser().resolve()
    evidence_file = Path(evidence_path).expanduser().resolve()
    if not report_file.is_file() or not evidence_file.is_file():
        raise SyncPlanError("Candidate report and verification evidence must be existing JSON files.")
    try:
        candidate_report = json.loads(report_file.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncPlanError(f"Candidate report or verification evidence is not valid readable JSON: {exc}") from exc
    if not isinstance(candidate_report, dict) or not isinstance(evidence, dict):
        raise SyncPlanError("Candidate report and verification evidence must each contain a JSON object.")
    if candidate_report.get("operation") != "upstream_sync_candidate":
        raise SyncPlanError("The supplied report is not an upstream sync candidate report.")
    if candidate_report.get("status") != "candidate_ready_for_review":
        raise SyncPlanError("Only a conflict-free candidate can be verified.")
    if candidate_report.get("integration_committed") is not False or candidate_report.get("original_repository_unchanged") is not True:
        raise SyncPlanError("Candidate report does not prove the expected uncommitted, isolated candidate state.")
    candidate_value = candidate_report.get("candidate_path")
    if not isinstance(candidate_value, str) or not candidate_value.strip():
        raise SyncPlanError("Candidate report does not contain a valid candidate path.")
    candidate = Path(candidate_value).expanduser().resolve()
    if not candidate.is_dir() or not (candidate / ".git").exists():
        raise SyncPlanError("The candidate repository is missing or is not a Git working repository.")

    for field in ("reviewer", "verification_source"):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            raise SyncPlanError(f"Verification evidence must include a non-empty {field}.")
    if evidence.get("schema_version") != "1.0":
        raise SyncPlanError("Unsupported verification evidence schema_version; expected 1.0.")
    if evidence.get("verification_status") != "passed":
        raise SyncPlanError("Verification evidence must explicitly report verification_status=passed.")
    if evidence.get("rights_reviewed") is not bool(candidate_report.get("rights_reviewed", False)):
        raise SyncPlanError("Verification rights_reviewed acknowledgement must match the candidate report.")

    verified_at = evidence.get("verified_at")
    if not isinstance(verified_at, str):
        raise SyncPlanError("Verification evidence must include an ISO-8601 verified_at timestamp with timezone.")
    try:
        parsed_time = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SyncPlanError("verified_at must be a valid ISO-8601 timestamp.") from exc
    if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
        raise SyncPlanError("verified_at must include an explicit timezone offset.")

    tests = evidence.get("test_results")
    if not isinstance(tests, list) or not tests:
        raise SyncPlanError("Verification evidence must list at least one successful test result.")
    for index, item in enumerate(tests):
        if not isinstance(item, dict):
            raise SyncPlanError(f"Test result {index + 1} must be a JSON object.")
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            raise SyncPlanError(f"Test result {index + 1} must include a test name.")
        if item.get("passed") is not True:
            raise SyncPlanError(f"Test result {index + 1} has not passed; candidate verification is blocked.")
        if not isinstance(item.get("evidence_ref"), str) or not item["evidence_ref"].strip():
            raise SyncPlanError(f"Test result {index + 1} must include an evidence_ref (log, report, or CI run).")

    _assert_no_custom_git_drivers(candidate)
    head = _git(candidate, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    expected_head = str(candidate_report.get("customized_sha", "")).lower()
    if head != expected_head:
        raise SyncPlanError("Candidate HEAD changed; it no longer matches the original customized SHA.")
    branch = _git(candidate, "branch", "--show-current").stdout.strip()
    if branch != candidate_report.get("candidate_branch"):
        raise SyncPlanError("Candidate branch changed; verification evidence is stale.")
    merge_head = _git(candidate, "rev-parse", "--verify", "MERGE_HEAD^{commit}", check=False)
    if merge_head.returncode != 0:
        raise SyncPlanError("Candidate is no longer in the expected uncommitted merge state.")
    expected_target = str(candidate_report.get("upstream_target_sha", "")).lower()
    if merge_head.stdout.strip().lower() != expected_target:
        raise SyncPlanError("Candidate MERGE_HEAD does not match the selected upstream target.")
    unresolved = _git(candidate, "diff", "--name-only", "--diff-filter=U", "-z").stdout.split("\0")
    if any(unresolved):
        raise SyncPlanError("Candidate contains unresolved merge conflicts.")
    if _git(candidate, "diff", "--quiet", check=False).returncode != 0:
        raise SyncPlanError("Candidate working files changed after merge; discard or recreate the candidate.")
    status_lines = _git(candidate, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
    if any(line.startswith("??") or (len(line) > 1 and line[1] != " ") for line in status_lines):
        raise SyncPlanError("Candidate has untracked or unstaged changes; verification is blocked.")

    tree_sha = _git(candidate, "write-tree").stdout.strip().lower()
    supplied_tree = evidence.get("candidate_tree_sha")
    if not isinstance(supplied_tree, str) or supplied_tree.lower() != tree_sha:
        raise SyncPlanError(
            "candidate_tree_sha does not match the current candidate index tree; evidence is stale or belongs to another candidate."
        )

    return {
        "schema_version": "1.0",
        "operation": "upstream_sync_verification",
        "status": "verification_passed",
        "base_sha": candidate_report.get("base_sha"),
        "upstream_target_sha": expected_target,
        "customized_sha": expected_head,
        "candidate_branch": branch,
        "candidate_tree_sha": tree_sha,
        "reviewer": evidence["reviewer"].strip(),
        "verified_at": parsed_time.isoformat(),
        "verification_source": evidence["verification_source"].strip(),
        "test_results": tests,
        "rights_reviewed": evidence.get("rights_reviewed", False),
        "evidence_authenticated": False,
        "note": (
            "This report validates the supplied evidence structure and binds it to the current candidate tree. "
            "It does not independently authenticate the evidence source, run tests, grant legal approval, "
            "or accept/update the original customized repository."
        ),
    }
