"""Read-only, baseline-aware planning for upstream synchronization.

The planner requires a complete local Git history and never fetches, checks out,
merges, writes files, or updates refs. Fetching is deliberately a separate step.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any


_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$", re.IGNORECASE)
_RIGHTS_NAMES = {
    "license", "licence", "copying", "notice", "authors", "copyright",
    "third_party_notices", "third-party-notices",
}


class SyncPlanError(ValueError):
    """Raised when a safe upstream sync plan cannot be produced."""


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    ):
        env.pop(key, None)
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_CONFIG_GLOBAL": os.devnull,
    })
    try:
        result = subprocess.run(
            ["git", "-c", f"core.hooksPath={os.devnull}", "-c", "protocol.file.allow=never", *args],
            cwd=repo,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SyncPlanError(f"Git command could not be completed safely: {exc}") from exc
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise SyncPlanError(f"Git could not verify the requested synchronization: {detail}")
    return result


def _resolve_commit(repo: Path, value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise SyncPlanError(f"{label} must be a full 40- or 64-character commit SHA.")
    result = _git(repo, "rev-parse", "--verify", f"{value}^{{commit}}")
    resolved = result.stdout.strip().lower()
    if resolved != value.lower():
        raise SyncPlanError(f"{label} does not resolve to the exact supplied commit.")
    return resolved


def _changed_paths(repo: Path, base: str, tip: str) -> list[dict[str, Any]]:
    result = _git(repo, "diff", "--name-status", "-z", "--find-renames=50%", base, tip)
    fields = result.stdout.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    changes: list[dict[str, Any]] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if not status:
            continue
        if status.startswith(("R", "C")):
            if index + 1 >= len(fields):
                raise SyncPlanError("Git returned an incomplete rename/copy record.")
            old_path, new_path = fields[index], fields[index + 1]
            index += 2
            changes.append({"status": status, "paths": [old_path, new_path]})
        else:
            if index >= len(fields):
                raise SyncPlanError("Git returned an incomplete changed-path record.")
            path = fields[index]
            index += 1
            changes.append({"status": status, "paths": [path]})
    return changes


def _is_rights_path(path: str) -> bool:
    name = Path(path).name.lower()
    return name in _RIGHTS_NAMES or name.startswith(("license.", "licence.", "notice."))


def create_sync_plan(
    repository: str | Path,
    base_sha: str,
    target_sha: str,
) -> dict[str, Any]:
    """Create a deterministic, read-only three-way synchronization plan."""
    repo = Path(repository).expanduser().resolve()
    if not repo.is_dir():
        raise SyncPlanError("Repository path must be an existing directory.")
    if not (repo / ".git").exists():
        raise SyncPlanError("Path is not a Git working repository.")

    bare = _git(repo, "rev-parse", "--is-bare-repository").stdout.strip()
    if bare == "true":
        raise SyncPlanError("A bare repository cannot be used as the customized working copy.")
    shallow = _git(repo, "rev-parse", "--is-shallow-repository").stdout.strip()
    if shallow == "true":
        raise SyncPlanError("Shallow history is incomplete; fetch complete history before planning.")

    base = _resolve_commit(repo, base_sha, "Base SHA")
    target = _resolve_commit(repo, target_sha, "Target SHA")
    head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if status:
        raise SyncPlanError(
            "Customized working copy is not clean. Commit or safely preserve all local changes before planning."
        )

    for ancestor, descendant, label in (
        (base, head, "customized history"),
        (base, target, "upstream history"),
    ):
        result = _git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
        if result.returncode == 1:
            raise SyncPlanError(f"Base SHA is not an ancestor of {label}; a reliable three-way plan is unavailable.")
        if result.returncode != 0:
            raise SyncPlanError(f"Git could not verify the common base for {label}.")

    actual_merge_base = _git(repo, "merge-base", head, target).stdout.strip().lower()
    if actual_merge_base != base:
        raise SyncPlanError(
            "Recorded base SHA is not the exact merge base of the customized and upstream histories. "
            "Update the imported baseline before planning another synchronization."
        )

    upstream_changes = _changed_paths(repo, base, target)
    local_changes = _changed_paths(repo, base, head)
    upstream_paths = {p for item in upstream_changes for p in item["paths"]}
    local_paths = {p for item in local_changes for p in item["paths"]}
    overlap = sorted(upstream_paths & local_paths)

    merge = _git(repo, "merge-tree", "--write-tree", head, target, check=False)
    if merge.returncode not in (0, 1):
        raise SyncPlanError(
            "This Git version or repository state cannot safely perform a non-mutating merge preflight: "
            + (merge.stderr.strip() or merge.stdout.strip())
        )
    conflict_lines = [
        line.strip() for line in merge.stdout.splitlines()
        if "CONFLICT" in line.upper()
    ]
    conflicts = sorted({
        match.group(1).strip()
        for line in conflict_lines
        if (match := re.search(r"\b in (.+)$", line))
    })
    has_conflicts = merge.returncode == 1
    if has_conflicts and not conflicts:
        conflicts = overlap or ["Git reported a merge conflict; inspect the full conflict details."]

    rights_paths = sorted(
        p for p in upstream_paths
        if _is_rights_path(p)
    )
    classifications = {
        "upstream_only": sorted(upstream_paths - local_paths),
        "local_only": sorted(local_paths - upstream_paths),
        "both_changed": overlap,
    }
    return {
        "schema_version": "1.0",
        "operation": "upstream_sync_plan",
        "read_only": True,
        "base_sha": base,
        "upstream_target_sha": target,
        "customized_sha": head,
        "upstream_changes": upstream_changes,
        "local_changes": local_changes,
        "classifications": classifications,
        "merge_conflicts": conflicts,
        "merge_conflict_details": conflict_lines,
        "rights_review_required": bool(rights_paths),
        "rights_review_paths": rights_paths,
        "status": "blocked" if has_conflicts else "ready_for_review",
        "blocked_reasons": (
            ["Git's three-way merge preflight found conflicts; automatic integration is prohibited."]
            if has_conflicts else []
        ),
        "integration_approval_required": True,
        "integration_performed": False,
        "note": (
            "A clean preflight is not an integration approval. The original customized working copy "
            "has not been modified; candidate integration is a separate operation."
        ),
    }
