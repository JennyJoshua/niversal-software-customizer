from __future__ import annotations

import subprocess
from pathlib import Path

from customizer.build_evidence import inspect_git_source


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
    assert "dirty" in identity["source_git_identity_error"]


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
