from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from customizer.sync import SyncPlanError, create_sync_candidate
from customizer.verification_snapshot import create_sync_verification_snapshot


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
    assert "git push" in snapshot["push_command"]


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
    with pytest.raises(SyncPlanError, match="unstaged file changes"):
        create_sync_verification_snapshot(repo, report_path, push_url="https://github.com/acme/fork.git")
