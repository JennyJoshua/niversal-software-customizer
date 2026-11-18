"""Read-only repository inspection helpers.

This module inventories metadata and paths only. It never imports or executes
code from the inspected repository.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "dist", "build",
    ".next", ".nuxt", ".venv", "venv", "__pycache__", "coverage",
}
MAX_FILES = 5000
MAX_MANIFEST_BYTES = 1_000_000

MANIFESTS = {
    "package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json",
    "pyproject.toml", "requirements.txt", "Pipfile", "Cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "build.gradle.kts", "composer.json",
    "Gemfile", "mix.exs",
}
LICENSE_NAMES = {
    "license", "licence", "copying", "notice", "authors", "copyright",
    "license.md", "licence.md", "copying.md", "notice.md", "authors.md",
    "license.txt", "licence.txt", "copying.txt", "notice.txt",
}


class InspectionError(ValueError):
    """Raised when source input cannot be inspected safely."""


def _run_git(args: list[str], *, cwd: Path | None = None, timeout: int = 60) -> str:
    env = os.environ.copy()
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    })
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InspectionError(f"Git operation failed: {exc}") from exc
    if result.returncode:
        message = result.stderr.strip() or "unknown Git error"
        raise InspectionError(f"Git operation failed: {message[:500]}")
    return result.stdout.strip()


def _validate_github_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise InspectionError("Only public HTTPS GitHub repository URLs are supported.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise InspectionError("Repository URL must not contain credentials, query strings, or fragments.")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2 or any(part in {".", ".."} for part in parts):
        raise InspectionError("Use a GitHub repository URL in the form https://github.com/owner/repository.")
    owner, name = parts
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name.removesuffix(".git")):
        raise InspectionError("Repository URL contains an unsupported owner or repository name.")
    return f"https://github.com/{owner}/{name.removesuffix('.git')}.git"


def clone_pinned_repository(url: str, revision: str, destination: Path) -> str:
    """Fetch and checkout a requested revision without running repository scripts."""
    safe_url = _validate_github_url(url)
    revision_parts = revision.split("/") if isinstance(revision, str) else []
    if (
        not revision
        or revision.startswith("-")
        or revision.startswith("/")
        or revision.endswith("/")
        or "//" in revision
        or any(part in {".", ".."} for part in revision_parts)
        or len(revision) > 200
        or not re.fullmatch(r"[A-Za-z0-9._/-]+", revision)
    ):
        raise InspectionError("Revision must be a valid branch, tag, or commit identifier without option-like syntax or path traversal.")
    _run_git(["-c", "core.hooksPath=/dev/null", "clone", "--no-checkout",
              "--no-recurse-submodules", "--filter=blob:none", safe_url, str(destination)], timeout=180)
    _run_git(["-c", "core.hooksPath=/dev/null", "fetch", "--depth=1", "origin", revision],
             cwd=destination, timeout=180)
    commit = _run_git(["rev-parse", "--verify", "FETCH_HEAD^{commit}"], cwd=destination)
    _run_git(["-c", "core.hooksPath=/dev/null", "checkout", "--detach", commit],
             cwd=destination, timeout=120)
    return commit


def _git_commit(root: Path) -> str | None:
    try:
        return _run_git(["rev-parse", "--verify", "HEAD^{commit}"], cwd=root, timeout=10)
    except InspectionError:
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _walk(root: Path) -> tuple[list[str], list[str], bool]:
    files: list[str] = []
    licenses: list[str] = []
    truncated = False
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            name for name in dirs
            if name not in IGNORED_DIRS and not (Path(current) / name).is_symlink()
        )
        for name in sorted(names):
            path = Path(current) / name
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            files.append(relative)
            if name.lower() in LICENSE_NAMES or name.lower().startswith(("license-", "licence-")):
                licenses.append(relative)
            if len(files) >= MAX_FILES:
                truncated = True
                return files, licenses, truncated
    return files, licenses, truncated


def _technology_signals(root: Path, files: list[str]) -> dict[str, Any]:
    file_set = set(files)
    signals: list[str] = []
    families: list[str] = []
    package = _read_json(root / "package.json") if "package.json" in file_set else None
    deps: dict[str, str] = {}
    if package:
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            value = package.get(section, {})
            if isinstance(value, dict):
                deps.update({str(k): str(v) for k, v in value.items()})
        signals.append("package.json")
        if "next" in deps or any(p.startswith("next.config.") for p in files):
            families.append("nextjs")
            signals.append("Next.js dependency or config")
        if "react" in deps:
            families.append("react")
            signals.append("React dependency")
        if "vue" in deps:
            families.append("vue")
            signals.append("Vue dependency")
        if "@angular/core" in deps or "angular.json" in file_set:
            families.append("angular")
            signals.append("Angular dependency or config")
        if "vite" in deps or any(p.startswith("vite.config.") for p in files):
            families.append("vite")
            signals.append("Vite dependency or config")
        if not families:
            families.append("nodejs")
    if "pyproject.toml" in file_set or "requirements.txt" in file_set:
        families.append("python")
        signals.append("Python project manifest")
    if "Cargo.toml" in file_set:
        families.append("rust")
        signals.append("Cargo.toml")
    if "go.mod" in file_set:
        families.append("go")
        signals.append("go.mod")
    if "pom.xml" in file_set or "build.gradle" in file_set or "build.gradle.kts" in file_set:
        families.append("jvm")
        signals.append("JVM build manifest")
    if "composer.json" in file_set:
        families.append("php")
        signals.append("composer.json")
    if "Gemfile" in file_set:
        families.append("ruby")
        signals.append("Gemfile")
    if "mix.exs" in file_set:
        families.append("elixir")
        signals.append("mix.exs")
    families = list(dict.fromkeys(families))
    return {
        "status": "supported_candidate" if families else "unsupported",
        "families": families,
        "signals": signals,
        "package_name": package.get("name") if package else None,
        "package_version": package.get("version") if package else None,
        "scripts_declared": sorted(package.get("scripts", {}).keys())
            if package and isinstance(package.get("scripts"), dict) else [],
        "note": "Signals are metadata only; no build scripts or application code were executed.",
    }


def inspect_repository(source: str | Path) -> dict[str, Any]:
    """Inspect a local repository directory without modifying or executing it."""
    root = Path(source).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise InspectionError("Source path must be an existing directory.")
    files, license_files, truncated = _walk(root)
    manifests = sorted(path for path in files if Path(path).name in MANIFESTS)
    technology = _technology_signals(root, files)
    return {
        "schema_version": 1,
        "source": str(root),
        "commit": _git_commit(root),
        "result": technology["status"],
        "technology": technology,
        "inventory": {
            "file_count": len(files),
            "files": files,
            "truncated": truncated,
            "manifest_files": manifests,
            "license_evidence_files": sorted(license_files),
        },
        "safety": {
            "read_only": True,
            "executed_source_code": False,
            "ignored_directories": sorted(IGNORED_DIRS),
            "file_limit": MAX_FILES,
        },
        "limitations": [
            "A detected manifest or licence filename is evidence, not proof of project compatibility or legal permission.",
            "Dependency and asset licence analysis is not yet implemented.",
            "Technology detection is heuristic; human review is required.",
        ],
    }


def inspect_github_repository(url: str, revision: str) -> dict[str, Any]:
    """Inspect a public GitHub repository at a pinned revision in a temporary directory."""
    with tempfile.TemporaryDirectory(prefix="usc-inspect-") as temporary:
        checkout = Path(temporary) / "source"
        commit = clone_pinned_repository(url, revision, checkout)
        report = inspect_repository(checkout)
        report["source"] = {"repository_url": _validate_github_url(url), "requested_revision": revision}
        report["commit"] = commit
        return report
