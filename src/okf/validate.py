"""Stage 1 validation rules (etc/spec/cli-validator.md)."""

from __future__ import annotations

import difflib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from okf.bundle import MISSING, Bundle, Document, as_date, describe
from okf.report import ERROR, WARNING, Issue

# Appendix 2 of the spec, exact strings.
ALLOWED_TYPES = (
    "Concept",
    "Architecture",
    "Table",
    "Dataset",
    "Metric",
    "API Endpoint",
    "Runbook",
    "Playbook",
    "Guide",
    "Reference",
    "Policy",
    "Service",
    "Repository",
    "Glossary Term",
)

# `trust.generated` values that must never claim full confidence.
MACHINE_GENERATORS = ("script", "agent")


def validate_bundle(bundle: Bundle) -> list[Issue]:
    link_issues = check_links(bundle)
    issues: list[Issue] = []
    for doc in bundle.documents:
        if doc.is_generated:
            continue
        issues.extend(check_service_file(doc) if doc.is_service else check_knowledge_file(doc))
        issues.extend(link_issues.get(doc.path, []))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.level == ERROR for issue in issues)


def check_service_file(doc: Document) -> list[Issue]:
    if doc.read_error:
        return [Issue(ERROR, doc.path, "file", doc.read_error)]
    if doc.has_front_matter:
        return [Issue(ERROR, doc.path, "frontmatter", f"Service file {doc.rel} must not contain YAML front matter", 1)]
    return []


def check_knowledge_file(doc: Document) -> list[Issue]:
    if doc.read_error:
        return [Issue(ERROR, doc.path, "file", doc.read_error)]
    if not doc.has_front_matter:
        return [Issue(ERROR, doc.path, "frontmatter", "File must start with a YAML front matter block '---'", 1)]
    if doc.meta is None:
        return [Issue(ERROR, doc.path, "frontmatter", doc.meta_error, doc.meta_error_line)]

    issues: list[Issue] = []

    def error(name: str, message: str) -> None:
        issues.append(Issue(ERROR, doc.path, name, message, doc.field_line(name)))

    _check_type(doc, error)
    _check_tags(doc, error)
    _check_provenance(doc, error)
    _check_trust(doc, error)
    _check_freshness(doc, error)
    return issues


def _check_type(doc: Document, error) -> None:
    value = doc.get("type")
    if value is MISSING:
        error("type", "Field is required")
    elif value is None or (isinstance(value, str) and not value.strip()):
        error("type", "Field must not be empty")
    elif not isinstance(value, str) or value not in ALLOWED_TYPES:
        message = f"Value {_show(value)} is not in the allowed type dictionary"
        suggestion = _suggest_type(value)
        if suggestion:
            message += f' (did you mean "{suggestion}"?)'
        error("type", message)


def _check_tags(doc: Document, error) -> None:
    tags = doc.get("tags")
    if tags is MISSING:
        return
    if not isinstance(tags, list):
        error("tags", f"Must be a list of strings, got {describe(tags)}")
    elif not all(isinstance(tag, str) for tag in tags):
        error("tags", "Must be a list of strings, got a list with non-string items")


def _check_provenance(doc: Document, error) -> None:
    provenance = doc.get("provenance")
    if provenance is not MISSING and provenance is not None and not isinstance(provenance, dict):
        error("provenance", f"Must be a mapping with a 'sources' list, got {describe(provenance)}")
        return
    sources = doc.get("provenance.sources")
    if sources is MISSING or sources is None:
        error("provenance.sources", "Field is required: list at least one source, e.g. git://path/to/file")
    elif not isinstance(sources, list):
        error("provenance.sources", f"Must be a list of sources, got {describe(sources)}")
    elif not sources:
        error("provenance.sources", "List must not be empty: add at least one source, e.g. git://path/to/file")
    else:
        for i, source in enumerate(sources):
            if not isinstance(source, str) or not source.strip():
                error(f"provenance.sources[{i}]", "Source must be a non-empty string")


def _check_trust(doc: Document, error) -> None:
    trust = doc.get("trust")
    if trust is not MISSING and trust is not None and not isinstance(trust, dict):
        error("trust", f"Must be a mapping, got {describe(trust)}")
        return

    confidence = doc.get("trust.confidence")
    if confidence is MISSING or confidence is None:
        error("trust.confidence", "Field is required")
    elif isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        error("trust.confidence", f"Value must be a number between 0.0 and 1.0, got {describe(confidence)} {_show(confidence)}")
    elif not 0.0 <= confidence <= 1.0:
        error("trust.confidence", f"Value must be between 0.0 and 1.0 (got {confidence})")
    else:
        generated = doc.get("trust.generated")
        if isinstance(generated, str) and generated.strip().lower() in MACHINE_GENERATORS and confidence == 1.0:
            error(
                "trust.confidence",
                f'Value 1.0 is reserved for human-verified knowledge; a document generated by "{generated}" '
                "must have confidence below 1.0",
            )

    verified_by = doc.get("trust.verified_by")
    if verified_by is MISSING or verified_by is None or (isinstance(verified_by, str) and not verified_by.strip()):
        error("trust.verified_by", "Field is required: name the person responsible for this document")


def _check_freshness(doc: Document, error) -> None:
    freshness = doc.get("freshness")
    if freshness is not MISSING and freshness is not None and not isinstance(freshness, dict):
        error("freshness", f"Must be a mapping with last_reviewed and stale_after, got {describe(freshness)}")
        return
    hint = ""
    if freshness is MISSING and doc.get("lifecycle.freshness") is not MISSING:
        hint = " (found lifecycle.freshness: move freshness to the top level)"

    dates = {}
    for key in ("last_reviewed", "stale_after"):
        name = f"freshness.{key}"
        raw = doc.get(name)
        if raw is MISSING or raw is None:
            error(name, f"Field is required, format YYYY-MM-DD{hint}")
            continue
        value = as_date(raw)
        if value is None:
            error(name, f"Value {_show(raw)} is not a valid date, expected YYYY-MM-DD")
        else:
            dates[key] = value

    if len(dates) == 2 and dates["stale_after"] < dates["last_reviewed"]:
        error(
            "freshness.stale_after",
            f"Date {dates['stale_after']} is earlier than freshness.last_reviewed {dates['last_reviewed']}",
        )


def check_links(bundle: Bundle) -> dict[Path, list[Issue]]:
    """Broken links and orphan documents, both warnings. AGENTS.md links do not count."""
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

    for doc in bundle.knowledge():
        if not incoming[_key(doc.path)]:
            result[doc.path].append(
                Issue(WARNING, doc.path, "link", "Orphan file: no other file in the bundle links to it", 1)
            )
    return result


def _key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _show(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _suggest_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    def squash(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    for allowed in ALLOWED_TYPES:
        if squash(allowed) == squash(value):
            return allowed
    close = difflib.get_close_matches(value, ALLOWED_TYPES, n=1, cutoff=0.6)
    return close[0] if close else None
