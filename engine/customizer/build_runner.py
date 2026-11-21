"""Fail-closed disposable build execution using a pre-provisioned Docker image."""
from __future__ import annotations

import os
import re
import selectors
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Sequence

_PINNED_IMAGE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_SHELLS = {"sh", "bash", "dash", "zsh", "fish", "cmd", "powershell", "pwsh"}
_MAX_TIMEOUT = 3600
_MAX_LOG_BYTES = 1_048_576


def _directory(path: str | Path, label: str) -> Path:
    supplied = Path(path).expanduser()
    if supplied.is_symlink():
        raise ValueError(f"{label} must not be a symlink.")
    resolved = supplied.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be an existing directory.")
    return resolved


def _validate_request(
    source_path: str | Path,
    output_path: str | Path,
    image: str,
    command: Sequence[str],
    timeout_seconds: int,
    max_log_bytes: int,
) -> tuple[Path, Path, list[str]]:
    if not isinstance(image, str) or not _PINNED_IMAGE.fullmatch(image):
        raise ValueError("Build image must be pinned by an immutable sha256 digest.")
    if not isinstance(command, (list, tuple)) or not 1 <= len(command) <= 32:
        raise ValueError("Command must be a list of 1 to 32 arguments.")
    args = list(command)
    if any(not isinstance(arg, str) or not arg or "\x00" in arg or len(arg) > 4096 for arg in args):
        raise ValueError("Command arguments must be non-empty strings without NUL bytes and at most 4096 characters.")
    executable = Path(args[0]).name.lower()
    if executable in _SHELLS:
        raise ValueError("Shell interpreters are not accepted; provide an executable and arguments directly.")
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= _MAX_TIMEOUT:
        raise ValueError(f"timeout_seconds must be between 1 and {_MAX_TIMEOUT}.")
    if not isinstance(max_log_bytes, int) or isinstance(max_log_bytes, bool) or not 1024 <= max_log_bytes <= _MAX_LOG_BYTES:
        raise ValueError(f"max_log_bytes must be between 1024 and {_MAX_LOG_BYTES}.")

    source = _directory(source_path, "Source")
    output = _directory(output_path, "Output")
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Output directory must be separate from, and not an ancestor or descendant of, the source directory.")
    if "," in str(source) or "," in str(output):
        raise ValueError("Source and output paths must not contain commas.")
    if not hasattr(os, "getuid") or not hasattr(os, "getgid") or os.getuid() == 0:
        raise ValueError("The host runner must execute as a non-root user.")
    if not os.access(output, os.W_OK | os.X_OK):
        raise ValueError("Output directory must be writable by the non-root host runner.")
    if any(output.iterdir()):
        raise ValueError("Output directory must be empty before execution.")
    return source, output, args


def _labelled_container_ids(docker: str, label: str) -> list[str] | None:
    try:
        listing = subprocess.run(
            [docker, "ps", "-aq", "--filter", f"label={label}"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if listing.returncode != 0:
            return None
        return listing.stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        return None


def _export_container_output(docker: str, label: str, output: Path) -> bool:
    container_ids = _labelled_container_ids(docker, label)
    if container_ids is None or len(container_ids) != 1:
        return False
    try:
        copied = subprocess.run(
            [docker, "cp", f"{container_ids[0]}:/out/.", str(output)],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if copied.returncode != 0:
            return False
        for root, directories, files in os.walk(output, followlinks=False):
            for name in directories + files:
                if (Path(root) / name).is_symlink():
                    return False
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _cleanup_labelled_containers(docker: str, label: str) -> bool:
    container_ids = _labelled_container_ids(docker, label)
    if container_ids is None:
        return False
    for container_id in container_ids:
        try:
            removed = subprocess.run(
                [docker, "rm", "-f", container_id],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if removed.returncode != 0:
                return False
        except (OSError, subprocess.TimeoutExpired):
            return False
    remaining = _labelled_container_ids(docker, label)
    return remaining == []


def run_isolated_build(
    source_path: str | Path,
    output_path: str | Path,
    *,
    image: str,
    command: Sequence[str],
    approved: bool = False,
    timeout_seconds: int = 300,
    max_log_bytes: int = 262_144,
) -> dict:
    """Run an explicitly approved argv command in a network-disabled, read-only container.

    The image must already exist locally and be pinned by digest. No host environment
    variables, credentials, sockets, or additional mounts are passed to the container.
    """
    if approved is not True:
        return {
            "operation": "isolated_build",
            "status": "blocked_approval_required",
            "executed": False,
            "note": "Execution requires explicit approval of this exact command and image.",
        }
    try:
        source, output, args = _validate_request(
            source_path, output_path, image, command, timeout_seconds, max_log_bytes,
        )
    except (OSError, ValueError) as exc:
        return {
            "operation": "isolated_build",
            "status": "blocked_invalid_request",
            "executed": False,
            "errors": [str(exc)],
        }

    docker = shutil.which("docker")
    if not docker:
        return {
            "operation": "isolated_build",
            "status": "blocked_isolation_unavailable",
            "executed": False,
            "errors": ["Docker CLI is unavailable; no fallback execution is permitted."],
        }
    try:
        probe = subprocess.run(
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        probe = None
    if probe is None or probe.returncode != 0:
        return {
            "operation": "isolated_build",
            "status": "blocked_isolation_unavailable",
            "executed": False,
            "errors": ["Docker daemon is unavailable; no fallback execution is permitted."],
        }

    run_label = f"com.usc.build-run={uuid.uuid4().hex}"
    logs = bytearray()
    status = "failed"
    exit_code = None
    cleanup_ok = True
    artifact_exported = False
    docker_argv = [
        docker, "run", "--pull=never",
        "--network=none", "--read-only",
        f"--user={os.getuid()}:{os.getgid()}", "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=64", "--memory=512m", "--cpus=1.0",
        f"--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m,uid={os.getuid()},gid={os.getgid()},mode=0700",
        f"--tmpfs=/out:rw,noexec,nosuid,nodev,size=256m,uid={os.getuid()},gid={os.getgid()},mode=0700",
        f"--label={run_label}",
        f"--mount=type=bind,src={source},dst=/src,readonly",
        "--workdir=/src",
        "--env=HOME=/tmp", "--env=TMPDIR=/tmp",
        "--env=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        image, *args,
    ]

    process = None
    try:
        process = subprocess.Popen(
            docker_argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
        assert process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout_seconds
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = "timed_out"
                    process.kill()
                    break
                for key, _ in selector.select(timeout=min(0.1, remaining)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = max_log_bytes - len(logs)
                    if len(chunk) > available:
                        logs.extend(chunk[:available])
                        status = "output_limit_exceeded"
                        process.kill()
                        break
                    logs.extend(chunk)
                if status in {"timed_out", "output_limit_exceeded"}:
                    break
            exit_code = process.wait(timeout=5)
            if status not in {"timed_out", "output_limit_exceeded"}:
                if exit_code == 125:
                    status = "blocked_isolation_unavailable"
                else:
                    status = "passed" if exit_code == 0 else "failed"
                    artifact_exported = _export_container_output(docker, run_label, output)
                    if not artifact_exported:
                        status = "artifact_export_failed"
        finally:
            selector.close()
            process.stdout.close()
    except (OSError, subprocess.TimeoutExpired) as exc:
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        status = "blocked_isolation_unavailable"
        logs.extend(str(exc).encode("utf-8", errors="replace")[:max_log_bytes])
    finally:
        cleanup_ok = _cleanup_labelled_containers(docker, run_label)

    if not cleanup_ok:
        status = "blocked_cleanup_failed"
    return {
        "operation": "isolated_build",
        "status": status,
        "executed": status not in {"blocked_isolation_unavailable"},
        "exit_code": exit_code,
        "image": image,
        "command_executable": args[0],
        "timeout_seconds": timeout_seconds,
        "log_bytes": len(logs),
        "log_truncated": status == "output_limit_exceeded",
        "logs": logs.decode("utf-8", errors="replace"),
        "source_read_only": True,
        "output_path": str(output),
        "artifact_exported": artifact_exported,
        "network_disabled": True,
        "container_cleanup_confirmed": cleanup_ok,
        "note": "No host environment variables or credentials were forwarded. The image was not pulled; it had to be pre-provisioned locally.",
    }
