"""Connectors to where `sources` live, and the registry that picks one for a resource.

To add a connector: write okf/sources/<name>.py with a `Source` subclass (see base.py) and add
the class to CONNECTORS. The first connector whose `matches` accepts a resource serves it; git
comes last and takes every path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from okf.bundle import SCHEME_RE
from okf.git import History
from okf.sources.base import Check, Signal, Source, Unavailable
from okf.sources.confluence import ConfluenceSource
from okf.sources.git import GitSource
from okf.sources.http import Http
from okf.sources.jira import JiraSource
from okf.sources.notion import NotionSource

CONNECTORS: list[type[Source]] = [ConfluenceSource, JiraSource, NotionSource]

__all__ = ["CONNECTORS", "Check", "GitSource", "Registry", "Signal", "Source", "Unavailable", "registry"]


class Registry:
    def __init__(self, connectors: list[Source], git: GitSource | None = None):
        self.connectors = connectors
        self.git = git or GitSource()
        self._checks: dict[str, Check] = {}

    def find(self, resource: str) -> Source | None:
        """The connector of a resource: a remote one, else git for a path; None for an URL nobody serves."""
        for connector in self.connectors:
            if connector.matches(resource):
                return connector
        return self.git if self.git.matches(resource) else None

    def check(self, resource: str) -> Check:
        """Status, date and signal of a remote resource. Never raises: what cannot be read is "unknown"."""
        if resource not in self._checks:
            self._checks[resource] = self._check(resource)
        return self._checks[resource]

    def _check(self, resource: str) -> Check:
        connector = self.find(resource)
        if connector is None or connector is self.git:
            host = urlsplit(resource).netloc if SCHEME_RE.match(resource) else ""
            return Check(resource, None, "unknown", f"no connector for {host or resource}")
        problem = connector.problem(resource)
        if problem:
            return Check(resource, connector.name, "unknown", problem)
        try:
            signal = connector.signal(resource)
            modified = connector.last_modified(resource)
            return Check(resource, connector.name, "ok", connector.describe(resource), modified, signal)
        except Unavailable as exc:
            return Check(resource, connector.name, "unknown", f"{connector.describe(resource)}: {exc}")

    def changes_since(self, resource: str, since) -> str | None:
        connector = self.find(resource)
        if connector is None or connector is self.git or connector.problem(resource):
            return None
        try:
            return connector.changes_since(resource, since)
        except Unavailable as exc:
            return f"({connector.describe(resource)}: {exc})"


def registry(env: Mapping[str, str] | None = None, root: Path | None = None, history: History | None = None,
             http: Http | None = None) -> Registry:
    """Connectors configured from the environment (os.environ by default). Without settings none of
    them touches the network."""
    env = os.environ if env is None else env
    http = http or Http(env)
    connectors = [cls(env, http) for cls in CONNECTORS]
    for connector in connectors:
        connector.root = Path(root).resolve() if root else None
    return Registry(connectors, GitSource(root, history))
