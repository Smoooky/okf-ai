"""The connector interface: what okf needs to know about a `sources[].resource`.

A connector recognizes the resources it serves (`matches`) and answers, for one of them:
when it last changed (`last_modified`), what changed since a moment (`changes_since`, the
text `okf fix --draft` shows the model), and how to name it (`describe`). `signal` is the
change that asks every document relying on the resource to be rechecked; by default the last
modification, the Jira connector overrides it (a closed epic, not every comment).

A connector that is not configured, or cannot reach its service, never makes a document
broken: the resource is "unknown" and the reason says what to set or what went wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


class Unavailable(Exception):
    """The resource cannot be read now (no access, not found, rate limits, network): status unknown."""


@dataclass(frozen=True)
class Signal:
    """A change of a resource that asks documents relying on it to be rechecked."""

    at: datetime
    subject: str  # 'Confluence page "Тарифы" (v14)', "epic WHL-42"
    verb: str = "changed"  # the trust map says "<subject> <verb> <day>"
    reason: str = "recheck:source-changed"


@dataclass
class Check:
    """What the trust map and `okf stale` learn about one resource."""

    resource: str
    connector: str | None  # None: no connector knows this kind of resource
    status: str  # "ok" or "unknown"
    message: str  # describe() if ok, else why it is unknown
    last_modified: datetime | None = None
    signal: Signal | None = None

    @property
    def actionable(self) -> bool:
        """Unknown for a reason the user can fix: a connector exists but is not set up or failed."""
        return self.status == "unknown" and self.connector is not None


class Source:
    """Base class of a connector. Subclass it in one file under okf/sources/ and add it to CONNECTORS."""

    name = ""  # short id: "confluence", "jira"
    settings = ""  # what to set, shown in "connector not configured: <settings>"
    root = None  # the repository root, for connectors that keep files in it (Notion snapshots)

    def __init__(self, env: Mapping[str, str], http=None):
        self.env = env
        self.http = http

    def matches(self, resource: str) -> bool:
        raise NotImplementedError

    def unconfigured(self) -> str | None:
        """What the settings lack for this connector to work, or None."""
        return None

    def problem(self, resource: str) -> str | None:
        """Why this resource cannot be checked without touching the network, or None if it can."""
        return self.unconfigured()

    def last_modified(self, resource: str) -> datetime | None:
        raise NotImplementedError

    def changes_since(self, resource: str, since: datetime) -> str | None:
        """A diff or a short account of what changed after `since`, or None if nothing did."""
        raise NotImplementedError

    def describe(self, resource: str) -> str:
        return resource

    def signal(self, resource: str) -> Signal | None:
        at = self.last_modified(resource)
        return Signal(at, self.describe(resource)) if at else None


def not_configured(settings: str) -> str:
    return f"connector not configured: set {settings}"


def parse_time(value) -> datetime | None:
    """Atlassian timestamps: 2026-10-12T14:03:00.000+0300, 2026-10-12T11:03:00Z, ...; UTC if no offset."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    text = re.sub(r"[zZ]$", "+00:00", text)
    text = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", text)
    text = re.sub(r"\.(\d{1,6})\d*(?=[+-]\d\d:\d\d$|$)", lambda m: "." + m.group(1).ljust(6, "0"), text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def day(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).date().isoformat()
