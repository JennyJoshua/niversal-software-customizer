"""Command-line entry point for safe repository inspection and sync planning."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .inspector import InspectionError, inspect_github_repository, inspect_repository
from .licensing import LicenceScanError, scan_licence_evidence
from .sync import SyncPlanError, create_sync_candidate, create_sync_plan
from .verification import create_sync_verification
from .acceptance import accept_sync_candidate, recover_sync_acceptance


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="usc",
        description="Inspect source repositories and plan safe upstream synchronization without executing source code.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Create a static repository inspection report.")
    source = inspect_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", help="Existing local source directory.")
    source.add_argument("--repo-url", help="Public HTTPS GitHub repository URL.")
    inspect_parser.add_argument("--revision", help="Required with --repo-url: branch, tag, or commit to inspect.")
    inspect_parser.add_argument("--output", help="Write JSON report to this path instead of stdout.")

    licence_parser = subparsers.add_parser(
        "licences", help="Collect project, dependency, asset, and attribution evidence for human review."
    )
    licence_parser.add_argument("--path", required=True, help="Existing local source directory.")
    licence_parser.add_argument("--output", help="Write JSON report to this path instead of stdout.")

    sync_parser = subparsers.add_parser(
        "sync-plan", help="Create a read-only three-way upstream synchronization plan."
    )
    sync_parser.add_argument("--path", required=True, help="Customized Git working repository.")
    sync_parser.add_argument("--base-sha", required=True, help="Full SHA of the last imported upstream baseline.")
    sync_parser.add_argument("--target-sha", required=True, help="Full SHA of the selected newer upstream commit.")
    sync_parser.add_argument("--output", help="Write JSON plan outside the repository.")

    candidate_parser = subparsers.add_parser(
        "sync-candidate", help="Create an isolated, uncommitted upstream integration candidate."
    )
    candidate_parser.add_argument("--path", required=True, help="Customized Git working repository.")
    candidate_parser.add_argument("--base-sha", required=True, help="Full SHA of the last imported upstream baseline.")
    candidate_parser.add_argument("--target-sha", required=True, help="Full SHA of the selected newer upstream commit.")
    candidate_parser.add_argument("--workspace", required=True, help="New candidate directory outside the source repository.")
    candidate_parser.add_argument("--approve", action="store_true", help="Confirm creation of the isolated candidate.")
    candidate_parser.add_argument(
        "--rights-reviewed", action="store_true",
        help="Confirm human review of changed upstream licence/notice files when the plan flags them."
    )
    candidate_parser.add_argument("--output", help="Write JSON candidate report outside both repositories.")

    verify_parser = subparsers.add_parser(
        "sync-verify", help="Validate external test evidence against an unchanged candidate tree."
    )
    verify_parser.add_argument("--candidate-report", required=True, help="JSON report emitted by sync-candidate.")
    verify_parser.add_argument("--evidence", required=True, help="Reviewer-supplied JSON test evidence.")
    verify_parser.add_argument("--github-run-url", help="Canonical GitHub Actions run URL for a published candidate snapshot.")
    verify_parser.add_argument("--github-repo", help="Trusted GitHub OWNER/REPOSITORY for the Actions run.")
    verify_parser.add_argument("--workflow-id", type=int, help="Trusted numeric GitHub Actions workflow ID.")
    verify_parser.add_argument("--workflow-path", help="Trusted repository-relative workflow path.")
    verify_parser.add_argument("--workflow-blob-sha", help="Pinned Git blob SHA of the trusted workflow file.")
    verify_parser.add_argument("--output", help="Write verification report outside the candidate workspace.")

    accept_parser = subparsers.add_parser(
        "sync-accept", help="Accept a verified candidate and fast-forward the unchanged customized branch."
    )
    accept_parser.add_argument("--path", required=True, help="Original customized Git working repository.")
    accept_parser.add_argument("--candidate-report", required=True, help="JSON report emitted by sync-candidate.")
    accept_parser.add_argument("--verification-report", required=True, help="JSON report emitted by sync-verify.")
    accept_parser.add_argument("--upstream-url", required=True, help="Canonical HTTPS GitHub owner/repository URL.")
    accept_parser.add_argument("--approve", action="store_true", help="Explicitly approve updating the original branch.")
    accept_parser.add_argument(
        "--evidence-reviewed", action="store_true",
        help="Confirm that you personally reviewed the supplied CI/test evidence; it is not independently authenticated."
    )
    accept_parser.add_argument("--output", help="Write acceptance report outside both repositories.")

    recover_parser = subparsers.add_parser("sync-recover", help="Resume fast-forward after candidate provenance was committed.")
    recover_parser.add_argument("--path", required=True, help="Original customized Git repository.")
    recover_parser.add_argument("--candidate-report", required=True, help="Report emitted by sync-candidate.")
    recover_parser.add_argument("--approve", action="store_true", help="Explicitly approve recovery fast-forward.")
    recover_parser.add_argument("--output", help="Write recovery report outside both repositories.")

    return parser


def _write_report(report: dict, output: str | None, source_root: Path | None = None) -> None:
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output:
        output_path = Path(output).expanduser().resolve()
        if source_root is not None and (output_path == source_root or source_root in output_path.parents):
            raise ValueError("Report output must be outside the inspected source directory.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            if args.repo_url:
                if not args.revision:
                    parser.error("--revision is required when using --repo-url.")
                report = inspect_github_repository(args.repo_url, args.revision)
                _write_report(report, args.output)
            else:
                if args.revision:
                    parser.error("--revision can only be used with --repo-url.")
                source_root = Path(args.path).expanduser().resolve()
                report = inspect_repository(source_root)
                _write_report(report, args.output, source_root)
        elif args.command == "licences":
            source_root = Path(args.path).expanduser().resolve()
            report = scan_licence_evidence(source_root)
            _write_report(report, args.output, source_root)
        elif args.command == "sync-plan":
            source_root = Path(args.path).expanduser().resolve()
            report = create_sync_plan(source_root, args.base_sha, args.target_sha)
            _write_report(report, args.output, source_root)
        elif args.command == "sync-candidate":
            source_root = Path(args.path).expanduser().resolve()
            candidate_path = Path(args.workspace).expanduser().resolve()
            if args.output:
                output_path = Path(args.output).expanduser().resolve()
                if output_path == source_root or source_root in output_path.parents:
                    raise ValueError("Report output must be outside the inspected source directory.")
                if output_path == candidate_path or candidate_path in output_path.parents:
                    raise ValueError("Candidate report output must be outside the candidate workspace.")
            report = create_sync_candidate(
                source_root, args.base_sha, args.target_sha, args.workspace,
                approved=args.approve, rights_reviewed=args.rights_reviewed,
            )
            _write_report(report, args.output, source_root)
        elif args.command == "sync-verify":
            report = create_sync_verification(
                args.candidate_report, args.evidence,
                github_run_url=args.github_run_url, github_repository=args.github_repo,
                workflow_id=args.workflow_id, workflow_path=args.workflow_path,
                workflow_blob_sha=args.workflow_blob_sha,
            )
            candidate_data = json.loads(Path(args.candidate_report).expanduser().read_text(encoding="utf-8"))
            candidate_path = Path(candidate_data["candidate_path"]).expanduser().resolve()
            if args.output:
                output_path = Path(args.output).expanduser().resolve()
                if output_path == candidate_path or candidate_path in output_path.parents:
                    raise ValueError("Verification report output must be outside the candidate workspace.")
            _write_report(report, args.output, candidate_path)
        elif args.command == "sync-accept":
            source_root = Path(args.path).expanduser().resolve()
            candidate_data = json.loads(Path(args.candidate_report).expanduser().read_text(encoding="utf-8"))
            candidate_path = Path(candidate_data["candidate_path"]).expanduser().resolve()
            if args.output:
                output_path = Path(args.output).expanduser().resolve()
                if output_path == source_root or source_root in output_path.parents:
                    raise ValueError("Acceptance report output must be outside the original repository.")
                if output_path == candidate_path or candidate_path in output_path.parents:
                    raise ValueError("Acceptance report output must be outside the candidate workspace.")
            report = accept_sync_candidate(
                source_root, args.candidate_report, args.verification_report,
                upstream_url=args.upstream_url, approved=args.approve,
                evidence_reviewed=args.evidence_reviewed,
            )
            _write_report(report, args.output, source_root)
        else:
            source_root = Path(args.path).expanduser().resolve()
            candidate_data = json.loads(Path(args.candidate_report).expanduser().read_text(encoding="utf-8"))
            candidate_path = Path(candidate_data["candidate_path"]).expanduser().resolve()
            if args.output:
                output_path = Path(args.output).expanduser().resolve()
                if output_path == source_root or source_root in output_path.parents or output_path == candidate_path or candidate_path in output_path.parents:
                    raise ValueError("Recovery report output must be outside both repositories.")
            report = recover_sync_acceptance(source_root, args.candidate_report, approved=args.approve)
            _write_report(report, args.output, source_root)
        return 0
    except (InspectionError, LicenceScanError, SyncPlanError, ValueError, OSError, KeyError) as exc:
        print(f"usc: operation blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
