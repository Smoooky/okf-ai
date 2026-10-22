"""`okf stale`: documents whose `sources` changed, or past `stale_after`.

A report over the trust map (`okf trust`): which source a change touched, which remote source
changed after the document was checked, and how paths, directories and globs match, are decided
there once, so the two commands always agree.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from okf import schema
from okf.bundle import Bundle, Document
from okf.git import Change, History, toplevel
from okf.report import INFO, WARNING, Issue
from okf.sources import Registry, registry
from okf.sources.base import day
from okf.sources.git import normalize_repo_path, resource_paths, source_matches
from okf.trust import Unit, build_map, reference_moment

__all__ = ["find_stale", "normalize_repo_path", "resource_paths", "source_matches"]
_SINCE = {"verified": "it was last verified", "written": "it was last written", "edited": "it was last edited"}


def find_stale(bundle: Bundle, changed: list[str], repo_root: Path, now: datetime,
               sources: Registry | None = None) -> list[Issue]:
    """`changed`: repository paths a change touched, relative to `repo_root`. `sources`: connectors
    for remote resources (Confluence, Jira, ...), configured from the environment by default."""
    repo_root = Path(repo_root).resolve()
    git_root = toplevel(repo_root)
    history = History(git_root if git_root and git_root.resolve() == repo_root else None, now)
    changes = [Change("M", normalize_repo_path(path)) for path in changed if path.strip()]
    trust_map = build_map(repo_root, history, changes, [bundle.root], now,
                          sources=sources if sources is not None else registry(root=repo_root, history=history),
                          changes_root=repo_root, instructions=False)
    units = {unit.path: unit for unit in trust_map.units}
    issues: list[Issue] = []
    for doc in bundle.concepts():
        unit = units.get(doc.path)
        if doc.meta is None or unit is None:
            continue  # broken front matter is reported by `okf validate`
        issues.extend(_changed_sources(doc, unit))
        issues.extend(_remote_sources(doc, unit))
        expires = schema.stale_after(doc)
        if expires is not None and now >= expires:
            issues.append(Issue(WARNING, doc.path, "stale_after",
                                f"{doc.get('stale_after')} has passed (now {_utc(now)}); document is stale{_ask(doc)}",
                                doc.field_line("stale_after")))
    return issues


def _changed_sources(doc: Document, unit: Unit) -> list[Issue]:
    issues = []
    for resource, matched in unit.in_change_refs:
        what = f"Source {resource} changed" + (f" ({', '.join(matched)})" if matched != [resource] else "")
        if unit.updated_in_change:
            issues.append(Issue(INFO, doc.path, "sources", f"{what}; document was updated in the same change"))
        else:
            issues.append(Issue(WARNING, doc.path, "sources", f"{what}; document may be outdated{_ask(doc)}",
                                doc.field_line("sources")))
    return issues


def _remote_sources(doc: Document, unit: Unit) -> list[Issue]:
    """A Confluence page, Jira issue, Notion page or Slack message that changed after the moment the
    trust map compares with (`reference_moment`). Unreadable ones are INFO, never errors."""
    moment, kind = reference_moment(unit)
    issues = []
    for check in unit.remote:
        if check.connector is None:
            continue  # an URL no connector serves
        if check.status != "ok":
            issues.append(Issue(INFO, doc.path, "sources", f"Source {check.resource}: unknown, {check.message}"))
            continue
        signal = check.signal
        if signal is None or moment is None or signal.at <= moment:
            continue
        issues.append(Issue(WARNING, doc.path, "sources",
                            f"Source {check.resource}: {signal.subject} {signal.verb} {day(signal.at)}, "
                            f"after {_SINCE[kind]}; document may be outdated{_ask(doc)}", doc.field_line("sources")))
    return issues


def _ask(doc: Document) -> str:
    who = schema.reviewer(doc)
    return f", ask {who} to review it" if who else ""


def _utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
