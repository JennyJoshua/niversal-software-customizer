from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from customizer.sync import SyncPlanError, create_sync_candidate
from customizer.verification_snapshot import create_sync_verification_snapshot

class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload



def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=path, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def init_repo(tmp_path: Path):
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "USC tests")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "upstream.txt").write_text("upstream\n", encoding="utf-8")
    git(repo, "add", "upstream.txt")
    git(repo, "commit", "-qm", "upstream update")
    target = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "upstream/test", target)
    git(repo, "reset", "--hard", base)
    (repo / "custom.txt").write_text("custom\n", encoding="utf-8")
    git(repo, "add", "custom.txt")
    git(repo, "commit", "-qm", "custom change")
    return repo, base, target


def make_candidate(tmp_path):
    repo, base, target = init_repo(tmp_path)
    candidate_path = tmp_path / "candidate"
    report = create_sync_candidate(repo, base, target, candidate_path, approved=True)
    report_path = tmp_path / "candidate-report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return repo, candidate_path, report, report_path, target


def test_snapshot_creates_exact_tree_commit_without_changing_product_or_candidate(tmp_path):
    repo, candidate, candidate_report, report_path, target = make_candidate(tmp_path)
    original_head = git(repo, "rev-parse", "HEAD")
    candidate_head = git(candidate, "rev-parse", "HEAD")
    candidate_branch = git(candidate, "branch", "--show-current")
    merge_head = git(candidate, "rev-parse", "MERGE_HEAD")
    status = git(candidate, "status", "--porcelain=v1", "--untracked-files=all")
    tree_sha = git(candidate, "write-tree")

    snapshot = create_sync_verification_snapshot(
        repo, report_path, push_url="https://github.com/acme/fork.git"
    )

    assert snapshot["status"] == "snapshot_ready_to_publish"
    assert snapshot["repository"] == "acme/fork"
    assert snapshot["candidate_tree_sha"] == tree_sha
    assert snapshot["upstream_target_sha"] == target
    assert git(candidate, "rev-parse", f"{snapshot['snapshot_commit_sha']}^{{tree}}") == tree_sha
    assert git(candidate, "rev-list", "--parents", "-n", "1", snapshot["snapshot_commit_sha"]).split() == [
        snapshot["snapshot_commit_sha"], original_head
    ]
    assert git(candidate, "rev-parse", f"refs/heads/{snapshot['snapshot_branch']}") == snapshot["snapshot_commit_sha"]
    assert git(repo, "rev-parse", "HEAD") == original_head
    assert git(candidate, "rev-parse", "HEAD") == candidate_head
    assert git(candidate, "branch", "--show-current") == candidate_branch
    assert git(candidate, "rev-parse", "MERGE_HEAD") == merge_head
    assert git(candidate, "status", "--porcelain=v1", "--untracked-files=all") == status
    assert snapshot["push_performed"] is False
    assert snapshot["push_command"].split()[0] == "git"
    assert " push " in snapshot["push_command"]


@pytest.mark.parametrize(
    "push_url",
    [
        "http://github.com/acme/fork.git",
        "https://evil.example/acme/fork.git",
        "https://user@github.com/acme/fork.git",
        "https://github.com/acme/fork.git?token=secret",
        "https://github.com/acme",
    ],
)
def test_snapshot_rejects_unsafe_push_urls(tmp_path, push_url):
    repo, candidate, report, report_path, _ = make_candidate(tmp_path)
    with pytest.raises(SyncPlanError, match="canonical HTTPS GitHub"):
        create_sync_verification_snapshot(repo, report_path, push_url=push_url)


def test_snapshot_rejects_changed_original_branch(tmp_path):
    repo, candidate, report, report_path, _ = make_candidate(tmp_path)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(SyncPlanError, match="Original customized branch"):
        create_sync_verification_snapshot(repo, report_path, push_url="https://github.com/acme/fork.git")


def test_snapshot_rejects_candidate_with_unstaged_changes(tmp_path):
    repo, candidate, report, report_path, _ = make_candidate(tmp_path)
    (candidate / "tampered.txt").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(SyncPlanError, match="untracked or unstaged changes"):
        create_sync_verification_snapshot(repo, report_path, push_url="https://github.com/acme/fork.git")


def test_snapshot_creation_is_idempotent(tmp_path):
    repo, candidate, report, report_path, _ = make_candidate(tmp_path)
    first = create_sync_verification_snapshot(
        repo, report_path, push_url="https://github.com/acme/fork.git"
    )
    second = create_sync_verification_snapshot(
        repo, report_path, push_url="https://github.com/acme/fork.git"
    )
    assert second["snapshot_commit_sha"] == first["snapshot_commit_sha"]
    assert second["snapshot_branch"] == first["snapshot_branch"]


def test_authenticated_verification_binds_run_to_local_snapshot_and_candidate(monkeypatch, tmp_path):
    import customizer.github_actions as github_actions
    from urllib.parse import urlparse
    from customizer.verification import create_sync_verification

    repo, candidate, candidate_report, candidate_path, _ = make_candidate(tmp_path)
    snapshot = create_sync_verification_snapshot(
        repo, candidate_path, push_url="https://github.com/acme/fork.git"
    )
    snapshot_path = tmp_path / "snapshot-report.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    run_url = "https://github.com/acme/fork/actions/runs/12345"
    workflow_path = ".github/workflows/ci.yml"
    workflow_blob = "c" * 40
    payloads = {
        "/actions/runs/12345": {
            "id": 12345,
            "repository": {"full_name": "acme/fork"},
            "status": "completed",
            "conclusion": "success",
            "event": "push",
            "head_branch": snapshot["snapshot_branch"],
            "head_sha": snapshot["snapshot_commit_sha"],
            "workflow_id": 42,
            "path": workflow_path,
        },
        f"/git/commits/{snapshot['snapshot_commit_sha']}": {
            "tree": {"sha": snapshot["candidate_tree_sha"]},
            "parents": [{"sha": snapshot["parent_sha"]}],
        },
        f"/contents/{workflow_path}?ref={snapshot['snapshot_commit_sha']}": {"sha": workflow_blob},
        "/actions/runs/12345/jobs?per_page=100": {
            "total_count": 1,
            "jobs": [{"status": "completed", "conclusion": "success"}],
        },
    }

    def fake_urlopen(request, timeout):
        parsed = urlparse(request.full_url)
        key = parsed.path.removeprefix("/repos/acme/fork")
        if parsed.query:
            key += "?" + parsed.query
        return FakeResponse(payloads[key])

    monkeypatch.setattr(github_actions, "urlopen", fake_urlopen)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps({
        "schema_version": "1.0",
        "verification_status": "passed",
        "reviewer": "Test reviewer",
        "verified_at": "2026-11-19T10:30:00+10:00",
        "verification_source": run_url,
        "candidate_tree_sha": snapshot["candidate_tree_sha"],
        "rights_reviewed": False,
        "test_results": [{"name": "unit tests", "passed": True, "evidence_ref": run_url}],
    }), encoding="utf-8")

    verified = create_sync_verification(
        candidate_path, evidence_path,
        github_run_url=run_url,
        github_repository="acme/fork",
        workflow_id=42,
        workflow_path=workflow_path,
        workflow_blob_sha=workflow_blob,
        snapshot_report_path=snapshot_path,
    )
    assert verified["evidence_authenticated"] is True
    assert verified["github_actions_evidence"]["head_sha"] == snapshot["snapshot_commit_sha"]
    assert verified["candidate_tree_sha"] == snapshot["candidate_tree_sha"]
