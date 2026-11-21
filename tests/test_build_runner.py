from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from customizer.build_runner import run_isolated_build


IMAGE = "python:3.12-slim@sha256:" + "a" * 64


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    return source, output


def test_build_requires_explicit_approval_and_does_not_probe_docker(tmp_path, monkeypatch):
    source, output = _paths(tmp_path)

    def unexpected_which(_name):
        raise AssertionError("Docker must not be inspected before approval.")

    monkeypatch.setattr("customizer.build_runner.shutil.which", unexpected_which)
    report = run_isolated_build(
        source, output, image=IMAGE, command=["python", "-m", "pytest"],
    )

    assert report["status"] == "blocked_approval_required"
    assert report["executed"] is False


@pytest.mark.parametrize(
    ("image", "command", "timeout"),
    [
        ("python:latest", ["python", "-m", "pytest"], 30),
        (IMAGE, ["sh", "-c", "echo unsafe"], 30),
        (IMAGE, ["python", "-m", "pytest"], 0),
    ],
)
def test_invalid_execution_profiles_are_blocked(tmp_path, image, command, timeout):
    source, output = _paths(tmp_path)
    report = run_isolated_build(
        source, output, image=image, command=command, approved=True,
        timeout_seconds=timeout,
    )
    assert report["status"] == "blocked_invalid_request"
    assert report["executed"] is False


def test_output_directory_cannot_contain_or_enclose_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    report = run_isolated_build(
        source, tmp_path, image=IMAGE, command=["python", "-m", "pytest"],
        approved=True,
    )
    assert report["status"] == "blocked_invalid_request"
    assert "ancestor or descendant" in report["errors"][0]


def test_runner_fails_closed_when_docker_is_unavailable(tmp_path, monkeypatch):
    source, output = _paths(tmp_path)
    monkeypatch.setattr("customizer.build_runner.shutil.which", lambda _name: None)
    report = run_isolated_build(
        source, output, image=IMAGE, command=["python", "-m", "pytest"],
        approved=True,
    )
    assert report["status"] == "blocked_isolation_unavailable"
    assert report["executed"] is False


def test_runner_uses_restricted_container_and_reports_success(tmp_path, monkeypatch):
    source, output = _paths(tmp_path)
    captured = {}

    class FakeProcess:
        def __init__(self, argv, **kwargs):
            captured["argv"] = argv
            read_fd, write_fd = os.pipe()
            os.write(write_fd, b"fixture tests passed\\n")
            os.close(write_fd)
            self.stdout = os.fdopen(read_fd, "rb")
            self.returncode = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    def fake_run(argv, **kwargs):
        if argv[1] == "info":
            return subprocess.CompletedProcess(argv, 0, stdout="27.0", stderr="")
        if argv[1:3] == ["ps", "-aq"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected host command: {argv}")

    monkeypatch.setattr("customizer.build_runner.shutil.which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr("customizer.build_runner.subprocess.run", fake_run)
    monkeypatch.setattr("customizer.build_runner.subprocess.Popen", FakeProcess)

    report = run_isolated_build(
        source, output, image=IMAGE, command=["python", "-m", "pytest"],
        approved=True,
    )

    argv = captured["argv"]
    assert "--network=none" in argv
    assert "--read-only" in argv
    assert "--cap-drop=ALL" in argv
    assert "--security-opt=no-new-privileges:true" in argv
    assert "--pull=never" in argv
    assert f"--mount=type=bind,src={source.resolve()},dst=/src,readonly" in argv
    assert f"--mount=type=bind,src={output.resolve()},dst=/out" in argv
    assert "--env=HOME=/tmp" in argv
    assert report["status"] == "passed"
    assert report["source_read_only"] is True
    assert report["network_disabled"] is True
    assert report["container_cleanup_confirmed"] is True
    assert report["logs"] == "fixture tests passed\\n"


def test_runner_marks_container_cleanup_failure_as_blocked(tmp_path, monkeypatch):
    source, output = _paths(tmp_path)

    class FakeProcess:
        def __init__(self, _argv, **_kwargs):
            read_fd, write_fd = os.pipe()
            os.close(write_fd)
            self.stdout = os.fdopen(read_fd, "rb")
            self.returncode = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    def fake_run(argv, **kwargs):
        if argv[1] == "info":
            return subprocess.CompletedProcess(argv, 0, stdout="27.0", stderr="")
        if argv[1:3] == ["ps", "-aq"]:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="daemon error")
        raise AssertionError(f"Unexpected host command: {argv}")

    monkeypatch.setattr("customizer.build_runner.shutil.which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr("customizer.build_runner.subprocess.run", fake_run)
    monkeypatch.setattr("customizer.build_runner.subprocess.Popen", FakeProcess)

    report = run_isolated_build(
        source, output, image=IMAGE, command=["python", "-m", "pytest"],
        approved=True,
    )
    assert report["status"] == "blocked_cleanup_failed"
    assert report["container_cleanup_confirmed"] is False
