from __future__ import annotations

import subprocess

import pytest
from pathlib import Path

from customizer.build_evidence import inspect_git_source
from customizer.build_runner import _stage_source_snapshot


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _committed_repo(root: Path) -> None:
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "USC Fixture")
    _git(root, "config", "user.email", "usc-fixture@example.test")
    (root / "app.py").write_text("print('fixture')\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored.tmp\n", encoding="utf-8")
    _git(root, "add", "app.py", ".gitignore")
    _git(root, "commit", "-qm", "fixture baseline")


def test_inspect_git_source_proves_clean_commit_tree_and_raw_blob_identity(tmp_path):
    root = tmp_path / "repo"
    _committed_repo(root)

    identity = inspect_git_source(root)

    assert identity["source_worktree_clean"] is True
    assert len(identity["source_git_commit_sha"]) in {40, 64}
    assert len(identity["source_git_tree_sha"]) in {40, 64}
    assert identity["source_git_identity_error"] is None


def test_inspect_git_source_rejects_modified_tracked_file(tmp_path):
    root = tmp_path / "repo"
    _committed_repo(root)
    (root / "app.py").write_text("print('changed')\n", encoding="utf-8")

    identity = inspect_git_source(root)

    assert identity["source_worktree_clean"] is False
    assert identity["source_git_commit_sha"] is None
    assert "Raw tracked source contents differ" in identity["source_git_identity_error"]


def test_inspect_git_source_rejects_ignored_untracked_files(tmp_path):
    root = tmp_path / "repo"
    _committed_repo(root)
    (root / "ignored.tmp").write_text("not in the Git tree", encoding="utf-8")

    identity = inspect_git_source(root)

    assert identity["source_worktree_clean"] is False
    assert identity["source_git_tree_sha"] is None
    assert "Ignored or untracked" in identity["source_git_identity_error"]


def test_inspect_git_source_rejects_non_repository_root(tmp_path):
    parent = tmp_path / "repo"
    _committed_repo(parent)
    nested = parent / "nested"
    nested.mkdir()

    identity = inspect_git_source(nested)

    assert identity["source_worktree_clean"] is False
    assert "repository root" in identity["source_git_identity_error"]



def test_staged_snapshot_is_bound_to_inspected_git_blobs(tmp_path):
    root = tmp_path / "repo"
    _committed_repo(root)
    identity = inspect_git_source(root)
    assert identity["source_worktree_clean"] is True

    snapshot = tmp_path / "snapshot"
    _stage_source_snapshot(
        root,
        snapshot,
        expected_git_blobs=identity["_tracked_blob_sha_by_path"],
    )
    assert (snapshot / "app.py").read_text(encoding="utf-8") == "print('fixture')\n"


def test_staged_snapshot_rejects_file_changed_after_git_identity_check(tmp_path):
    root = tmp_path / "repo"
    _committed_repo(root)
    identity = inspect_git_source(root)
    (root / "app.py").write_text("tampered after identity check\\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exact Git tree blob"):
        _stage_source_snapshot(
            root,
            tmp_path / "snapshot",
            expected_git_blobs=identity["_tracked_blob_sha_by_path"],
        )


def test_staged_snapshot_rejects_new_untracked_file_after_identity_check(tmp_path):
    root = tmp_path / "repo"
    _committed_repo(root)
    identity = inspect_git_source(root)
    (root / "untracked.py").write_text("not in HEAD\\n", encoding="utf-8")

    with pytest.raises(ValueError, match="outside the inspected Git tree"):
        _stage_source_snapshot(
            root,
            tmp_path / "snapshot",
            expected_git_blobs=identity["_tracked_blob_sha_by_path"],
        )



def test_staged_snapshot_normalizes_non_executable_modes_to_git_mode(tmp_path):
    root = tmp_path / "repo"
    _committed_repo(root)
    (root / "app.py").chmod(0o664)
    identity = inspect_git_source(root)
    assert identity["source_worktree_clean"] is True

    snapshot = tmp_path / "snapshot"
    _stage_source_snapshot(
        root,
        snapshot,
        expected_git_blobs=identity["_tracked_blob_sha_by_path"],
    )
    assert (snapshot / "app.py").stat().st_mode & 0o777 == 0o644
