import json
from pathlib import Path

import pytest

from customizer.inspector import InspectionError, inspect_repository, _validate_github_url


def test_detects_common_web_stack(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "fixture-site",
        "version": "1.2.3",
        "dependencies": {"react": "^18.0.0", "vite": "^5.0.0"},
        "scripts": {"build": "vite build"},
    }), encoding="utf-8")
    (tmp_path / "LICENSE").write_text("Example licence text", encoding="utf-8")
    report = inspect_repository(tmp_path)
    assert report["result"] == "supported_candidate"
    assert "react" in report["technology"]["families"]
    assert "vite" in report["technology"]["families"]
    assert report["technology"]["scripts_declared"] == ["build"]
    assert report["inventory"]["license_evidence_files"] == ["LICENSE"]
    assert report["safety"]["executed_source_code"] is False


def test_unknown_directory_is_unsupported(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    report = inspect_repository(tmp_path)
    assert report["result"] == "unsupported"
    assert report["technology"]["families"] == []


def test_ignores_dependency_and_build_directories(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"dependencies":{"vue":"3"}}', encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "private.js").write_text("not inventoried", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("not inventoried", encoding="utf-8")
    report = inspect_repository(tmp_path)
    assert report["inventory"]["files"] == ["package.json"]


@pytest.mark.parametrize("url", [
    "http://github.com/example/project",
    "https://gitlab.com/example/project",
    "https://user:password@github.com/example/project",
    "https://github.com/example/project/tree/main",
    "https://github.com/example/../project",
])
def test_rejects_unsafe_or_unsupported_urls(url: str):
    with pytest.raises(InspectionError):
        _validate_github_url(url)


def test_accepts_public_github_url():
    assert _validate_github_url("https://github.com/example/project") == (
        "https://github.com/example/project.git"
    )


def test_missing_directory_fails(tmp_path: Path):
    with pytest.raises(InspectionError):
        inspect_repository(tmp_path / "missing")


def test_empty_directory_is_unsupported(tmp_path: Path):
    report = inspect_repository(tmp_path)
    assert report["result"] == "unsupported"
    assert report["inventory"]["file_count"] == 0


@pytest.mark.parametrize("revision", ["", "-upload-pack=evil", "../main", "main;echo-bad", "x" * 201])
def test_rejects_unsafe_revision_before_git_call(monkeypatch, tmp_path: Path, revision: str):
    import customizer.inspector as inspector

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Git must not be called for an invalid revision")

    monkeypatch.setattr(inspector, "_run_git", fail_if_called)
    with pytest.raises(InspectionError):
        inspector.clone_pinned_repository(
            "https://github.com/example/project",
            revision,
            tmp_path / "checkout",
        )


def test_local_inspection_does_not_follow_symlink_directories(tmp_path: Path):
    outside = tmp_path.parent / "usc-outside-fixture"
    outside.mkdir(exist_ok=True)
    (outside / "package.json").write_text('{"dependencies":{"react":"18"}}', encoding="utf-8")
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks are not supported in this environment")

    report = inspect_repository(tmp_path)
    assert report["result"] == "unsupported"
    assert "linked/package.json" not in report["inventory"]["files"]
