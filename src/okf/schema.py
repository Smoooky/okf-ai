"""OKF v0.2 front matter: every field name and rule lives here.

Two validation profiles:

- `okf` (default): conformance with OKF v0.2,
  https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md
- `strict`: the okf-ai team rules on top of it, see etc/spec/cli-validator-v2.md.

The field readers below (`sources`, `trust_tier`, `stale_after`, ...) are shared
by `okf validate`, `okf stale` and `okf agents`.
"""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Callable

from okf.report import ERROR, WARNING, Issue
from okf.values import MISSING, describe, parse_instant, show

if TYPE_CHECKING:
    from okf.bundle import Document

# §3.1: reserved at any level of the bundle, never concepts.
RESERVED_FILES = ("index.md", "log.md")
# Written by `okf agents` into the bundle root; not validated, its links do not count.
GENERATED_FILES = ("AGENTS.md",)
# §8, §12: the only key a bundle-root index.md may carry.
ROOT_INDEX_KEYS = ("okf_version",)
OKF_VERSION = "0.2"
# §5.4
STATUSES = ("draft", "stable", "deprecated")
DEFAULT_STATUS = "stable"
ATTESTED_COMPUTATION = "Attested Computation"
# stale_after within this window: "review due" in the router, "через N дней" highlighted in okf view.
REVIEW_WINDOW = timedelta(days=30)

# Appendix 2 of etc/spec/cli-validator.md. Strict profile only, and only a warning:
# OKF consumers must tolerate unknown types (§4.1).
TEAM_TYPES = (
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
    ATTESTED_COMPUTATION,  # defined by OKF itself (§10)
)

HUMAN_PREFIX = "human:"
# §7: human:<id>, process:<id>, or <producer>/<version> for agents and tools.
_ACTOR_RE = re.compile(r"^(?:human:\S+|process:\S+|[^\s/:]+/[^\s/]+)$")
_INSTANT_EXAMPLE = "2026-06-30T14:00:00Z"
_LOG_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)

Report = Callable[[str, str], None]


# --- Reading fields -----------------------------------------------------------


def sources(doc: Document) -> list[str]:
    """`sources[].resource` values of well-formed entries."""
    value = doc.get("sources", None)
    if not isinstance(value, list):
        return []
    return [
        entry["resource"].strip()
        for entry in value
        if isinstance(entry, dict) and isinstance(entry.get("resource"), str) and entry["resource"].strip()
    ]


def generated_by(doc: Document) -> str | None:
    value = doc.get("generated", None)
    by = value.get("by") if isinstance(value, dict) else None
    return by.strip() if isinstance(by, str) and by.strip() else None


def verifications(doc: Document) -> list[dict]:
    """`verified` as a list; a bare mapping is a one-element list (§5.2)."""
    value = doc.get("verified", None)
    entries = [value] if isinstance(value, dict) else value if isinstance(value, list) else []
    return [entry for entry in entries if isinstance(entry, dict)]


def latest_verification(doc: Document) -> tuple[datetime, str] | None:
    """(instant, value as written) of the most recent `verified[].at`."""
    latest = None
    for entry in verifications(doc):
        at = parse_instant(entry.get("at"))
        if at is not None and (latest is None or at > latest[0]):
            latest = (at, entry["at"])
    return latest


def is_actor(value: object) -> bool:
    """§7: human:<id>, process:<id> or <producer>/<version>."""
    return isinstance(value, str) and bool(_ACTOR_RE.match(value.strip()))


def is_human(actor: object) -> bool:
    return isinstance(actor, str) and actor.strip().startswith(HUMAN_PREFIX)


def trust_tier(doc: Document) -> str:
    """§5.3: unverified, machine-confirmed or human-reviewed."""
    entries = verifications(doc)
    if not entries:
        return "unverified"
    return "human-reviewed" if any(is_human(entry.get("by")) for entry in entries) else "machine-confirmed"


def status(doc: Document) -> str:
    value = doc.get("status", None)
    return value.strip() if isinstance(value, str) and value.strip() else DEFAULT_STATUS


def tags(doc: Document) -> list[str]:
    """`tags` as a list: a YAML list, or the `a, b` string official bundles also use."""
    value = doc.get("tags", None)
    if isinstance(value, str):
        value = [t.strip() for t in value.split(",")]
    return [str(t) for t in value if str(t).strip()] if isinstance(value, list) else []


def stale_after(doc: Document) -> datetime | None:
    return parse_instant(doc.get("stale_after", None))


def reviewer(doc: Document) -> str | None:
    """Who to ask about a document: the latest human verifier, else a human author."""
    humans = [entry for entry in verifications(doc) if is_human(entry.get("by"))]
    if humans:
        humans.sort(key=lambda entry: parse_instant(entry.get("at")) or _EPOCH)
        return humans[-1]["by"].strip()
    author = generated_by(doc)
    return author if is_human(author) else None


# --- Validation profiles ------------------------------------------------------


class Profile:
    """OKF v0.2 conformance (§4–§9, §11): only `type` is required; present families must be well-formed."""

    name = "okf"
    report_orphans = False
    # §4.1 asks for a YAML list, but official bundles ship `tags: a, b` strings: soft guidance here.
    tags_level = WARNING

    def check_concept(self, doc: Document) -> list[Issue]:
        """Rules for a concept whose front matter parsed into a mapping."""
        issues: list[Issue] = []
        error, warning = _reporter(issues, doc, ERROR), _reporter(issues, doc, WARNING)
        self._check_type(doc, error)
        self._check_tags(doc, _reporter(issues, doc, self.tags_level))
        self._check_sources(doc, error)
        self._check_trust(doc, error)
        self._check_lifecycle(doc, error)
        self._check_computation(doc, error)
        self.check_extra(doc, error, warning)
        return issues

    def check_extra(self, doc: Document, error: Report, warning: Report) -> None:
        """Hook for profiles that add rules."""

    def check_index(self, doc: Document, at_root: bool) -> list[Issue]:
        if not doc.has_front_matter:
            return []
        if doc.meta is None:
            return [Issue(ERROR, doc.path, "frontmatter", doc.meta_error, doc.meta_error_line)]
        if not at_root:
            return [Issue(ERROR, doc.path, "frontmatter", "index.md must not contain YAML front matter "
                          "(only the bundle-root index.md may declare okf_version)", 1)]
        extra = [str(key) for key in doc.meta if key not in ROOT_INDEX_KEYS]
        if extra:
            return [Issue(ERROR, doc.path, "frontmatter", "Bundle-root index.md front matter may only contain "
                          f"okf_version, found: {', '.join(extra)}", 1)]
        version = doc.meta.get("okf_version")
        if version is not None and str(version) != OKF_VERSION:
            return [Issue(WARNING, doc.path, "okf_version", f"Bundle declares OKF {version}; "
                          f"okf validates against {OKF_VERSION}", doc.field_line("okf_version"))]
        return []

    def check_log(self, doc: Document) -> list[Issue]:
        issues = []
        if doc.has_front_matter and doc.meta is None:
            issues.append(Issue(ERROR, doc.path, "frontmatter", doc.meta_error, doc.meta_error_line))
        for heading, line in doc.headings(level=2):
            if not _LOG_DATE_RE.match(heading) or _bad_date(heading):
                issues.append(Issue(WARNING, doc.path, "log", f'Date heading "{heading}" must use YYYY-MM-DD', line))
        return issues

    def _check_type(self, doc: Document, error: Report) -> None:
        value = doc.get("type")
        if value is MISSING:
            error("type", "Field is required")
        elif value is None or (isinstance(value, str) and not value.strip()):
            error("type", "Field must not be empty")
        elif not isinstance(value, str):
            error("type", f"Must be a string, got {describe(value)}")

    def _check_tags(self, doc: Document, report: Report) -> None:
        tags = doc.get("tags")
        if tags is MISSING or tags is None:
            return
        if not isinstance(tags, list):
            report("tags", f"Must be a YAML list of strings like [a, b], got {describe(tags)}")
        elif not all(isinstance(tag, str) for tag in tags):
            report("tags", "Must be a YAML list of strings, got a list with non-string items")

    def _check_sources(self, doc: Document, error: Report) -> None:
        value = doc.get("sources")
        if value is not MISSING:
            if not isinstance(value, list):
                error("sources", f"Must be a list of entries like {{resource: ...}}, got {describe(value)}")
                value = []
            for i, entry in enumerate(value):
                name = f"sources[{i}]"
                if not isinstance(entry, dict):
                    error(name, f"Entry must be a mapping like {{resource: ...}}, got {describe(entry)} {show(entry)}")
                    continue
                resource = entry.get("resource")
                if resource is None or (isinstance(resource, str) and not resource.strip()):
                    error(f"{name}.resource", "Field is required in every sources entry")
                elif not isinstance(resource, str):
                    error(f"{name}.resource", f"Must be a URL or a path, got {describe(resource)}")
                if "last_modified" in entry:
                    _check_instant(entry["last_modified"], f"{name}.last_modified", error)
                if "usage_window" in entry:
                    _check_window(entry["usage_window"], f"{name}.usage_window", error)
        if doc.get("usage_window") is not MISSING:
            _check_window(doc.get("usage_window"), "usage_window", error)

    def _check_trust(self, doc: Document, error: Report) -> None:
        generated = doc.get("generated")
        if generated is not MISSING:
            if not isinstance(generated, dict):
                error("generated", f"Must be a mapping like {{by: <actor>, at: <datetime>}}, got {describe(generated)}")
            else:
                if _blank(generated.get("by")):
                    error("generated.by", "Field is required in generated")
                else:
                    _check_actor(generated["by"], "generated.by", error)
                if "at" in generated:
                    _check_instant(generated["at"], "generated.at", error)

        verified = doc.get("verified")
        if verified is MISSING:
            return
        if not isinstance(verified, (dict, list)):
            error("verified", f"Must be a {{by, at}} mapping or a list of them, got {describe(verified)}")
            return
        bare = isinstance(verified, dict)
        for i, entry in enumerate([verified] if bare else verified):
            name = "verified" if bare else f"verified[{i}]"
            if not isinstance(entry, dict):
                error(name, f"Entry must be a mapping like {{by: <actor>, at: <datetime>}}, got {describe(entry)}")
                continue
            if _blank(entry.get("by")):
                error(f"{name}.by", "Field is required in every verified entry")
            else:
                _check_actor(entry["by"], f"{name}.by", error)
            if _blank(entry.get("at")):
                error(f"{name}.at", "Field is required in every verified entry")
            else:
                _check_instant(entry["at"], f"{name}.at", error)

    def _check_lifecycle(self, doc: Document, error: Report) -> None:
        value = doc.get("status")
        if value is not MISSING and value not in STATUSES:
            error("status", f"Value {show(value)} must be one of {', '.join(STATUSES)}")
        if doc.get("stale_after") is not MISSING:
            _check_instant(doc.get("stale_after"), "stale_after", error)

    def _check_computation(self, doc: Document, error: Report) -> None:
        if doc.get("type") == ATTESTED_COMPUTATION and _blank(doc.get("runtime", None)):
            error("runtime", f"Field is required for type {ATTESTED_COMPUTATION}")


class StrictProfile(Profile):
    """okf-ai team rules (etc/spec/cli-validator-v2.md), expressed in OKF v0.2 fields."""

    name = "strict"
    report_orphans = True
    tags_level = ERROR

    def check_extra(self, doc: Document, error: Report, warning: Report) -> None:
        kind = doc.get("type")
        if isinstance(kind, str) and kind.strip() and kind not in TEAM_TYPES:
            message = f"Value {show(kind)} is not in the okf-ai type dictionary"
            suggestion = _suggest_type(kind)
            warning("type", message + (f' (did you mean "{suggestion}"?)' if suggestion else ""))

        if doc.get("sources") in (MISSING, None, []):
            hint = " (found provenance.sources: OKF v0.2 uses top-level sources)" if _has(doc, "provenance") else ""
            error("sources", "List at least one source, e.g. - resource: /src/auth.py" + hint)

        if doc.get("verified") in (MISSING, None, []):
            hint = " (found trust.verified_by: OKF v0.2 uses verified)" if _has(doc, "trust") else ""
            error("verified", "Field is required: record the review, e.g. {by: human:<id>, at: <datetime>}" + hint)

        if doc.get("stale_after") in (MISSING, None):
            hint = " (found freshness.stale_after: OKF v0.2 uses top-level stale_after)" if _has(doc, "freshness") else ""
            error("stale_after", f"Field is required, e.g. {_INSTANT_EXAMPLE}" + hint)
        else:
            expires, latest = stale_after(doc), latest_verification(doc)
            if expires is not None and latest is not None and expires < latest[0]:
                error("stale_after", f"{doc.get('stale_after')} is earlier than the latest verified.at {latest[1]}")

        author = generated_by(doc)
        entries = verifications(doc)
        if (
            author
            and not is_human(author)
            and status(doc) == "stable"
            and entries
            and not any(is_human(entry.get("by")) for entry in entries)
        ):
            error(
                "verified",
                f'Document generated by "{author}" is status: stable without human review; '
                "add a human:<id> entry to verified or set status: draft",
            )

    def check_log(self, doc: Document) -> list[Issue]:
        issues = super().check_log(doc)
        if doc.has_front_matter and doc.meta is not None:
            issues.insert(0, Issue(ERROR, doc.path, "frontmatter", "log.md must not contain YAML front matter", 1))
        return issues


PROFILES = {"okf": Profile(), "strict": StrictProfile()}


def get_profile(strict: bool = False) -> Profile:
    return PROFILES["strict" if strict else "okf"]


# --- Helpers ------------------------------------------------------------------


def _reporter(issues: list[Issue], doc: Document, level: str) -> Report:
    def report(name: str, message: str) -> None:
        issues.append(Issue(level, doc.path, name, message, doc.field_line(name)))

    return report


def _blank(value: object) -> bool:
    return value is None or value is MISSING or (isinstance(value, str) and not value.strip())


def _has(doc: Document, key: str) -> bool:
    return doc.get(key) is not MISSING


def _check_actor(value: object, name: str, error: Report) -> None:
    if not isinstance(value, str) or not _ACTOR_RE.match(value.strip()):
        error(name, f"Actor {show(value)} must be human:<id>, process:<id> or <producer>/<version>")


def _check_instant(value: object, name: str, error: Report) -> None:
    if parse_instant(value) is None:
        error(name, f"Value {show(value)} must be an ISO 8601 datetime with a UTC offset, e.g. {_INSTANT_EXAMPLE}")


def _check_window(value: object, name: str, error: Report) -> None:
    if not isinstance(value, dict):
        error(name, f"Must be a mapping like {{from: <datetime>, to: <datetime>}}, got {describe(value)}")
        return
    for key in ("from", "to"):
        if _blank(value.get(key)):
            error(f"{name}.{key}", "Field is required")
        else:
            _check_instant(value[key], f"{name}.{key}", error)


def _bad_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return True
    return False


def _suggest_type(value: str) -> str | None:
    def squash(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    for allowed in TEAM_TYPES:
        if squash(allowed) == squash(value):
            return allowed
    close = difflib.get_close_matches(value, TEAM_TYPES, n=1, cutoff=0.6)
    return close[0] if close else None
