"""Command line: okf init | trust | fix | verify | view | notify | import | sources | agents-check | stale | validate | agents | scan."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from okf import __version__
from okf.agents import render_agents
from okf.bundle import Bundle
from okf.report import ERROR, INFO, WARNING, Issue, display_path, format_issue
from okf.git import (
    SHALLOW_HINT, Change, GitError, History, changed_paths, changes_since, merge_base, toplevel, web_base,
)
from okf.fix import KEY_HELP, FixError, ReplayProvider, apply, plan_drafts, plan_fixes, provider_from_env, render
from okf.importer import import_confluence
from okf.notify import NotifyError, load_people, plain, reminders, send, slack_message, teams_message
from okf.pr import PrError, open_pr
from okf.instructions import check_repository
from okf.scan import ScanError, find_repos, parse_repos, scan, score
from okf.scaffold import init as init_scaffold
from okf.schema import get_profile
from okf.sources import Unavailable, registry
from okf.sources.base import day
from okf.sources.confluence import ConfluenceSource
from okf.stale import find_stale, normalize_repo_path
from okf.trust import (
    TrustError, build_map, default_actor, knowledge_units, machine_edited, unit_json, verify, verify_units,
)
from okf.validate import has_errors, validate_bundle
from okf.view import build_site, find_bundles, trust_html
from okf.values import parse_now


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # UTF-8 even through a Windows pipe (Cyrillic section titles)
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    if args.command == "verify":
        return _verify(args)
    if args.command == "scan":
        return _scan(args)
    if args.command == "import":
        return _import(args)
    if args.command == "fix":
        if not Path(args.repo).is_dir():
            print(f"okf: error: directory not found: {args.repo}", file=sys.stderr)
            return 2
        return _fix(args)
    if args.command == "view":
        return _view(args)
    if args.command == "init":
        return _init(args)
    if args.command == "notify":
        return _notify(args)
    if args.command in ("agents-check", "trust", "sources"):
        if not Path(args.repo).is_dir():
            print(f"okf: error: directory not found: {args.repo}", file=sys.stderr)
            return 2
        handlers = {"agents-check": _agents_check, "trust": _trust, "sources": _sources}
        return handlers[args.command](args)
    bundle_dir = Path(args.bundle)
    if not bundle_dir.is_dir():
        print(f"okf: error: bundle directory not found: {args.bundle}", file=sys.stderr)
        return 2
    return args.handler(args, Bundle.load(bundle_dir))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="okf",
        description="Shows which instructions and knowledge for AI agents can be trusted right now.",
    )
    parser.add_argument("--version", action="version", version=f"okf {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    init_parser = commands.add_parser("init", help="set up okf-ai here: an OKF bundle, .okf/trust.yml, the workflow")
    init_parser.add_argument("repo", nargs="?", default=".", help="repository (default: .)")
    init_parser.add_argument("--force", action="store_true", help="overwrite files that already exist")
    init_parser.add_argument("--from-agents", action="store_true",
                             help="also propose a knowledge document for every section of AGENTS.md and CLAUDE.md")
    _add_now(init_parser)

    trust = commands.add_parser("trust", help="trust map: what agents can rely on, what to recheck, what is broken")
    trust.add_argument("repo", nargs="?", default=".", help="repository or directory (default: .)")
    trust.add_argument("--since", "--base", dest="since", metavar="REF",
                       help="show only what a change since REF (e.g. origin/main) makes to recheck")
    trust.add_argument("--bundle", action="append", default=[], metavar="DIR",
                       help="OKF bundle to include (default: every .md with a type in its front matter)")
    trust.add_argument("--strict", action="store_true", help="exit 1 if anything is broken or to recheck")
    trust.add_argument("--json", action="store_true", help="print the map as JSON")
    trust.add_argument("--html", metavar="FILE", help="also write the map as one self-contained page, e.g. report.html")
    _add_now(trust)
    _add_format(trust)

    fix = commands.add_parser("fix", help="propose fixes for broken and outdated instructions: a diff, --apply writes it")
    fix.add_argument("repo", nargs="?", default=".", help="repository or directory (default: .)")
    write = fix.add_mutually_exclusive_group()
    write.add_argument("--apply", action="store_true", help="write the fixes; rewritten sections become not verified")
    write.add_argument("--pr", action="store_true", help="commit the fixes to a branch okf/update-<base>-<sha> and "
                       "open a pull request [OKF-Update] with gh (or update the open one)")
    fix.add_argument("--draft", action="store_true",
                     help="also ask an LLM to redraft sections whose code changed (your own key: " + KEY_HELP + ")")
    fix.add_argument("--replay", metavar="FILE", help="--draft from a saved model answer instead of a model call")
    fix.add_argument("--only", action="append", default=[], metavar="UNIT", help="only this unit, e.g. AGENTS.md#Auth")
    fix.add_argument("--since", "--base", dest="since", metavar="REF",
                     help="also fix files renamed since REF, and draft for what this change touched")
    fix.add_argument("--max-diff", type=int, default=40000, help="largest source diff sent to the model, in characters")
    _add_now(fix)

    verify_parser = commands.add_parser("verify", help="confirm that an instruction section or OKF document is true")
    verify_parser.add_argument("units", nargs="*", metavar="FILE[#SECTION]",
                               help="e.g. AGENTS.md#Auth (a whole file: every section), knowledge/auth_flow.md")
    verify_parser.add_argument("--by", metavar="ACTOR", help="who confirms (default: human:<git user.email>)")
    verify_parser.add_argument("--at", type=parse_now, metavar="DATETIME", help="when (default: now)")
    verify_parser.add_argument("--all-current", action="store_true",
                               help="confirm every not yet verified instruction section whose code did not change")
    verify_parser.add_argument("--repo", default=".", help="where --all-current looks (default: .)")

    view = commands.add_parser("view", help="a static site of the OKF knowledge: documents, trust levels, links")
    view.add_argument("repo", nargs="?", default=".", help="a bundle, or a repository with bundles (default: .)")
    view.add_argument("--out", default="site", metavar="DIR", help="where to write the site (default: site)")
    _add_now(view)

    notify = commands.add_parser("notify", help="remind whoever confirmed a section that it needs a recheck "
                                 "(Slack or Teams)")
    notify.add_argument("repo", nargs="?", default=".", help="repository (default: .)")
    notify.add_argument("--slack-webhook", metavar="URL", default=os.environ.get("OKF_SLACK_WEBHOOK"),
                        help="Slack incoming webhook (default: $OKF_SLACK_WEBHOOK)")
    notify.add_argument("--teams-webhook", metavar="URL", default=os.environ.get("OKF_TEAMS_WEBHOOK"),
                        help="Microsoft Teams Workflows webhook (default: $OKF_TEAMS_WEBHOOK)")
    notify.add_argument("--people", metavar="FILE", default=".okf/people.yml",
                        help="human:<id> -> {slack: <member id>} to mention people (default: .okf/people.yml)")
    notify.add_argument("--dry-run", action="store_true", help="print the messages, send nothing")
    _add_now(notify)

    importer = commands.add_parser("import", help="bring knowledge from Confluence into git as OKF documents")
    importer.add_argument("system", choices=["confluence"], help="where from")
    importer.add_argument("--space", metavar="KEY", help="every page of this space")
    importer.add_argument("--page", action="append", default=[], metavar="ID", help="only this page (repeatable)")
    importer.add_argument("--out", required=True, metavar="DIR", help="bundle directory to write to")
    importer.add_argument("--type", metavar="TYPE", help="OKF type of new documents (default: the file's, else Guide)")
    importer.add_argument("--limit", type=int, default=200, help="at most this many pages (default: 200)")
    _add_now(importer)

    sources_parser = commands.add_parser("sources", help="connectors (Confluence, Jira) and the remote sources "
                                         "of the knowledge, with their status")
    sources_parser.add_argument("repo", nargs="?", default=".", help="repository or directory (default: .)")
    sources_parser.add_argument("--bundle", action="append", default=[], metavar="DIR",
                                help="OKF bundle (default: every .md with a type in its front matter)")

    scan_parser = commands.add_parser("scan", help="probe: the trust map over many public GitHub repositories")
    mode = scan_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--repos", metavar="FILE", help="owner/repo (or owner/repo@commit) per line")
    mode.add_argument("--score", metavar="LABELS", help="precision of a hand-labelled label.csv")
    mode.add_argument("--find", type=_positive, metavar="N", help="print N public repositories with AGENTS.md or "
                      "CLAUDE.md pushed recently (needs `gh auth login`)")
    scan_parser.add_argument("--out", default="report", help="report directory (default: report)")
    scan_parser.add_argument("--jobs", type=int, default=4, help="repositories at a time (default: 4)")
    scan_parser.add_argument("--sample", type=int, default=100, help="links to sample for labelling (default: 100)")
    scan_parser.add_argument("--seed", type=int, default=42, help="seed of the sample (default: 42)")
    scan_parser.add_argument("--timeout", type=int, default=300, help="seconds per clone (default: 300)")
    scan_parser.add_argument("--work", help="where temporary clones go (default: the system temp directory)")
    scan_parser.add_argument("--keep", action="store_true", help="keep the clones (for debugging)")
    scan_parser.add_argument("--months", type=int, default=3, help="--find: pushed within this many months")
    _add_now(scan_parser)

    check = commands.add_parser(
        "agents-check", help="check AGENTS.md, CLAUDE.md, Cursor and Copilot rules against the code"
    )
    check.add_argument("repo", nargs="?", default=".", help="repository or directory to check (default: .)")
    check.add_argument("--strict", action="store_true", help="report broken paths and commands as errors (exit 1)")
    _add_changes(check)
    _add_format(check)

    validate = commands.add_parser("validate", help="check the bundle against OKF v0.2")
    validate.add_argument("bundle", help="bundle directory")
    validate.add_argument(
        "--strict", action="store_true",
        help="also apply the okf-ai team rules: sources, verified and stale_after required, no unreviewed "
        "agent-written stable documents, type dictionary, orphan files",
    )
    _add_format(validate)
    validate.set_defaults(handler=_validate)

    agents = commands.add_parser("agents", help="generate the AGENTS.md router")
    agents.add_argument("bundle", help="bundle directory")
    agents.add_argument("-o", "--output", help="output file, '-' for stdout (default: <bundle>/AGENTS.md)")
    agents.add_argument("--check", action="store_true", help="exit 1 if AGENTS.md is out of date, write nothing")
    _add_now(agents)
    agents.set_defaults(handler=_agents)

    stale = commands.add_parser("stale", help="find documents that may be outdated")
    stale.add_argument("bundle", help="bundle directory")
    _add_changes(stale)
    _add_now(stale)
    _add_format(stale)
    stale.set_defaults(handler=_stale)
    return parser


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, got {value}")
    return value


def _add_changes(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--changed", nargs="+", default=[], metavar="FILE",
        help="changed files, relative to the repository root; '-' reads them from stdin",
    )
    parser.add_argument("--base", metavar="REF", help="git ref to diff against, e.g. origin/main")
    parser.add_argument("--repo-root", help="repository root (default: git top level, else the current directory)")


def _changed_files(args: argparse.Namespace) -> list[str]:
    changed = []
    for item in args.changed:
        changed.extend(sys.stdin.read().splitlines() if item == "-" else [item])
    return [path for path in changed if path.strip()]


def _add_format(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format", choices=["text", "github"], default="text",
        help="'github' prints workflow commands that become PR annotations",
    )


def _add_now(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--now", type=parse_now, default=None, metavar="DATETIME",
                        help="moment to evaluate stale_after against: YYYY-MM-DD (midnight UTC) or an ISO "
                        "datetime with offset (default: now)")


def _now(args: argparse.Namespace) -> datetime:
    return args.now or datetime.now(timezone.utc)


def _agents_check(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    git_root = Path(args.repo_root).resolve() if args.repo_root else toplevel(root) or Path.cwd()
    changes = None
    if args.changed or args.base:
        changes = [Change("M", normalize_repo_path(path)) for path in _changed_files(args)]
        if args.base:
            try:
                changes.extend(changes_since(git_root, args.base))
            except GitError as exc:
                print(f"okf: error: {exc}", file=sys.stderr)
                return 2
    report = check_repository(root, args.strict, changes, git_root)
    _print(report.issues, args.format)
    errors = sum(issue.level == ERROR for issue in report.issues)
    warnings = sum(issue.level == WARNING for issue in report.issues)
    print(
        f"okf agents-check: {report.files} instruction files, {report.paths} paths, {report.commands} commands, "
        f"{errors} errors, {warnings} warnings",
        file=sys.stderr,
    )
    return 1 if errors else 0


_TRUST_LABELS = {"broken": ERROR, "recheck": WARNING, "human-verified": "OK", "process-verified": "OK",
                 "unverified": INFO}


def _trust(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    git_root = toplevel(root)
    now = _now(args)
    changes = base_commit = None
    if args.since:
        if git_root is None:
            print("okf: error: --since needs a git repository", file=sys.stderr)
            return 2
        try:
            base_commit = merge_base(git_root, args.since)
            changes = changes_since(git_root, args.since)
        except GitError as exc:
            print(f"okf: error: {exc}", file=sys.stderr)
            return 2
    history = History(git_root, now)
    trust_map = build_map(root, history, changes, [Path(b) for b in args.bundle] or None, now, base_commit)
    problems = trust_map.problems()
    if changes is not None:
        broken = trust_map.broken_in_change()
        shown = [u for u in trust_map.units if u.in_change or u in broken]
    else:
        shown = trust_map.units
    if args.html:
        page = trust_html(trust_map, root, now, shown, web_base(git_root), git_root)
        Path(args.html).write_text(page, encoding="utf-8", newline="\n")
    if args.json:
        data = {"summary": _trust_summary(trust_map), "warnings": [SHALLOW_HINT] if trust_map.shallow else [],
                "units": [unit_json(u, root) for u in shown],
                "notes": [{"file": display_path(p), "note": n} for p, n in trust_map.notes]}
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if trust_map.shallow:
            print(f"okf trust: warning: {SHALLOW_HINT}", file=sys.stderr)
        print(trust_map.summary(), file=sys.stderr)
        sys.stderr.flush()
        for unit in shown:
            label, message = _TRUST_LABELS[unit.level], unit.message
            if unit.updated_in_change and unit.level != "broken":
                label = INFO
                message = f"{', '.join(unit.in_change)} and this {'section' if unit.section else 'file'} " \
                          "changed together in this change"
            if args.format == "github":
                if label in (ERROR, WARNING):
                    shown_message = f"{unit.section}: {message}" if unit.section else message
                    print(format_issue(Issue(label, unit.path, "trust", shown_message, unit.line), "github"))
                continue
            name = display_path(unit.path) + (f"#{unit.section}" if unit.section else "")
            print(f"[{label}] {name}: trust: {message}")
        if args.format != "github":
            for path, note in trust_map.notes:
                print(f"[INFO] {display_path(path)}: trust: {note}")
        sys.stdout.flush()
    if args.html:
        print(f"okf trust: wrote {args.html}", file=sys.stderr)
    return 1 if args.strict and problems else 0


def _trust_summary(trust_map) -> dict:
    return {
        "units": len(trust_map.units),
        "verified": trust_map.count("human-verified", "process-verified"),
        "recheck": trust_map.count("recheck"),
        "broken": trust_map.count("broken"),
        "unverified": trust_map.count("unverified"),
        "in_change": len(trust_map.in_change()) if trust_map.since else None,
        "history": "shallow" if trust_map.shallow else "full",
    }


def _fix(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    git_root = toplevel(root)
    now = _now(args)
    changes = base_commit = None
    if args.since:
        if git_root is None:
            print("okf: error: --since needs a git repository", file=sys.stderr)
            return 2
        try:
            base_commit = merge_base(git_root, args.since)
            changes = changes_since(git_root, args.since)
        except GitError as exc:
            print(f"okf: error: {exc}", file=sys.stderr)
            return 2
    history = History(git_root, now)
    sources = registry(root=root, history=history)
    trust_map = build_map(root, history, changes, None, now, base_commit, sources)
    plan = plan_fixes(root, history, trust_map, changes, args.only)
    if args.draft or args.replay:
        try:
            provider = ReplayProvider(Path(args.replay)) if args.replay else provider_from_env()
        except (OSError, ValueError) as exc:
            print(f"okf: error: cannot read {args.replay}: {exc}", file=sys.stderr)
            return 2
        if provider is None:
            print(f"okf fix: no LLM key, so no drafts: {KEY_HELP}; showing the mechanical fixes only", file=sys.stderr)
        else:
            plan_drafts(plan, trust_map, history, provider, args.only, base_commit, args.max_diff, sources)
    mechanical, drafted = render(plan)
    sys.stdout.write(mechanical + drafted)
    sys.stdout.flush()
    for edit in plan.edits:
        print(f"okf fix: {edit.unit}: {edit.reason}", file=sys.stderr)
    for item in plan.manual:
        print(f"okf fix: {item.unit} (line {item.line}): {item.reason}", file=sys.stderr)
    for draft in plan.drafts:
        if draft.rejected:
            print(f"okf fix --draft: {draft.unit}: no draft: {draft.rejected}", file=sys.stderr)
        else:
            print(f"okf fix --draft: {draft.unit}: {draft.summary} (by {draft.by}; not verified)", file=sys.stderr)
    drafts = sum(not d.rejected for d in plan.drafts)
    print(f"okf fix: {len(plan.edits)} mechanical fixes, {drafts} drafts, {len(plan.manual)} need a manual fix",
          file=sys.stderr)
    if args.pr:
        if git_root is None:
            print("okf: error: --pr needs a git repository", file=sys.stderr)
            return 2
        try:
            pull = open_pr(plan, git_root, now if args.now else None)
        except PrError as exc:
            print(f"okf: error: {exc}", file=sys.stderr)
            return 2
        if pull is None:
            print("okf fix: nothing to fix, so no pull request", file=sys.stderr)
        else:
            print(f"okf fix: {'updated the open' if pull.updated else 'opened a'} pull request from {pull.branch}: "
                  f"{pull.url}", file=sys.stderr)
        return 0
    if args.apply and (plan.edits or drafts):
        try:
            units = apply(plan, git_root, now if args.now else None)
        except (OSError, FixError) as exc:
            print(f"okf: error: {exc}", file=sys.stderr)
            return 2
        print(f"okf fix: applied to {', '.join(units)}; they stay not verified until okf verify", file=sys.stderr)
    return 0


def _verify(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    at = args.at or datetime.now(timezone.utc)
    if not args.units and not args.all_current:
        print("okf: error: name what to verify (FILE[#SECTION]) or pass --all-current", file=sys.stderr)
        return 2
    try:
        by = args.by or default_actor(cwd)
        names, skipped = [], []
        for target in args.units:
            folder = (cwd / target.partition("#")[0]).resolve().parent
            names.extend(verify(target, by, at, cwd, toplevel(folder) if folder.is_dir() else None))
        if args.all_current:
            root = Path(args.repo).resolve()
            git_root = toplevel(root)
            trust_map = build_map(root, History(git_root), None, None, sources=registry({}))
            current = [u for u in trust_map.units if u.kind == "instruction" and u.level == "unverified"]
            skipped = [u.name for u in current if machine_edited(u)]  # AI edits: a person reads them one by one
            names.extend(verify_units([u for u in current if not machine_edited(u)], by, at, cwd, git_root))
    except TrustError as exc:
        print(f"okf: error: {exc}", file=sys.stderr)
        return 2
    stamp = at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name in names:
        print(f"okf verify: {name} verified by {by} at {stamp}", file=sys.stderr)
    if skipped:
        print(f"okf verify: skipped {len(skipped)} edited by a tool or a model ({', '.join(skipped)}): "
              "read each and confirm it with okf verify <unit>", file=sys.stderr)
    elif not names:
        print("okf verify: nothing to verify", file=sys.stderr)
    return 0


def _notify(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"okf: error: directory not found: {args.repo}", file=sys.stderr)
        return 2
    if not (args.slack_webhook or args.teams_webhook or args.dry_run):
        print("okf: error: set --slack-webhook (or OKF_SLACK_WEBHOOK) or --teams-webhook (or OKF_TEAMS_WEBHOOK); "
              "--dry-run prints the messages", file=sys.stderr)
        return 2
    now = _now(args)
    git_root = toplevel(root)
    trust_map = build_map(root, History(git_root, now), None, None, now)
    found = reminders(trust_map)
    if not found:
        print("okf notify: nothing to recheck, no messages", file=sys.stderr)
        return 0
    web = web_base(git_root)
    people = load_people(root / args.people)
    targets = [(name, url) for name, url in (("slack", args.slack_webhook), ("teams", args.teams_webhook)) if url]
    failed = 0
    for reminder in found:
        for name, url in targets or [("slack", None)]:
            message = (slack_message(reminder, root, web, git_root, people) if name == "slack"
                       else teams_message(reminder, root, web, git_root))
            if args.dry_run:
                print(f"--- {name}, for {reminder.who} ---\n{plain(message)}\n")
                continue
            try:
                send(url, message)
                print(f"okf notify: sent to {name} for {reminder.who} ({len(reminder.units)} units)", file=sys.stderr)
            except NotifyError as exc:
                failed += 1
                print(f"okf notify: {name}, for {reminder.who}: {exc}", file=sys.stderr)
    sys.stdout.flush()
    units = sum(len(r.units) for r in found)
    verb = "would send" if args.dry_run else "sent"
    print(f"okf notify: {units} units to recheck, {len(found)} people or groups; {verb} "
          f"{len(found) * max(len(targets), 1) - failed} messages", file=sys.stderr)
    return 1 if failed else 0


def _init(args: argparse.Namespace) -> int:
    root = Path(args.repo)
    if not root.is_dir():
        print(f"okf: error: directory not found: {args.repo}", file=sys.stderr)
        return 2
    result = init_scaffold(root, _now(args), args.force, args.from_agents)
    for path in result.created:
        print(f"okf init: created {display_path(path)}", file=sys.stderr)
    for path in result.updated:
        print(f"okf init: updated {display_path(path)}", file=sys.stderr)
    for path in result.kept:
        print(f"okf init: kept {display_path(path)} (it exists; --force overwrites it)", file=sys.stderr)
    print("okf init: next: fill in knowledge/, then okf trust and okf verify <file>", file=sys.stderr)
    return 0


def _view(args: argparse.Namespace) -> int:
    path = Path(args.repo).resolve()
    if not path.is_dir():
        print(f"okf: error: directory not found: {args.repo}", file=sys.stderr)
        return 2
    bundles = find_bundles(path)
    if not bundles:
        print(f"okf view: no OKF bundle (an index.md with okf_version) in {args.repo}", file=sys.stderr)
        return 2
    now, out = _now(args), Path(args.out)
    git_root = toplevel(path)
    history = History(git_root, now)
    for bundle_root in bundles:
        trust_map = build_map(git_root or path, history, None, [bundle_root], now)
        units = {u.path: u for u in trust_map.units if u.kind == "knowledge"}
        target = out if len(bundles) == 1 else out / bundle_root.name
        bundle = Bundle.load(bundle_root)
        pages = build_site(bundle, target, units, now)
        print(f"okf view: {display_path(bundle_root)}: {len(bundle.concepts())} documents, "
              f"open {display_path(pages[0])}", file=sys.stderr)
    return 0


def _import(args: argparse.Namespace) -> int:
    if not args.space and not args.page:
        print("okf: error: name a space (--space KEY) or pages (--page ID)", file=sys.stderr)
        return 2
    connector = next(c for c in registry().connectors if isinstance(c, ConfluenceSource))
    problem = connector.unconfigured()
    if problem:
        print(f"okf import: {problem}", file=sys.stderr)
        return 2
    out = Path(args.out)
    try:
        done = import_confluence(connector, out, args.space, args.page, args.type, args.limit, _now(args))
    except Unavailable as exc:
        print(f"okf import: Confluence: {exc}", file=sys.stderr)
        return 1
    for item in done:
        at = f", {day(item.page.at)}" if item.page.at else ""
        print(f"okf import: {item.action}: {display_path(item.path)} (page {item.page.id} v{item.page.version}{at})",
              file=sys.stderr)
    written = sum(item.action != "unchanged" for item in done)
    where = f"space {args.space}" if args.space and not args.page else "Confluence"
    after = "; they stay not verified until okf verify" if written else ""
    print(f"okf import: {len(done)} pages from {where}, {written} written to {display_path(out)}{after}",
          file=sys.stderr)
    return 0


def _sources(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    sources = registry(root=root)
    for connector in sources.connectors:
        state = connector.unconfigured() or f"configured ({getattr(connector, 'base', '')})"
        print(f"okf sources: {connector.name}: {state}", file=sys.stderr)
    units = knowledge_units(root, History(toplevel(root)), [Path(b) for b in args.bundle] or None, sources)
    count = 0
    for unit in units:
        for check in unit.remote:
            if check.connector is None:
                continue
            count += 1
            signal = f"; {check.signal.subject} {check.signal.verb} {day(check.signal.at)}" if check.signal else ""
            label = "OK" if check.status == "ok" else INFO
            print(f"[{label}] {display_path(unit.path)}: {check.connector}: {check.resource}: "
                  f"{check.status}, {check.message}{signal}")
    sys.stdout.flush()
    print(f"okf sources: {count} remote sources with a connector", file=sys.stderr)
    return 0


def _scan(args: argparse.Namespace) -> int:
    def log(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    try:
        if args.score:
            sys.stdout.write(score(Path(args.score)))
            return 0
        if args.find is not None:
            for name in find_repos(args.find, args.months, log):
                print(name)
            return 0
        specs = parse_repos(Path(args.repos).read_text(encoding="utf-8"))
    except (ScanError, OSError) as exc:
        print(f"okf: error: {exc}", file=sys.stderr)
        return 2
    out = Path(args.out)
    log(f"okf scan: {len(specs)} repositories, {args.jobs} at a time; report in {out}")
    rows = scan(specs, out, args.jobs, args.sample, args.seed, args.now, args.timeout,
                Path(args.work) if args.work else None, args.keep, log=log)
    done = sum(r["status"] == "ok" for r in rows)
    log(f"okf scan: {done} scanned, {len(rows) - done} skipped; see {out / 'summary.md'}")
    return 0


def _validate(args: argparse.Namespace, bundle: Bundle) -> int:
    profile = get_profile(args.strict)
    issues = validate_bundle(bundle, profile)
    _print(issues, args.format)
    errors = sum(issue.level == ERROR for issue in issues)
    warnings = sum(issue.level == WARNING for issue in issues)
    print(
        f"okf validate ({profile.name}): {len(bundle.documents)} files, {errors} errors, {warnings} warnings",
        file=sys.stderr,
    )
    return 1 if has_errors(issues) else 0


def _agents(args: argparse.Namespace, bundle: Bundle) -> int:
    output = Path(args.output) if args.output and args.output != "-" else bundle.root / "AGENTS.md"
    text, skipped = render_agents(bundle, _now(args), output.resolve())
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
    rows = len(bundle.concepts()) - len(skipped)
    print(f"okf agents: wrote {display_path(output)} ({rows} documents)", file=sys.stderr)
    return 0


def _stale(args: argparse.Namespace, bundle: Bundle) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else toplevel(bundle.root) or Path.cwd()
    changed = _changed_files(args)
    if args.base:
        try:
            changed.extend(changed_paths(changes_since(repo_root, args.base)))
        except GitError as exc:
            print(f"okf: error: {exc}", file=sys.stderr)
            return 2
    issues = find_stale(bundle, changed, repo_root, _now(args))
    _print(issues, args.format)
    outdated = len({issue.path for issue in issues if issue.field == "sources" and issue.level == WARNING})
    updated = len({issue.path for issue in issues if issue.level == INFO and "same change" in issue.message})
    expired = sum(issue.field == "stale_after" for issue in issues)
    print(
        f"okf stale: {len(set(changed))} changed files, {outdated} documents may be outdated, "
        f"{updated} updated alongside their sources, {expired} past stale_after",
        file=sys.stderr,
    )
    return 0


def _print(issues: list[Issue], fmt: str) -> None:
    for issue in issues:
        print(format_issue(issue, fmt))
    sys.stdout.flush()  # keep issues above the stderr summary line
