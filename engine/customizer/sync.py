"""Read-only, baseline-aware planning for upstream synchronization.

The planner requires a complete local Git history and never fetches, checks out,
merges, writes files, or updates refs. Fetching is deliberately a separate step.
"""
from __future__ import annotations

import os
import re
import shutil
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


def _assert_no_custom_git_drivers(repo: Path) -> None:
    """Reject repository-local Git settings that could execute external commands."""
    unsafe_settings = (
        (r"^merge\..*\.driver$", "custom merge drivers"),
        (r"^filter\..*\.(clean|smudge|process)$", "external filter drivers"),
        (r"^core\.fsmonitor$", "external filesystem monitor"),
    )
    for pattern, label in unsafe_settings:
        result = _git(repo, "config", "--local", "--get-regexp", pattern, check=False)
        if result.returncode == 0:
            raise SyncPlanError(
                f"Repository-local {label} are configured. Disable them before planning; "
                "the planner will not execute custom Git commands."
            )
        if result.returncode not in (1,):
            raise SyncPlanError("Git configuration could not be checked safely.")


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
    _assert_no_custom_git_drivers(repo)
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


def create_sync_candidate(
    repository: str | Path,
    base_sha: str,
    target_sha: str,
    workspace: str | Path,
    *,
    approved: bool = False,
    rights_reviewed: bool = False,
) -> dict[str, Any]:
    """Create an isolated, uncommitted candidate merge; never modify the source repo."""
    if not approved:
        raise SyncPlanError("Candidate creation requires explicit --approve confirmation.")
    repo = Path(repository).expanduser().resolve()
    workspace_arg = Path(workspace).expanduser()
    if not workspace_arg.name or workspace_arg.name in (".", ".."):
        raise SyncPlanError("Candidate workspace must be a new directory path.")
    parent = workspace_arg.parent.expanduser().resolve()
    if not parent.is_dir():
        raise SyncPlanError("Candidate workspace parent directory must already exist.")
    candidate = parent / workspace_arg.name
    if candidate.exists() or candidate.is_symlink():
        raise SyncPlanError("Candidate workspace already exists; choose a new, empty path.")
    if candidate == repo or repo in candidate.parents:
        raise SyncPlanError("Candidate workspace must be outside the customized repository.")

    plan = create_sync_plan(repo, base_sha, target_sha)
    if plan["status"] != "ready_for_review":
        raise SyncPlanError("The sync plan is blocked by conflicts; candidate integration is prohibited.")
    if plan["rights_review_required"] and not rights_reviewed:
        raise SyncPlanError(
            "Upstream licence/notice files changed. Complete human rights review before using --rights-reviewed."
        )

    target = plan["upstream_target_sha"]
    customized = plan["customized_sha"]
    for commit, label in ((target, "upstream target"), (customized, "customized HEAD")):
        refs = _git(repo, "for-each-ref", "--contains", commit, "--format=%(refname)").stdout.strip()
        if not refs:
            raise SyncPlanError(f"The {label} must be reachable from a local Git ref before candidate creation.")

    original_head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
    original_status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    branch_name = f"usc-sync-candidate-{target[:12]}"
    try:
        _git(
            repo,
            "-c", "protocol.file.allow=always",
            "clone", "--no-hardlinks", "--no-checkout", "--no-recurse-submodules",
            "--no-tags", "--", str(repo), str(candidate),
        )
        _git(candidate, "checkout", "--no-track", "-b", branch_name, customized)
        merge_result = _git(
            candidate, "merge", "--no-commit", "--no-ff", "--no-edit", target, check=False
        )
        if merge_result.returncode not in (0, 1):
            raise SyncPlanError(
                "Candidate merge could not be completed safely: "
                + (merge_result.stderr.strip() or merge_result.stdout.strip())
            )

        conflict_paths = _git(
            candidate, "diff", "--name-only", "--diff-filter=U", "-z"
        ).stdout.split("\0")
        conflict_paths = sorted(path for path in conflict_paths if path)
        has_conflicts = merge_result.returncode == 1
        current_head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip().lower()
        current_status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
        if current_head != original_head or current_status != original_status:
            raise SyncPlanError(
                "The original customized repository changed during candidate creation; candidate discarded."
            )

        return {
            "schema_version": "1.0",
            "operation": "upstream_sync_candidate",
            "status": "blocked" if has_conflicts else "candidate_ready_for_review",
            "candidate_path": str(candidate),
            "candidate_branch": branch_name,
            "base_sha": plan["base_sha"],
            "upstream_target_sha": target,
            "customized_sha": customized,
            "merge_conflicts": conflict_paths,
            "merge_output": merge_result.stdout.strip(),
            "rights_reviewed": bool(rights_reviewed),
            "integration_committed": False,
            "original_repository_unchanged": True,
            "tests_run": False,
            "note": (
                "Candidate is isolated and uncommitted. Review the diff and run approved verification before accepting it."
                if not has_conflicts else
                "Candidate contains unresolved conflicts. Do not accept it automatically; resolve manually or discard the candidate."
            ),
        }
    except Exception:
        if candidate.exists() and not candidate.is_symlink():
            shutil.rmtree(candidate)
        raise
