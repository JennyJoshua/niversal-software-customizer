"""Build evidence helpers: bounded artifact inventory, log redaction, and schema validation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

_MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
_MAX_ARTIFACT_FILES = 20_000

_LOG_REDACTIONS = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(\b(?:password|token|secret|api[_-]?key|credential)[\w-]*\s*[:=]\s*)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)([\\"']?(?:password|token|secret|api[_-]?key|credential|authorization)[\\"']?\s*:\s*[\\"']?)([^\\"'\s,}]+)"), r"\1[REDACTED]"),
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
