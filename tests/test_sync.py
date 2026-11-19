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
        create_sync_verification(report_path, evidence_path)


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


def _make_verified_candidate(tmp_path):
    import json
    from customizer.sync import create_sync_candidate

    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream update\n", "upstream change")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "custom.txt", "custom work\n", "custom change")
    workspace = tmp_path / "candidate"
    candidate_report = create_sync_candidate(repo, base, target, workspace, approved=True)
    candidate_report_path = tmp_path / "candidate-report.json"
    candidate_report_path.write_text(json.dumps(candidate_report), encoding="utf-8")
    verification_report = {
        "schema_version": "1.0",
        "operation": "upstream_sync_verification",
        "status": "verification_passed",
        "base_sha": base,
        "upstream_target_sha": target,
        "customized_sha": candidate_report["customized_sha"],
        "candidate_branch": candidate_report["candidate_branch"],
        "candidate_tree_sha": git(workspace, "write-tree"),
        "reviewer": "Reviewer",
        "verified_at": "2026-11-19T10:30:00+10:00",
        "verification_source": "CI run 123",
        "test_results": [{"name": "regression tests", "passed": True, "evidence_ref": "CI run 123"}],
        "rights_reviewed": False,
        "evidence_authenticated": False,
    }
    verification_path = tmp_path / "verification-report.json"
    verification_path.write_text(json.dumps(verification_report), encoding="utf-8")
    return repo, base, target, workspace, candidate_report, candidate_report_path, verification_path


def test_acceptance_fast_forwards_original_and_records_baseline_and_provenance(tmp_path):
    import json
    from customizer.acceptance import accept_sync_candidate

    repo, base, target, workspace, candidate, candidate_path, verification_path = _make_verified_candidate(tmp_path)
    original_branch = git(repo, "branch", "--show-current")
    original_head = git(repo, "rev-parse", "HEAD")

    result = accept_sync_candidate(
        repo, candidate_path, verification_path,
        upstream_url="https://github.com/upstream/sample-project",
        approved=True, evidence_reviewed=True,
    )

    assert result["status"] == "accepted"
    assert result["original_branch"] == original_branch
    assert result["previous_customized_sha"] == original_head
    assert git(repo, "rev-parse", "HEAD") == result["provenance_commit_sha"]
    assert (repo / "upstream.txt").read_text(encoding="utf-8") == "upstream update\n"
    assert (repo / "custom.txt").read_text(encoding="utf-8") == "custom work\n"
    baseline = json.loads((repo / ".usc" / "upstream-baseline.json").read_text(encoding="utf-8"))
    assert baseline["last_imported_upstream_sha"] == target
    provenance = json.loads((repo / result["provenance_path"]).read_text(encoding="utf-8"))
    assert provenance["merge_commit_sha"] == result["merge_commit_sha"]
    assert provenance["base_sha"] == base
    parents = git(repo, "rev-list", "--parents", "-n", "1", result["merge_commit_sha"]).split()
    assert parents[1:] == [original_head, target]
    assert git(repo, "status", "--porcelain") == ""


def test_acceptance_blocks_if_original_head_changed_after_candidate_creation(tmp_path):
    from customizer.acceptance import accept_sync_candidate
    from customizer.sync import SyncPlanError

    repo, _, _, _, _, candidate_path, verification_path = _make_verified_candidate(tmp_path)
    changed_head = commit_file(repo, "new-local-change.txt", "later local work\n", "later customization")

    with pytest.raises(SyncPlanError, match="changed after candidate creation"):
        accept_sync_candidate(
            repo, candidate_path, verification_path,
            upstream_url="https://github.com/upstream/sample-project",
            approved=True, evidence_reviewed=True,
        )

    assert git(repo, "rev-parse", "HEAD") == changed_head
    assert (repo / "new-local-change.txt").exists()


def test_acceptance_requires_explicit_approval_and_evidence_review(tmp_path):
    from customizer.acceptance import accept_sync_candidate
    from customizer.sync import SyncPlanError

    repo, _, _, _, _, candidate_path, verification_path = _make_verified_candidate(tmp_path)
    with pytest.raises(SyncPlanError, match="explicit --approve"):
        accept_sync_candidate(
            repo, candidate_path, verification_path,
            upstream_url="https://github.com/upstream/sample-project",
            evidence_reviewed=True,
        )
    with pytest.raises(SyncPlanError, match="--evidence-reviewed"):
        accept_sync_candidate(
            repo, candidate_path, verification_path,
            upstream_url="https://github.com/upstream/sample-project",
            approved=True,
        )
    assert git(repo, "status", "--porcelain") == ""


def test_recovery_finishes_fast_forward_after_provenance_commit(tmp_path, monkeypatch):
    import json
    import customizer.acceptance as acceptance
    from customizer.sync import create_sync_candidate
    from customizer.verification import create_sync_verification

    repo, base = init_repo(tmp_path)
    target = commit_file(repo, "upstream.txt", "upstream update\n", "upstream change")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "custom.txt", "custom work\n", "custom change")
    workspace = tmp_path / "candidate"
    candidate = create_sync_candidate(repo, base, target, workspace, approved=True)
    candidate_report = tmp_path / "candidate-report.json"
    candidate_report.write_text(json.dumps(candidate), encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({
        "schema_version": "1.0", "verification_status": "passed",
        "reviewer": "Reviewer", "verified_at": "2026-11-19T10:30:00+10:00",
        "verification_source": "CI run 123", "candidate_tree_sha": git(workspace, "write-tree"),
        "rights_reviewed": False,
        "test_results": [{"name": "regression", "passed": True, "evidence_ref": "CI run 123"}]
    }), encoding="utf-8")
    verification = tmp_path / "verification.json"
    verification.write_text(json.dumps(create_sync_verification(candidate_report, evidence)), encoding="utf-8")
    original_head = git(repo, "rev-parse", "HEAD")
    original_git = acceptance._git

    def fail_fetch(path, *args, **kwargs):
        if Path(path).resolve() == repo.resolve() and "fetch" in args:
            raise SyncPlanError("simulated interruption before original fast-forward")
        return original_git(path, *args, **kwargs)

    monkeypatch.setattr(acceptance, "_git", fail_fetch)
    with pytest.raises(SyncPlanError, match="simulated interruption"):
        acceptance.accept_sync_candidate(
            repo, candidate_report, verification,
            upstream_url="https://github.com/upstream/sample-project",
            approved=True, evidence_reviewed=True,
        )
    assert git(repo, "rev-parse", "HEAD") == original_head
    assert not (repo / "upstream.txt").exists()

    monkeypatch.setattr(acceptance, "_git", original_git)
    recovered = acceptance.recover_sync_acceptance(repo, candidate_report, approved=True)
    assert recovered["status"] == "recovered"
    assert git(repo, "rev-parse", "HEAD") == recovered["accepted_commit_sha"]
    assert (repo / "upstream.txt").read_text(encoding="utf-8") == "upstream update\n"
    assert (repo / "custom.txt").read_text(encoding="utf-8") == "custom work\n"
    assert git(repo, "status", "--porcelain") == ""
    repeated = acceptance.recover_sync_acceptance(repo, candidate_report, approved=True)
    assert repeated["status"] == "already_applied"


def test_upstream_deletion_of_locally_modified_file_blocks_sync(tmp_path):
    repo, base = init_repo(tmp_path)
    (repo / "tracked.txt").write_text("base file\n", encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-qm", "add tracked file")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "rm", "tracked.txt")
    git(repo, "commit", "-qm", "upstream removes file")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "reset", "--hard", base)
    commit_file(repo, "tracked.txt", "custom local content\n", "customize file")
    plan = create_sync_plan(repo, base, target)
    assert plan["status"] == "blocked"
    assert plan["merge_conflicts"]
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "custom local content\n"


def test_upstream_rename_with_unambiguous_local_edit_preserves_local_content(tmp_path):
    from customizer.sync import create_sync_candidate
    repo, base = init_repo(tmp_path)
    git(repo, "mv", "base.txt", "renamed.txt")
    git(repo, "commit", "-qm", "upstream rename")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "base.txt", "local edit\n", "local edit")
    plan = create_sync_plan(repo, base, target)
    assert plan["status"] == "ready_for_review"
    assert any(change["status"].startswith("R") for change in plan["upstream_changes"])
    candidate = tmp_path / "candidate"
    result = create_sync_candidate(repo, base, target, candidate, approved=True)
    assert result["status"] == "candidate_ready_for_review"
    assert (candidate / "renamed.txt").read_text(encoding="utf-8") == "local edit\n"
    assert (repo / "base.txt").read_text(encoding="utf-8") == "local edit\n"


def test_recovery_rejects_modified_committed_provenance(tmp_path, monkeypatch):
    import customizer.acceptance as acceptance
    from customizer.acceptance import recover_sync_acceptance
    from customizer.sync import SyncPlanError

    repo, base, target, workspace, candidate, candidate_path, verification_path = _make_verified_candidate(tmp_path)
    original_head = git(repo, "rev-parse", "HEAD")
    original_git = acceptance._git

    def fail_fetch(path, *args, **kwargs):
        if Path(path).resolve() == repo.resolve() and "fetch" in args:
            raise SyncPlanError("simulated interruption before original fast-forward")
        return original_git(path, *args, **kwargs)

    monkeypatch.setattr(acceptance, "_git", fail_fetch)
    with pytest.raises(SyncPlanError, match="simulated interruption"):
        acceptance.accept_sync_candidate(
            repo, candidate_path, verification_path,
            upstream_url="https://github.com/upstream/sample-project",
            approved=True, evidence_reviewed=True,
        )
    monkeypatch.setattr(acceptance, "_git", original_git)
    provenance_file = workspace / ".usc" / "provenance" / f"sync-{target}.json"
    provenance_file.write_text('{"tampered": true}\n', encoding="utf-8")

    with pytest.raises(SyncPlanError, match="uncommitted changes"):
        recover_sync_acceptance(repo, candidate_path, approved=True)
    assert git(repo, "rev-parse", "HEAD") == original_head
    assert not (repo / "upstream.txt").exists()


def test_acceptance_rejects_candidate_tampering_after_verification(tmp_path):
    from customizer.acceptance import accept_sync_candidate
    from customizer.sync import SyncPlanError

    repo, _, _, workspace, _, candidate_path, verification_path = _make_verified_candidate(tmp_path)
    original_head = git(repo, "rev-parse", "HEAD")
    (workspace / "custom.txt").write_text("tampered after verification\n", encoding="utf-8")

    with pytest.raises(SyncPlanError, match="working files changed after verification"):
        accept_sync_candidate(
            repo, candidate_path, verification_path,
            upstream_url="https://github.com/upstream/sample-project",
            approved=True, evidence_reviewed=True,
        )

    assert git(repo, "rev-parse", "HEAD") == original_head
    assert not (repo / "upstream.txt").exists()
    assert not (repo / ".usc" / "upstream-baseline.json").exists()


def test_recovery_rejects_baseline_provenance_mismatch(tmp_path, monkeypatch):
    import json
    import customizer.acceptance as acceptance
    from customizer.acceptance import recover_sync_acceptance
    from customizer.sync import SyncPlanError

    repo, _, target, workspace, _, candidate_path, verification_path = _make_verified_candidate(tmp_path)
    original_head = git(repo, "rev-parse", "HEAD")
    original_git = acceptance._git

    def fail_fetch(path, *args, **kwargs):
        if Path(path).resolve() == repo.resolve() and "fetch" in args:
            raise SyncPlanError("simulated interruption before original fast-forward")
        return original_git(path, *args, **kwargs)

    monkeypatch.setattr(acceptance, "_git", fail_fetch)
    with pytest.raises(SyncPlanError, match="simulated interruption"):
        acceptance.accept_sync_candidate(
            repo, candidate_path, verification_path,
            upstream_url="https://github.com/upstream/sample-project",
            approved=True, evidence_reviewed=True,
        )
    monkeypatch.setattr(acceptance, "_git", original_git)

    baseline_path = workspace / ".usc" / "upstream-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["last_imported_upstream_sha"] = "0" * 40
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n", encoding="utf-8")
    git(workspace, "config", "user.name", "USC tests")
    git(workspace, "config", "user.email", "tests@example.invalid")
    git(workspace, "add", ".usc/upstream-baseline.json")
    git(workspace, "commit", "-qm", "tamper with committed upstream baseline")

    with pytest.raises(SyncPlanError, match="baseline does not point to the selected upstream target"):
        recover_sync_acceptance(repo, candidate_path, approved=True)

    assert git(repo, "rev-parse", "HEAD") == original_head
    assert not (repo / "upstream.txt").exists()
    assert target != "0" * 40


def test_recovery_refuses_interruption_before_provenance_commit(tmp_path):
    from customizer.acceptance import recover_sync_acceptance
    from customizer.sync import SyncPlanError

    repo, _, _, workspace, _, candidate_path, _ = _make_verified_candidate(tmp_path)
    original_head = git(repo, "rev-parse", "HEAD")
    git(workspace, "config", "user.name", "USC tests")
    git(workspace, "config", "user.email", "tests@example.invalid")
    git(workspace, "commit", "--no-edit")

    with pytest.raises(SyncPlanError, match="provenance is incomplete"):
        recover_sync_acceptance(repo, candidate_path, approved=True)

    assert git(repo, "rev-parse", "HEAD") == original_head
    assert not (repo / "upstream.txt").exists()
    assert not (repo / ".usc" / "upstream-baseline.json").exists()


def test_upstream_and_custom_renames_of_same_file_are_blocked(tmp_path):
    repo, base = init_repo(tmp_path)
    git(repo, "mv", "base.txt", "upstream-renamed.txt")
    git(repo, "commit", "-qm", "upstream rename")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    git(repo, "mv", "base.txt", "custom-renamed.txt")
    git(repo, "commit", "-qm", "custom rename")
    customized = git(repo, "rev-parse", "HEAD")

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "blocked"
    assert plan["merge_conflicts"]
    assert git(repo, "rev-parse", "HEAD") == customized
    assert (repo / "custom-renamed.txt").read_text(encoding="utf-8") == "base\n"
    assert not (repo / "upstream-renamed.txt").exists()


def test_acceptance_rejects_removed_rights_review_acknowledgement(tmp_path):
    import json
    from customizer.acceptance import accept_sync_candidate
    from customizer.sync import create_sync_candidate
    from customizer.verification import create_sync_verification

    repo, _ = init_repo(tmp_path)
    commit_file(repo, "LICENSE", "Original licence terms\n", "base licence")
    base = git(repo, "rev-parse", "HEAD")
    target = commit_file(repo, "LICENSE", "Updated upstream licence terms\n", "upstream licence update")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "custom.txt", "custom feature\n", "custom feature")

    workspace = tmp_path / "candidate"
    candidate = create_sync_candidate(
        repo, base, target, workspace, approved=True, rights_reviewed=True,
    )
    candidate_path = tmp_path / "candidate-report.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps({
        "schema_version": "1.0",
        "verification_status": "passed",
        "reviewer": "Reviewer",
        "verified_at": "2026-11-20T08:00:00+10:00",
        "verification_source": "CI run 456",
        "candidate_tree_sha": git(workspace, "write-tree"),
        "rights_reviewed": True,
        "test_results": [{
            "name": "candidate regression tests",
            "passed": True,
            "evidence_ref": "CI run 456",
        }],
    }), encoding="utf-8")
    verification = create_sync_verification(candidate_path, evidence_path)
    verification_path = tmp_path / "verification-report.json"
    verification_path.write_text(json.dumps(verification), encoding="utf-8")

    candidate["rights_reviewed"] = False
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    original_head = git(repo, "rev-parse", "HEAD")

    with pytest.raises(SyncPlanError, match="rights acknowledgement"):
        accept_sync_candidate(
            repo, candidate_path, verification_path,
            upstream_url="https://github.com/upstream/sample-project",
            approved=True, evidence_reviewed=True,
        )

    assert git(repo, "rev-parse", "HEAD") == original_head
    assert (repo / "LICENSE").read_text(encoding="utf-8") == "Original licence terms\n"
    assert not (repo / ".usc" / "upstream-baseline.json").exists()


def test_upstream_deletion_of_unmodified_file_is_integrated_without_losing_custom_file(tmp_path):
    from customizer.sync import create_sync_candidate

    repo, _ = init_repo(tmp_path)
    commit_file(repo, "retired.txt", "upstream-owned file\n", "add upstream file")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "rm", "retired.txt")
    git(repo, "commit", "-qm", "upstream removes obsolete file")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "custom.txt", "custom feature\n", "add custom feature")
    original_head = git(repo, "rev-parse", "HEAD")

    plan = create_sync_plan(repo, base, target)
    candidate = tmp_path / "candidate"
    result = create_sync_candidate(repo, base, target, candidate, approved=True)

    assert plan["status"] == "ready_for_review"
    assert result["status"] == "candidate_ready_for_review"
    assert not (candidate / "retired.txt").exists()
    assert (candidate / "custom.txt").read_text(encoding="utf-8") == "custom feature\n"
    assert (repo / "retired.txt").read_text(encoding="utf-8") == "upstream-owned file\n"
    assert git(repo, "rev-parse", "HEAD") == original_head


def test_upstream_deletion_conflicts_with_custom_rename(tmp_path):
    repo, base = init_repo(tmp_path)
    git(repo, "rm", "base.txt")
    git(repo, "commit", "-qm", "upstream deletes base file")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    git(repo, "mv", "base.txt", "custom-renamed.txt")
    git(repo, "commit", "-qm", "custom renames base file")
    customized = git(repo, "rev-parse", "HEAD")

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "blocked"
    assert plan["merge_conflicts"]
    assert git(repo, "rev-parse", "HEAD") == customized
    assert (repo / "custom-renamed.txt").read_text(encoding="utf-8") == "base\n"


def _registry_repo(tmp_path, *, ownership="mixed", protection_mode="require_regression_tests"):
    import json

    repo, _ = init_repo(tmp_path)
    (repo / "feature.py").write_text("base feature\n", encoding="utf-8")
    (repo / ".usc").mkdir()
    (repo / ".usc" / "customizations.json").write_text(json.dumps({
        "schema_version": "1.0",
        "project_id": "sync-test",
        "customizations": [{
            "id": "custom-feature",
            "name": "Custom feature",
            "purpose": "Protect a project-specific feature",
            "category": "feature_workflow",
            "protection_mode": protection_mode,
            "paths": [{"path": "feature.py", "ownership": ownership}],
            "test_ids": ["feature-regression"] if protection_mode == "require_regression_tests" else [],
            "review_note": "Human review required" if protection_mode == "block_for_review" else None,
        }],
    }), encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "add customization registry")
    base = git(repo, "rev-parse", "HEAD")
    return repo, base


def _upstream_target(repo, base, *, delete=False):
    if delete:
        (repo / "feature.py").unlink()
        git(repo, "add", "-u", "feature.py")
    else:
        (repo / "feature.py").write_text("upstream feature update\n", encoding="utf-8")
        git(repo, "add", "feature.py")
    git(repo, "commit", "-qm", "upstream feature change")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "upstream/registry-test", target)
    git(repo, "reset", "--hard", base)
    return target


def test_registry_required_tests_are_reported_in_sync_plan(tmp_path):
    repo, base = _registry_repo(tmp_path)
    target = _upstream_target(repo, base)

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "ready_for_review"
    assert plan["customization_impact"]["status"] == "review_required"
    assert plan["customization_impact"]["affected_customizations"][0]["id"] == "custom-feature"
    assert plan["required_customization_test_ids"] == ["feature-regression"]
    assert plan["integration_performed"] is False


def test_upstream_change_to_custom_only_path_blocks_sync_plan(tmp_path):
    repo, base = _registry_repo(tmp_path, ownership="custom_only", protection_mode="preserve")
    target = _upstream_target(repo, base)

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "blocked"
    assert any("custom-only path" in reason for reason in plan["blocked_reasons"])


def test_upstream_deletion_of_mixed_customization_path_blocks_sync_plan(tmp_path):
    repo, base = _registry_repo(tmp_path)
    target = _upstream_target(repo, base, delete=True)

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "blocked"
    assert any("deletes mixed-ownership path" in reason for reason in plan["blocked_reasons"])


def test_invalid_registry_blocks_sync_plan(tmp_path):
    repo, base = _registry_repo(tmp_path)
    target = _upstream_target(repo, base)
    registry = repo / ".usc" / "customizations.json"
    registry.write_text("{invalid json", encoding="utf-8")
    git(repo, "add", ".usc/customizations.json")
    git(repo, "commit", "-qm", "corrupt registry")
    customized = git(repo, "rev-parse", "HEAD")
    # Keep the corrupt local registry change separate from the upstream history.

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "blocked"
    assert plan["customization_impact"]["registry_status"] == "blocked"


def test_registry_impact_matches_both_sides_of_upstream_rename(tmp_path):
    repo, base = _registry_repo(tmp_path)
    git(repo, "mv", "feature.py", "renamed_feature.py")
    git(repo, "commit", "-qm", "upstream rename feature")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "upstream/rename-test", target)
    git(repo, "reset", "--hard", base)

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "ready_for_review"
    affected = plan["customization_impact"]["affected_customizations"]
    assert affected[0]["changed_paths"] == ["feature.py"]
    assert plan["required_customization_test_ids"] == ["feature-regression"]


def test_unmapped_overlapping_change_is_blocked_when_registry_exists(tmp_path):
    repo, base = _registry_repo(tmp_path)
    target = commit_file(repo, "base.txt", "upstream base change\n", "upstream base edit")
    git(repo, "branch", "upstream/unmapped-overlap", target)
    git(repo, "reset", "--hard", base)
    commit_file(repo, "base.txt", "custom base change\n", "local base edit")

    plan = create_sync_plan(repo, base, target)

    assert plan["status"] == "blocked"
    assert plan["customization_impact"]["unmapped_overlaps"] == ["base.txt"]


def _make_registry_candidate(tmp_path):
    import json
    from customizer.sync import create_sync_candidate

    repo, base = _registry_repo(tmp_path)
    target = _upstream_target(repo, base)
    candidate = create_sync_candidate(repo, base, target, tmp_path / "candidate", approved=True)
    candidate_path = tmp_path / "candidate-report.json"
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    return repo, candidate, candidate_path, tmp_path / "candidate"


def _registry_verification_evidence(candidate, workspace, *, test_results=None):
    return {
        "schema_version": "1.0",
        "verification_status": "passed",
        "reviewer": "Independent reviewer",
        "verified_at": "2026-11-20T10:30:00+10:00",
        "verification_source": "CI run 789",
        "candidate_tree_sha": git(workspace, "write-tree"),
        "rights_reviewed": False,
        "test_results": test_results if test_results is not None else [{
            "test_id": "feature-regression",
            "name": "Feature regression test",
            "passed": True,
            "evidence_ref": "CI run 789",
        }],
    }


def test_registry_verification_requires_every_declared_test_id(tmp_path):
    import json
    from customizer.verification import create_sync_verification

    _, candidate, candidate_path, workspace = _make_registry_candidate(tmp_path)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(_registry_verification_evidence(
        candidate, workspace, test_results=[{
            "test_id": "unrelated-test",
            "name": "Unrelated test",
            "passed": True,
            "evidence_ref": "CI run 789",
        }],
    )), encoding="utf-8")

    with pytest.raises(SyncPlanError, match="Required customization regression test IDs are missing"):
        create_sync_verification(candidate_path, evidence_path)


def test_registry_verification_records_exact_required_test_ids(tmp_path):
    import json
    from customizer.verification import create_sync_verification

    _, candidate, candidate_path, workspace = _make_registry_candidate(tmp_path)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(_registry_verification_evidence(candidate, workspace)), encoding="utf-8")

    result = create_sync_verification(candidate_path, evidence_path)

    assert result["status"] == "verification_passed"
    assert result["required_customization_test_ids"] == ["feature-regression"]
    assert result["verified_customization_test_ids"] == ["feature-regression"]


def test_registry_acceptance_rejects_missing_verified_test_evidence(tmp_path):
    import json
    from customizer.acceptance import accept_sync_candidate
    from customizer.verification import create_sync_verification

    repo, candidate, candidate_path, workspace = _make_registry_candidate(tmp_path)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(_registry_verification_evidence(candidate, workspace)), encoding="utf-8")
    verification = create_sync_verification(candidate_path, evidence_path)
    verification["verified_customization_test_ids"] = []
    verification_path = tmp_path / "verification-report.json"
    verification_path.write_text(json.dumps(verification), encoding="utf-8")
    original_head = git(repo, "rev-parse", "HEAD")

    with pytest.raises(SyncPlanError, match="does not prove every currently required"):
        accept_sync_candidate(
            repo, candidate_path, verification_path,
            upstream_url="https://github.com/upstream/sample-project",
            approved=True, evidence_reviewed=True,
        )

    assert git(repo, "rev-parse", "HEAD") == original_head
    assert not (repo / "upstream.txt").exists()


def test_registry_acceptance_succeeds_only_with_exact_required_test_evidence(tmp_path):
    import json
    from customizer.acceptance import accept_sync_candidate
    from customizer.verification import create_sync_verification

    repo, candidate, candidate_path, workspace = _make_registry_candidate(tmp_path)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(_registry_verification_evidence(candidate, workspace)), encoding="utf-8")
    verification = create_sync_verification(candidate_path, evidence_path)
    verification_path = tmp_path / "verification-report.json"
    verification_path.write_text(json.dumps(verification), encoding="utf-8")

    result = accept_sync_candidate(
        repo, candidate_path, verification_path,
        upstream_url="https://github.com/upstream/sample-project",
        approved=True, evidence_reviewed=True,
    )

    assert result["status"] == "accepted"
    assert (repo / "feature.py").read_text(encoding="utf-8") == "upstream feature update\n"
