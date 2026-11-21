"""Build evidence helpers: bounded artifact inventory, log redaction, and schema validation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

_MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
_MAX_ARTIFACT_FILES = 20_000

_LOG_REDACTIONS = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(\b(?:password|token|secret|api[_-]?key|credential)[\w-]*\s*[:=]\s*)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"""(?i)(["']?(?:password|token|secret|api[_-]?key|credential|authorization)["']?\s*:\s*["']?)([^"'\s,}]+)"""), r"\1[REDACTED]"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
    (re.compile(r"(://)[^/@:\s]+:[^/@\s]+@"), r"\1[REDACTED]@"),
)


def redact_build_logs(value: str) -> str:
    """Best-effort redaction for common credential patterns in captured build output."""
    redacted = value
    for pattern, replacement in _LOG_REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def create_artifact_inventory(output_path: str | Path) -> tuple[list[dict], str]:
    """Return a deterministic SHA-256 inventory of regular files in a build output directory."""
    root = Path(output_path).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Artifact output path must be a directory.")

    entries: list[dict] = []
    total_bytes = 0

    def raise_walk_error(error: OSError) -> None:
        raise error

    for current_text, directories, filenames in os.walk(
        root, topdown=True, followlinks=False, onerror=raise_walk_error,
    ):
        current = Path(current_text)
        for directory in sorted(directories):
            if (current / directory).is_symlink():
                raise ValueError(f"Artifact output contains a symlinked directory: {(current / directory).relative_to(root)}")
        for filename in sorted(filenames):
            path = current / filename
            relative = path.relative_to(root)
            if path.is_symlink():
                raise ValueError(f"Artifact output contains a symlinked file: {relative.as_posix()}")
            before = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError(f"Artifact output contains a non-regular file: {relative.as_posix()}")
            total_bytes += before.st_size
            if total_bytes > _MAX_ARTIFACT_BYTES:
                raise ValueError("Artifact output exceeds the 256 MB inventory limit.")
            if len(entries) >= _MAX_ARTIFACT_FILES:
                raise ValueError("Artifact output exceeds the 20,000-file inventory limit.")

            digest = hashlib.sha256()
            read_bytes = 0
            with path.open("rb") as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    read_bytes += len(chunk)
            after = path.stat(follow_symlinks=False)
            if (
                read_bytes != before.st_size
                or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_ino != before.st_ino
            ):
                raise ValueError(f"Artifact changed while inventory was being created: {relative.as_posix()}")

            entries.append({
                "path": relative.as_posix(),
                "size_bytes": read_bytes,
                "sha256": digest.hexdigest(),
                "mode": stat.S_IMODE(before.st_mode) & 0o777,
            })

    entries.sort(key=lambda item: item["path"])
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return entries, hashlib.sha256(canonical).hexdigest()


@lru_cache(maxsize=1)
def _evidence_validator() -> Draft202012Validator:
    schema_path = Path(__file__).with_name("schemas") / "build-evidence.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_build_evidence(report: dict) -> None:
    """Raise ValueError unless a build evidence report matches the versioned schema."""
    errors = sorted(
        _evidence_validator().iter_errors(report),
        key=lambda error: tuple(str(part) for part in error.path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "report"
        raise ValueError(f"Invalid build evidence at {location}: {first.message}")


def inspect_git_source(source_path: str | Path) -> dict:
    """Return exact Git identity only when the worktree and raw tracked files match HEAD."""
    root = Path(source_path).resolve(strict=True)

    def unavailable(reason: str) -> dict:
        return {
            "source_git_commit_sha": None,
            "source_git_tree_sha": None,
            "source_worktree_clean": False,
            "source_git_identity_error": reason,
        }

    git = "git"

    env = os.environ.copy()
    for key in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    ):
        env.pop(key, None)
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
    })

    def run_git(*args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [git, "-c", f"core.hooksPath={os.devnull}", "-c", "protocol.file.allow=never", "-C", str(root), *args],
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"Git source identity check could not complete: {exc}") from exc

    try:
        top = run_git("rev-parse", "--show-toplevel")
        if top.returncode != 0:
            return unavailable("Source directory is not inside a readable Git working repository.")
        top_path = Path(os.fsdecode(top.stdout.strip())).resolve(strict=True)
        if top_path != root:
            return unavailable("Source directory must be the Git repository root for exact source identity.")

        head = run_git("rev-parse", "--verify", "HEAD^{commit}")
        tree = run_git("rev-parse", "--verify", "HEAD^{tree}")
        if head.returncode != 0 or tree.returncode != 0:
            return unavailable("Git HEAD commit/tree identity could not be resolved.")
        commit_sha = os.fsdecode(head.stdout.strip()).lower()
        tree_sha = os.fsdecode(tree.stdout.strip()).lower()

        tree_listing = run_git("ls-tree", "-r", "--full-tree", "-z", "HEAD")
        index_listing = run_git("ls-files", "--stage", "-z")
        untracked_listing = run_git("ls-files", "--others", "--ignored", "--exclude-standard", "-z")
        if tree_listing.returncode != 0 or index_listing.returncode != 0:
            return unavailable("Git commit tree or index inventory could not be read.")
        if untracked_listing.returncode != 0 or untracked_listing.stdout:
            return unavailable("Ignored or untracked files are present; exact source identity is unavailable.")

        tree_entries: dict[bytes, tuple[bytes, bytes]] = {}
        for record in tree_listing.stdout.split(b"\\x00"):
            if not record:
                continue
            try:
                header, path_bytes = record.split(b"\\t", 1)
                mode, object_type, blob_sha = header.split()
            except ValueError:
                return unavailable("Git returned an invalid commit-tree record.")
            if object_type != b"blob" or mode not in {b"100644", b"100755"}:
                return unavailable("Committed source contains a symlink, submodule, or non-regular entry.")
            tree_entries[path_bytes] = (mode, blob_sha)

        index_entries: dict[bytes, tuple[bytes, bytes]] = {}
        for record in index_listing.stdout.split(b"\\x00"):
            if not record:
                continue
            try:
                header, path_bytes = record.split(b"\\t", 1)
                mode, blob_sha, stage = header.split()
            except ValueError:
                return unavailable("Git returned an invalid tracked-file index record.")
            if stage != b"0" or mode not in {b"100644", b"100755"}:
                return unavailable("Git index contains a conflict stage, symlink, submodule, or non-regular entry.")
            index_entries[path_bytes] = (mode, blob_sha)

        if index_entries != tree_entries:
            return unavailable("Git index does not exactly match the committed HEAD tree.")

        paths = sorted(tree_entries)
        expected_blobs = [tree_entries[path][1] for path in paths]
        for path_bytes in paths:
            path = root / os.fsdecode(path_bytes)
            try:
                metadata = path.stat(follow_symlinks=False)
            except OSError:
                return unavailable("A tracked source file is missing or unreadable.")
            if not stat.S_ISREG(metadata.st_mode):
                return unavailable("A tracked source path is not a regular file.")
            executable = bool(metadata.st_mode & 0o111)
            if executable != (tree_entries[path_bytes][0] == b"100755"):
                return unavailable("A tracked source file's executable mode differs from its Git tree mode.")

        if paths:
            actual_blobs: list[bytes] = []
            for offset in range(0, len(paths), 128):
                batch = [os.fsdecode(item) for item in paths[offset:offset + 128]]
                hashed = run_git("hash-object", "--no-filters", "--", *batch)
                if hashed.returncode != 0:
                    return unavailable("Raw tracked source contents could not be compared with Git blobs.")
                actual_blobs.extend(hashed.stdout.splitlines())
            if actual_blobs != expected_blobs:
                return unavailable("Raw tracked source contents differ from the exact Git tree (including filter/smudge differences).")

        return {
            "source_git_commit_sha": commit_sha,
            "source_git_tree_sha": tree_sha,
            "source_worktree_clean": True,
            "source_git_identity_error": None,
            "_tracked_blob_sha_by_path": {
                os.fsdecode(path): os.fsdecode(blob_sha)
                for path, blob_sha in zip(paths, expected_blobs)
            },
        }
    except RuntimeError as exc:
        return unavailable(str(exc))
