"""`okf stale`: documents whose `sources` changed, or past `stale_after`."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from okf import schema
from okf.bundle import Bundle, Document
from okf.report import INFO, WARNING, Issue
from okf.sources import Registry, registry
from okf.sources.base import day
from okf.sources.git import normalize_repo_path, relative_path as _relative, resource_paths, source_matches
from okf.values import parse_instant

__all__ = ["find_stale", "normalize_repo_path", "resource_paths", "source_matches"]


def find_stale(bundle: Bundle, changed: list[str], repo_root: Path, now: datetime,
               sources: Registry | None = None) -> list[Issue]:
    """`changed`: repository paths a change touched. `sources`: connectors for remote resources
    (Confluence, Jira), configured from the environment by default."""
    repo_root = Path(repo_root).resolve()
    sources = sources if sources is not None else registry()
    changed_paths = {normalize_repo_path(path) for path in changed if path.strip()}
    issues: list[Issue] = []
    for doc in bundle.concepts():
        if doc.meta is None:
            continue  # broken front matter is reported by `okf validate`
        issues.extend(_changed_sources(doc, bundle, changed_paths, repo_root))
        issues.extend(_remote_sources(doc, sources))
        expires = schema.stale_after(doc)
        if expires is not None and now >= expires:
            issues.append(
                Issue(
                    WARNING,
                    doc.path,
                    "stale_after",
                    f"{doc.get('stale_after')} has passed (now {_utc(now)}); document is stale{_ask(doc)}",
                    doc.field_line("stale_after"),
                )
            )
    return issues


def _changed_sources(doc: Document, bundle: Bundle, changed_paths: set[str], repo_root: Path) -> list[Issue]:
    if not changed_paths:
        return []
    updated = _relative(doc.path, repo_root) in changed_paths
    issues = []
    for resource in schema.sources(doc):
        if any(ch.isspace() for ch in resource):
            continue  # a scope descriptor ("payments, all regions"), not a path: as in okf trust
        patterns = resource_paths(resource, doc, bundle.root, repo_root)
        matched = sorted(path for path in changed_paths if any(source_matches(p, path) for p in patterns))
        if not matched:
            continue
        what = f"Source {resource} changed"
        if matched != [resource]:
            what += f" ({', '.join(matched)})"
        if updated:
            issues.append(Issue(INFO, doc.path, "sources", f"{what}; document was updated in the same change"))
        else:
            issues.append(
                Issue(WARNING, doc.path, "sources", f"{what}; document may be outdated{_ask(doc)}", doc.field_line("sources"))
            )
    return issues


def _remote_sources(doc: Document, sources: Registry) -> list[Issue]:
    """A Confluence page or Jira issue that changed after the document was last verified (or, never
    verified, after the `last_modified` recorded for it). Unreadable ones are INFO, never errors."""
    latest = schema.latest_verification(doc)
    issues = []
    for entry in _entries(doc):
        resource = entry["resource"].strip()
        if any(ch.isspace() for ch in resource):
            continue
        connector = sources.find(resource)
        if connector is None or connector is sources.git:
            continue
        check = sources.check(resource)
        if check.status != "ok":
            issues.append(Issue(INFO, doc.path, "sources", f"Source {resource}: unknown, {check.message}"))
            continue
        recorded = parse_instant(entry.get("last_modified"))
        known = max(filter(None, [latest[0] if latest else None, recorded]), default=None)
        if check.signal is None or known is None or check.signal.at <= known:
            continue
        since = "it was last verified" if latest and known == latest[0] else "its recorded last_modified"
        issues.append(Issue(WARNING, doc.path, "sources",
                            f"Source {resource}: {check.signal.subject} {check.signal.verb} {day(check.signal.at)}, "
                            f"after {since}; document may be outdated{_ask(doc)}", doc.field_line("sources")))
    return issues


def _entries(doc: Document) -> list[dict]:
    value = doc.get("sources", None)
    return [e for e in value if isinstance(e, dict) and isinstance(e.get("resource"), str)
            and e["resource"].strip()] if isinstance(value, list) else []


def _ask(doc: Document) -> str:
    who = schema.reviewer(doc)
    return f", ask {who} to review it" if who else ""


def _utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
