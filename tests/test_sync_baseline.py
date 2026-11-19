from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from customizer.sync import SyncPlanError, resolve_sync_base


UPSTREAM_URL = "https://github.com/upstream/sample-project"


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=path, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def make_repo_with_baseline(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "USC tests")
    git(repo, "config", "user.email", "tests@example.invalid")
    (repo / "source.txt").write_text("source\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "upstream import")
    upstream_sha = git(repo, "rev-parse", "HEAD")

    provenance_dir = repo / ".usc" / "provenance"
    provenance_dir.mkdir(parents=True)
    provenance_path = provenance_dir / f"sync-{upstream_sha}.json"
    provenance = {
        "schema_version": "1.0",
        "operation": "accepted_upstream_sync",
        "upstream_repository_url": UPSTREAM_URL,
        "upstream_target_sha": upstream_sha,
        "merge_commit_sha": upstream_sha,
    }
    provenance_path.write_text(json.dumps(provenance, sort_keys=True) + "\n", encoding="utf-8")
    baseline = {
        "schema_version": "1.0",
        "upstream_repository_url": UPSTREAM_URL,
        "last_imported_upstream_sha": upstream_sha,
        "last_customized_merge_commit_sha": upstream_sha,
        "provenance_path": provenance_path.relative_to(repo).as_posix(),
    }
    baseline_path = repo / ".usc" / "upstream-baseline.json"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n", encoding="utf-8")
    git(repo, "add", ".usc")
    git(repo, "commit", "-qm", "record baseline and provenance")
    return repo, upstream_sha, baseline_path, provenance_path


def test_resolves_committed_baseline_for_expected_upstream(tmp_path):
    repo, upstream_sha, _, _ = make_repo_with_baseline(tmp_path)

    assert resolve_sync_base(repo, upstream_url=UPSTREAM_URL) == upstream_sha


def test_explicit_full_sha_override_does_not_depend_on_baseline(tmp_path):
    repo, upstream_sha, baseline_path, _ = make_repo_with_baseline(tmp_path)
    baseline_path.write_text("{ invalid json", encoding="utf-8")

    assert resolve_sync_base(repo, base_sha=upstream_sha) == upstream_sha


def test_requires_explicit_sha_or_expected_upstream_url(tmp_path):
    repo, _, _, _ = make_repo_with_baseline(tmp_path)
    with pytest.raises(SyncPlanError, match="Supply --base-sha or --upstream-url"):
        resolve_sync_base(repo)


def test_rejects_different_upstream_repository(tmp_path):
    repo, _, _, _ = make_repo_with_baseline(tmp_path)
    with pytest.raises(SyncPlanError, match="different upstream repository"):
        resolve_sync_base(repo, upstream_url="https://github.com/other/project")


def test_rejects_modified_working_baseline_or_provenance(tmp_path):
    repo, _, baseline_path, _ = make_repo_with_baseline(tmp_path)
    baseline_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SyncPlanError, match="differs from the committed"):
        resolve_sync_base(repo, upstream_url=UPSTREAM_URL)


def test_rejects_missing_or_tampered_provenance(tmp_path):
    repo, _, _, provenance_path = make_repo_with_baseline(tmp_path)
    provenance_path.write_text('{"tampered": true}\n', encoding="utf-8")
    with pytest.raises(SyncPlanError, match="differs from the committed"):
        resolve_sync_base(repo, upstream_url=UPSTREAM_URL)


def test_rejects_baseline_when_merge_commit_is_not_in_current_history(tmp_path):
    repo, upstream_sha, baseline_path, _ = make_repo_with_baseline(tmp_path)
    tree_sha = git(repo, "write-tree")
    unrelated_sha = git(repo, "-c", "user.name=USC tests", "-c", "user.email=tests@example.invalid", "commit-tree", tree_sha, "-m", "unrelated history")
    git(repo, "branch", "unrelated", unrelated_sha)
    git(repo, "checkout", "unrelated")
    with pytest.raises(SyncPlanError, match="not an ancestor"):
        resolve_sync_base(repo, upstream_url=UPSTREAM_URL)


def test_rejects_symlinked_baseline(tmp_path):
    repo, upstream_sha, baseline_path, _ = make_repo_with_baseline(tmp_path)
    contents = baseline_path.read_text(encoding="utf-8")
    baseline_path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text(contents, encoding="utf-8")
    baseline_path.symlink_to(outside)
    with pytest.raises(SyncPlanError, match="missing or unsafe"):
        resolve_sync_base(repo, upstream_url=UPSTREAM_URL)
