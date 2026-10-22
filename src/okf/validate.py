"""`okf validate`: front matter structure, the profile's field rules, links."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from okf.bundle import Bundle, Document
from okf.report import ERROR, WARNING, Issue
from okf.schema import Profile, get_profile


def validate_bundle(bundle: Bundle, profile: Profile | None = None) -> list[Issue]:
    profile = profile or get_profile()
    link_issues = check_links(bundle, profile)
    issues: list[Issue] = []
    for doc in bundle.documents:
        if doc.is_generated:
            continue
        if doc.read_error:
            issues.append(Issue(ERROR, doc.path, "file", doc.read_error))
        elif doc.name == "index.md":
            issues.extend(profile.check_index(doc, at_root=doc.rel == "index.md"))
        elif doc.name == "log.md":
            issues.extend(profile.check_log(doc))
        else:
            issues.extend(check_concept(doc, profile))
        issues.extend(link_issues.get(doc.path, []))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.level == ERROR for issue in issues)


def check_concept(doc: Document, profile: Profile) -> list[Issue]:
    """OKF §11: every concept has parseable front matter that is a mapping; then the profile's rules."""
    if not doc.has_front_matter:
        return [Issue(ERROR, doc.path, "frontmatter", "File must start with a YAML front matter block '---'", 1)]
    if doc.meta is None:
        return [Issue(ERROR, doc.path, "frontmatter", doc.meta_error, doc.meta_error_line)]
    return profile.check_concept(doc)


def check_links(bundle: Bundle, profile: Profile) -> dict[Path, list[Issue]]:
    """Broken links (warnings, OKF §6.1) and, if the profile asks, orphan concepts. AGENTS.md links do not count."""
    result: dict[Path, list[Issue]] = defaultdict(list)
    incoming: dict[str, set[str]] = defaultdict(set)
    for doc in bundle.documents:
        if doc.is_generated or doc.text is None:
            continue
        for target, line in doc.links():
            resolved = bundle.resolve_link(doc, target)
            if resolved is None:
                continue
            if not resolved.exists():
                result[doc.path].append(Issue(WARNING, doc.path, "link", f"Broken link to {target}", line))
            elif _key(resolved) != _key(doc.path):
                incoming[_key(resolved)].add(_key(doc.path))

    if profile.report_orphans:
        for doc in bundle.concepts():
            if not incoming[_key(doc.path)]:
                result[doc.path].append(
                    Issue(WARNING, doc.path, "link", "Orphan file: no other file in the bundle links to it", 1)
                )
    return result


def _key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))
