"""Command-line entry point for safe, read-only source inspection."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .inspector import InspectionError, inspect_github_repository, inspect_repository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="usc",
        description="Inspect source repositories without executing or modifying their code.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="Create a static repository inspection report.")
    source = inspect_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", help="Existing local source directory.")
    source.add_argument("--repo-url", help="Public HTTPS GitHub repository URL.")
    inspect_parser.add_argument(
        "--revision",
        help="Required with --repo-url: branch, tag, or commit to inspect.",
    )
    inspect_parser.add_argument("--output", help="Write JSON report to this path instead of stdout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.repo_url:
            if not args.revision:
                parser.error("--revision is required when using --repo-url.")
            report = inspect_github_repository(args.repo_url, args.revision)
        else:
            if args.revision:
                parser.error("--revision can only be used with --repo-url.")
            report = inspect_repository(args.path)
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\\n"
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except InspectionError as exc:
        print(f"usc: inspection blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
