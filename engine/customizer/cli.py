"""Command-line interface for read-only source inspection."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .inspector import InspectionError, inspect_github_repository, inspect_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="usc",
        description="Inspect eligible source repositories without executing their code.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = commands.add_parser(
        "inspect",
        help="Create a read-only source inventory and technology report.",
    )
    source = inspect_cmd.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", help="Path to an existing local repository directory.")
    source.add_argument("--repo-url", help="Public HTTPS GitHub repository URL.")
    inspect_cmd.add_argument(
        "--revision",
        help="Branch, tag, or commit to inspect (required with --repo-url).",
    )
    inspect_cmd.add_argument(
        "--output",
        choices=("json",),
        default="json",
        help="Report format (currently json only).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        if args.repo_url and not args.revision:
            parser.error("--revision is required when --repo-url is used.")
        if args.path and args.revision:
            parser.error("--revision can only be used with --repo-url.")
        try:
            if args.path:
                report = inspect_repository(Path(args.path))
            else:
                report = inspect_github_repository(args.repo_url, args.revision)
        except InspectionError as exc:
            print(f"usc: error: {exc}", file=sys.stderr)
            return 2

        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report.get("result") == "supported_candidate" else 1

    parser.error("Unsupported command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
