"""Command line: okf validate | agents | stale."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from okf import __version__
from okf.agents import render_agents
from okf.bundle import Bundle
from okf.report import ERROR, INFO, WARNING, Issue, display_path, format_issue
from okf.stale import GitError, find_stale, git_changed_files, git_toplevel
from okf.validate import has_errors, validate_bundle


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = _parser().parse_args(argv)
    bundle_dir = Path(args.bundle)
    if not bundle_dir.is_dir():
        print(f"okf: error: bundle directory not found: {args.bundle}", file=sys.stderr)
        return 2
    return args.handler(args, Bundle.load(bundle_dir))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="okf", description="Tools for Open Knowledge Format (OKF v0.2) bundles.")
    parser.add_argument("--version", action="version", version=f"okf {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    validate = commands.add_parser("validate", help="check front matter, trust, freshness and links")
    validate.add_argument("bundle", help="bundle directory")
    _add_format(validate)
    validate.set_defaults(handler=_validate)

    agents = commands.add_parser("agents", help="generate the AGENTS.md router")
    agents.add_argument("bundle", help="bundle directory")
    agents.add_argument("-o", "--output", help="output file, '-' for stdout (default: <bundle>/AGENTS.md)")
    agents.add_argument("--check", action="store_true", help="exit 1 if AGENTS.md is out of date, write nothing")
    _add_today(agents)
    agents.set_defaults(handler=_agents)

    stale = commands.add_parser("stale", help="find documents that may be outdated")
    stale.add_argument("bundle", help="bundle directory")
    stale.add_argument(
        "--changed", nargs="+", default=[], metavar="FILE",
        help="changed files, relative to the repository root; '-' reads them from stdin",
    )
    stale.add_argument("--base", metavar="REF", help="git ref to diff against, e.g. origin/main")
    stale.add_argument("--repo-root", help="repository root for git:// paths (default: git top level)")
    _add_today(stale)
    _add_format(stale)
    stale.set_defaults(handler=_stale)
    return parser


def _add_format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format", choices=["text", "github"], default="text",
        help="'github' prints workflow commands that become PR annotations",
    )


def _add_today(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--today", type=date.fromisoformat, default=None, metavar="YYYY-MM-DD",
                        help="date to evaluate freshness against (default: today)")


def _validate(args: argparse.Namespace, bundle: Bundle) -> int:
    issues = validate_bundle(bundle)
    _print(issues, args.format)
    errors = sum(issue.level == ERROR for issue in issues)
    warnings = sum(issue.level == WARNING for issue in issues)
    print(f"okf validate: {len(bundle.documents)} files, {errors} errors, {warnings} warnings", file=sys.stderr)
    return 1 if has_errors(issues) else 0


def _agents(args: argparse.Namespace, bundle: Bundle) -> int:
    output = Path(args.output) if args.output and args.output != "-" else bundle.root / "AGENTS.md"
    text, skipped = render_agents(bundle, args.today or date.today(), output.resolve())
    for issue in skipped:
        print(format_issue(issue), file=sys.stderr)
    if args.output == "-":
        sys.stdout.write(text)
        return 0
    current = output.read_text(encoding="utf-8") if output.exists() else None
    if args.check:
        if current == text:
            print(f"okf agents: {display_path(output)} is up to date", file=sys.stderr)
            return 0
        print(f"[ERROR] {display_path(output)}: agents: File is out of date, run `okf agents {args.bundle}`")
        return 1
    output.write_text(text, encoding="utf-8", newline="\n")
    rows = len(bundle.knowledge()) - len(skipped)
    print(f"okf agents: wrote {display_path(output)} ({rows} documents)", file=sys.stderr)
    return 0


def _stale(args: argparse.Namespace, bundle: Bundle) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else git_toplevel(bundle.root) or Path.cwd()
    changed = []
    for item in args.changed:
        changed.extend(sys.stdin.read().splitlines() if item == "-" else [item])
    if args.base:
        try:
            changed.extend(git_changed_files(repo_root, args.base))
        except GitError as exc:
            print(f"okf: error: {exc}", file=sys.stderr)
            return 2
    issues = find_stale(bundle, changed, repo_root, args.today or date.today())
    _print(issues, args.format)
    outdated = len({issue.path for issue in issues if issue.field == "provenance.sources" and issue.level == WARNING})
    updated = len({issue.path for issue in issues if issue.level == INFO})
    expired = sum(issue.field == "freshness.stale_after" for issue in issues)
    print(
        f"okf stale: {len(set(changed))} changed files, {outdated} documents may be outdated, "
        f"{updated} updated alongside the code, {expired} past stale_after",
        file=sys.stderr,
    )
    return 0


def _print(issues: list[Issue], fmt: str) -> None:
    for issue in issues:
        print(format_issue(issue, fmt))
    sys.stdout.flush()  # keep issues above the stderr summary line
