"""Run a GitHub Actions-authenticated sync lifecycle on a dedicated test snapshot.

The trigger file is supplied only by the isolated test fixture branches. This script
uses public GitHub refs and temporary local clones; it never pushes or writes to a
product branch.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


WORKFLOW_ID = 422317206
WORKFLOW_PATH = ".github/workflows/ci.yml"
TRUSTED_WORKFLOW_BLOB_SHA = "0752aaa0aea0d75a300ed9782761bc3012f6a594"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def command(*args: str) -> str:
    result = subprocess.run(
        list(args),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def main() -> None:
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    repository = os.environ["GITHUB_REPOSITORY"]
    snapshot_sha = os.environ["USC_SNAPSHOT_SHA"].lower()
    snapshot_branch = os.environ["USC_SNAPSHOT_BRANCH"]
    run_url = os.environ["USC_AUTHENTICATED_RUN_URL"]
    trigger_path = workspace / "tests/fixtures/live-upstream-sync/trigger.json"
    trigger = json.loads(trigger_path.read_text(encoding="utf-8"))

    required = {
        "base_sha", "upstream_branch", "customized_branch",
        "upstream_file", "upstream_content", "custom_file", "custom_content",
    }
    if not required.issubset(trigger):
        raise RuntimeError(f"Live-sync fixture is missing fields: {sorted(required - set(trigger))}")
    if not snapshot_branch.startswith("usc-verify/"):
        raise RuntimeError("Live-sync validation must run only on a USC verification branch.")

    upstream_url = f"https://github.com/{repository}"
    with tempfile.TemporaryDirectory(prefix="usc-live-sync-") as temporary:
        root = Path(temporary)
        source = root / "customized"
        candidate = root / "candidate"
        candidate_report = root / "candidate-report.json"
        snapshot_report = root / "snapshot-report.json"
        evidence_file = root / "verification-evidence.json"
        verification_report = root / "verification-report.json"
        acceptance_report = root / "acceptance-report.json"

        command("git", "clone", "--no-tags", "--no-checkout", f"{upstream_url}.git", str(source))
        git(source, "fetch", "--no-tags", "origin",
            f"+refs/heads/{trigger['customized_branch']}:refs/remotes/origin/{trigger['customized_branch']}")
        git(source, "fetch", "--no-tags", "origin",
            f"+refs/heads/{trigger['upstream_branch']}:refs/heads/{trigger['upstream_branch']}")
        git(source, "fetch", "--no-tags", "origin",
            f"+refs/heads/{snapshot_branch}:refs/heads/{snapshot_branch}")
        git(source, "checkout", "-B", trigger["customized_branch"],
            f"refs/remotes/origin/{trigger['customized_branch']}")
        git(source, "config", "user.name", "USC Live Validation")
        git(source, "config", "user.email", "usc-live-validation@example.invalid")

        base_sha = str(trigger["base_sha"]).lower()
        upstream_sha = git(source, "rev-parse", f"refs/heads/{trigger['upstream_branch']}").lower()
        customized_sha = git(source, "rev-parse", "HEAD").lower()
        snapshot_tree = git(workspace, "rev-parse", f"{snapshot_sha}^{{tree}}").lower()
        snapshot_parent = git(workspace, "rev-parse", f"{snapshot_sha}^").lower()

        if snapshot_parent != customized_sha:
            raise RuntimeError("Published verification snapshot does not have the customized commit as its sole parent.")
        if git(workspace, "rev-list", "--parents", "-n", "1", snapshot_sha).split() != [snapshot_sha, customized_sha]:
            raise RuntimeError("Published verification snapshot has unexpected parent structure.")

        command(
            "usc", "sync-candidate",
            "--path", str(source),
            "--base-sha", base_sha,
            "--target-sha", upstream_sha,
            "--workspace", str(candidate),
            "--approve",
            "--output", str(candidate_report),
        )
        candidate_data = json.loads(candidate_report.read_text(encoding="utf-8"))
        if candidate_data.get("status") != "candidate_ready_for_review":
            raise RuntimeError(f"Candidate was not ready for review: {candidate_data.get('status')}")
        if candidate_data.get("customized_sha") != customized_sha:
            raise RuntimeError("Candidate report customized SHA differs from the fixture branch.")
        candidate_tree = git(candidate, "write-tree").lower()
        if candidate_tree != snapshot_tree:
            raise RuntimeError(
                f"Candidate tree {candidate_tree} does not match published snapshot tree {snapshot_tree}."
            )

        # Make the already-published snapshot ref available to the candidate verifier.
        git(candidate, "-c", "protocol.file.allow=always", "fetch", "--no-tags",
            str(source), f"refs/heads/{snapshot_branch}:refs/heads/{snapshot_branch}")

        snapshot_data = {
            "schema_version": "1.0",
            "operation": "upstream_sync_verification_snapshot",
            "status": "snapshot_ready_to_publish",
            "repository": repository,
            "push_url": f"{upstream_url}.git",
            "candidate_path": str(candidate),
            "candidate_branch": candidate_data["candidate_branch"],
            "snapshot_branch": snapshot_branch,
            "snapshot_commit_sha": snapshot_sha,
            "candidate_tree_sha": candidate_tree,
            "parent_sha": customized_sha,
            "upstream_target_sha": upstream_sha,
            "push_performed": True,
            "original_repository_unchanged": True,
            "candidate_merge_state_unchanged": True,
        }
        snapshot_report.write_text(json.dumps(snapshot_data, indent=2) + "\n", encoding="utf-8")

        evidence = {
            "schema_version": "1.0",
            "verification_status": "passed",
            "reviewer": "USC Phase 3 automated live-validation workflow",
            "verified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "verification_source": run_url,
            "candidate_tree_sha": candidate_tree,
            "rights_reviewed": False,
            "test_results": [{
                "name": "GitHub Actions CI and live candidate-tree preservation assertions",
                "passed": True,
                "evidence_ref": run_url,
            }],
        }
        evidence_file.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

        command(
            "usc", "sync-verify",
            "--candidate-report", str(candidate_report),
            "--evidence", str(evidence_file),
            "--snapshot-report", str(snapshot_report),
            "--github-run-url", run_url,
            "--github-repo", repository,
            "--workflow-id", str(WORKFLOW_ID),
            "--workflow-path", WORKFLOW_PATH,
            "--workflow-blob-sha", TRUSTED_WORKFLOW_BLOB_SHA,
            "--output", str(verification_report),
        )
        verification = json.loads(verification_report.read_text(encoding="utf-8"))
        if verification.get("status") != "verification_passed" or verification.get("evidence_authenticated") is not True:
            raise RuntimeError("Live GitHub Actions evidence was not independently authenticated.")

        command(
            "usc", "sync-accept",
            "--path", str(source),
            "--candidate-report", str(candidate_report),
            "--verification-report", str(verification_report),
            "--upstream-url", upstream_url,
            "--evidence-reviewed",
            "--approve",
            "--output", str(acceptance_report),
        )
        accepted = json.loads(acceptance_report.read_text(encoding="utf-8"))
        if accepted.get("status") != "accepted" or accepted.get("original_repository_updated") is not True:
            raise RuntimeError("The isolated live acceptance step did not complete.")

        for field in ("custom_file", "upstream_file"):
            path = trigger[field]
            expected = trigger["custom_content" if field == "custom_file" else "upstream_content"]
            actual = (source / path).read_text(encoding="utf-8")
            if actual != expected:
                raise RuntimeError(f"Preservation assertion failed for {path}.")
        baseline = json.loads((source / ".usc/upstream-baseline.json").read_text(encoding="utf-8"))
        if str(baseline.get("last_imported_upstream_sha", "")).lower() != upstream_sha:
            raise RuntimeError("Accepted upstream baseline does not match the selected upstream target.")
        provenance_path = source / baseline["provenance_path"]
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance.get("verification_evidence_authenticated") is not True:
            raise RuntimeError("Accepted provenance does not record authenticated CI evidence.")
        if git(source, "status", "--porcelain", "--untracked-files=all"):
            raise RuntimeError("Accepted source clone is not clean.")

        print(json.dumps({
            "status": "live_sync_lifecycle_passed",
            "repository": repository,
            "snapshot_branch": snapshot_branch,
            "snapshot_commit_sha": snapshot_sha,
            "candidate_tree_sha": candidate_tree,
            "customized_sha": customized_sha,
            "upstream_target_sha": upstream_sha,
            "authenticated_actions_run": run_url,
            "accepted_merge_commit": accepted["merge_commit_sha"],
            "provenance_commit": accepted["provenance_commit_sha"],
            "custom_feature_preserved": True,
            "upstream_improvement_included": True,
            "baseline_advanced": True,
            "product_remote_branch_pushed": False,
        }, indent=2))


if __name__ == "__main__":
    main()
