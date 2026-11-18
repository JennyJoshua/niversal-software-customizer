from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from customizer.sync import SyncPlanError, create_sync_plan


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=path, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def init_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "USC tests")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    return repo, base


def commit_file(repo: Path, name: str, content: str, message: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", "--", name)
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def test_clean_plan_preserves_local_only_customization_and_is_read_only(tmp_path):
    repo, base = init_repo(tmp_path)
    commit_file(repo, "upstream.txt", "upstream update\n", "upstream change")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "reset", "--hard", base)
    commit_file(repo, "custom.txt", "my customization\n", "custom change")
    customized = git(repo, "rev-parse", "HEAD")

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "ready_for_review"
    assert plan["classifications"]["upstream_only"] == ["upstream.txt"]
    assert plan["classifications"]["local_only"] == ["custom.txt"]
    assert plan["merge_conflicts"] == []
    assert git(repo, "rev-parse", "HEAD") == customized
    assert (repo / "custom.txt").read_text(encoding="utf-8") == "my customization\n"
    assert not (repo / "upstream.txt").exists()


def test_overlapping_conflict_blocks_plan_without_changing_working_copy(tmp_path):
    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "base.txt", "upstream version\n", "upstream edit")
    git(repo, "reset", "--hard", base)
    customized = commit_file(repo, "base.txt", "custom version\n", "custom edit")

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "blocked"
    assert plan["merge_conflicts"]
    assert plan["integration_performed"] is False
    assert git(repo, "rev-parse", "HEAD") == customized
    assert (repo / "base.txt").read_text(encoding="utf-8") == "custom version\n"


def test_non_overlapping_edits_in_same_file_can_be_preflighted(tmp_path):
    repo, base = init_repo(tmp_path)
    (repo / "base.txt").write_text("line one\nline two\nline three\n", encoding="utf-8")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-qm", "expand base")
    base = git(repo, "rev-parse", "HEAD")
    target = commit_file(repo, "base.txt", "UPSTREAM\nline two\nline three\n", "upstream top edit")
    git(repo, "reset", "--hard", base)
    commit_file(repo, "base.txt", "line one\nline two\nCUSTOM\n", "custom bottom edit")

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "ready_for_review"
    assert plan["classifications"]["both_changed"] == ["base.txt"]
    assert plan["merge_conflicts"] == []


def test_dirty_working_copy_is_rejected(tmp_path):
    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "change\n", "upstream")
    (repo / "uncommitted.txt").write_text("not committed", encoding="utf-8")

    with pytest.raises(SyncPlanError, match="not clean"):
        create_sync_plan(repo, base, target)


def test_missing_or_non_ancestor_base_is_rejected(tmp_path):
    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "change\n", "upstream")
    with pytest.raises(SyncPlanError, match="full 40- or 64-character"):
        create_sync_plan(repo, "main", target)
    with pytest.raises(SyncPlanError, match="not an ancestor"):
        create_sync_plan(repo, target, base)


def test_rights_file_changes_trigger_human_review_flag(tmp_path):
    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "LICENSE", "Updated terms\n", "upstream licence change")
    git(repo, "reset", "--hard", base)

    plan = create_sync_plan(repo, base, target)

    assert plan["rights_review_required"] is True
    assert plan["rights_review_paths"] == ["LICENSE"]


def test_stale_recorded_base_is_rejected_when_upstream_commit_already_merged(tmp_path):
    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream\n", "upstream")
    commit_file(repo, "custom.txt", "custom\n", "customization after upstream merge")

    with pytest.raises(SyncPlanError, match="not the exact merge base"):
        create_sync_plan(repo, base, target)


def test_shallow_repository_is_rejected(tmp_path):
    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream\n", "upstream")
    (repo / ".git" / "shallow").write_text(base + "\n", encoding="ascii")

    with pytest.raises(SyncPlanError, match="Shallow history"):
        create_sync_plan(repo, base, target)


def test_custom_merge_driver_is_rejected_before_merge_preflight(tmp_path):
    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream\n", "upstream")
    git(repo, "reset", "--hard", base)
    git(repo, "config", "--local", "merge.custom.driver", "touch /tmp/usc-merge-driver-should-not-run")

    with pytest.raises(SyncPlanError, match="custom merge drivers"):
        create_sync_plan(repo, base, target)


def test_external_filter_driver_is_rejected_before_status_check(tmp_path):
    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream\n", "upstream")
    git(repo, "reset", "--hard", base)
    git(repo, "config", "--local", "filter.custom.clean", "touch /tmp/usc-filter-driver-should-not-run")

    with pytest.raises(SyncPlanError, match="external filter drivers"):
        create_sync_plan(repo, base, target)


def test_candidate_integrates_clean_update_in_separate_clone_and_preserves_original(tmp_path):
    from customizer.sync import create_sync_candidate

    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream update\n", "upstream change")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "custom.txt", "custom work\n", "custom change")
    original_head = git(repo, "rev-parse", "HEAD")
    workspace = tmp_path / "candidate"

    result = create_sync_candidate(repo, base, target, workspace, approved=True)

    assert result["status"] == "candidate_ready_for_review"
    assert result["integration_committed"] is False
    assert result["original_repository_unchanged"] is True
    assert (workspace / "upstream.txt").read_text(encoding="utf-8") == "upstream update\n"
    assert (workspace / "custom.txt").read_text(encoding="utf-8") == "custom work\n"
    assert git(repo, "rev-parse", "HEAD") == original_head
    assert not (repo / "upstream.txt").exists()
    assert git(workspace, "rev-parse", "HEAD") == original_head


def test_candidate_creation_is_blocked_when_sync_plan_has_conflicts(tmp_path):
    from customizer.sync import create_sync_candidate

    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "base.txt", "upstream version\n", "upstream edit")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "base.txt", "custom version\n", "custom edit")
    original_head = git(repo, "rev-parse", "HEAD")
    workspace = tmp_path / "candidate"

    with pytest.raises(SyncPlanError, match="plan is blocked by conflicts"):
        create_sync_candidate(repo, base, target, workspace, approved=True)

    assert not workspace.exists()
    assert git(repo, "rev-parse", "HEAD") == original_head
    assert (repo / "base.txt").read_text(encoding="utf-8") == "custom version\n"


def test_candidate_requires_approval_and_rights_review(tmp_path):
    from customizer.sync import create_sync_candidate

    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "LICENSE", "Updated terms\n", "upstream licence change")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    workspace = tmp_path / "candidate"

    with pytest.raises(SyncPlanError, match="explicit --approve"):
        create_sync_candidate(repo, base, target, workspace)

    with pytest.raises(SyncPlanError, match="human rights review"):
        create_sync_candidate(repo, base, target, workspace, approved=True)

    assert not workspace.exists()


def test_candidate_verification_binds_external_evidence_to_current_tree(tmp_path):
    import json
    from customizer.sync import create_sync_candidate
    from customizer.verification import create_sync_verification

    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream update\n", "upstream change")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "custom.txt", "custom work\n", "custom change")
    workspace = tmp_path / "candidate"
    candidate = create_sync_candidate(repo, base, target, workspace, approved=True)
    report_path = tmp_path / "candidate-report.json"
    report_path.write_text(json.dumps(candidate), encoding="utf-8")
    tree_sha = git(workspace, "write-tree")
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps({
        "schema_version": "1.0",
        "verification_status": "passed",
        "reviewer": "Independent reviewer",
        "verified_at": "2026-11-19T10:30:00+10:00",
        "verification_source": "https://github.com/example/project/actions/runs/123",
        "candidate_tree_sha": tree_sha,
        "rights_reviewed": False,
        "test_results": [{
            "name": "upstream and customization regression suite",
            "passed": True,
            "evidence_ref": "https://github.com/example/project/actions/runs/123"
        }]
    }), encoding="utf-8")

    result = create_sync_verification(report_path, evidence_path)

    assert result["status"] == "verification_passed"
    assert result["candidate_tree_sha"] == tree_sha
    assert result["evidence_authenticated"] is False
    assert result["customized_sha"] == candidate["customized_sha"]
    assert git(repo, "rev-parse", "HEAD") == candidate["customized_sha"]


def test_candidate_verification_rejects_changed_tree_and_failed_tests(tmp_path):
    import json
    from customizer.sync import create_sync_candidate
    from customizer.verification import create_sync_verification

    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream update\n", "upstream change")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "custom.txt", "custom work\n", "custom change")
    workspace = tmp_path / "candidate"
    candidate = create_sync_candidate(repo, base, target, workspace, approved=True)
    report_path = tmp_path / "candidate-report.json"
    report_path.write_text(json.dumps(candidate), encoding="utf-8")
    evidence = {
        "schema_version": "1.0",
        "verification_status": "passed",
        "reviewer": "Reviewer",
        "verified_at": "2026-11-19T00:30:00Z",
        "verification_source": "CI run 123",
        "candidate_tree_sha": "0" * 40,
        "rights_reviewed": False,
        "test_results": [{"name": "tests", "passed": True, "evidence_ref": "run 123"}]
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(SyncPlanError, match="candidate_tree_sha"):
        create_sync_verification(report_path, evidence_path)

    evidence["candidate_tree_sha"] = git(workspace, "write-tree")
    evidence["test_results"][0]["passed"] = False
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(SyncPlanError, match="has not passed"):
        create_sync_verification(report_path, evidence)


def test_candidate_verification_requires_timezone_aware_timestamp(tmp_path):
    import json
    from customizer.sync import create_sync_candidate
    from customizer.verification import create_sync_verification

    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream update\n", "upstream change")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "custom.txt", "custom work\n", "custom change")
    workspace = tmp_path / "candidate"
    candidate = create_sync_candidate(repo, base, target, workspace, approved=True)
    report_path = tmp_path / "candidate-report.json"
    report_path.write_text(json.dumps(candidate), encoding="utf-8")
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps({
        "schema_version": "1.0", "verification_status": "passed",
        "reviewer": "Reviewer", "verified_at": "2026-11-19T10:30:00",
        "verification_source": "CI run 123", "candidate_tree_sha": git(workspace, "write-tree"),
        "rights_reviewed": False,
        "test_results": [{"name": "tests", "passed": True, "evidence_ref": "run 123"}]
    }), encoding="utf-8")
    with pytest.raises(SyncPlanError, match="explicit timezone offset"):
        create_sync_verification(report_path, evidence_path)
