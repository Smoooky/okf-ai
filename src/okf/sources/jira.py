"""Jira issues as sources: a closed epic asks the documents that rely on it to be rechecked.

Resources: https://<site>.atlassian.net/browse/<KEY-123> (or any host with /browse/<KEY-123>)
and jira://<KEY-123>.

Settings: OKF_JIRA_URL, and OKF_ATLASSIAN_EMAIL + OKF_ATLASSIAN_TOKEN (Cloud, REST v3) or
OKF_ATLASSIAN_PAT (Server/DC, REST v2).

`last_modified` is `fields.updated`, but every comment moves it, so the trust signal is the
moment the issue reached a done status (from the changelog), and nothing while it is open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from okf.sources.base import Signal, Source, Unavailable, day, not_configured, parse_time
from okf.sources.http import atlassian_headers

_KEY = r"[A-Z][A-Z0-9_]*-\d+"
SETTINGS = "OKF_JIRA_URL"  # credentials: OKF_ATLASSIAN_EMAIL + OKF_ATLASSIAN_TOKEN, or OKF_ATLASSIAN_PAT
FIELDS = "summary,status,updated,resolutiondate,issuetype"


@dataclass
class Issue:
    key: str
    summary: str
    kind: str  # "epic", "task", ...
    status: str
    done: bool
    updated: datetime | None
    resolved: datetime | None
    history: list[tuple[datetime, str, str, str, str]] = field(default_factory=list)  # (at, who, field, from, to)

    @property
    def closed_at(self) -> datetime | None:
        """When it reached the done status it is in now, if it is done."""
        if not self.done:
            return None
        moves = [at for at, _, name, _, _ in self.history if name == "status"]
        return max(moves, default=None) or self.resolved or self.updated


def issue_ref(resource: str) -> tuple[str | None, str] | None:
    """(host or None, issue key) of a Jira issue resource, else None."""
    resource = resource.strip()
    match = re.match(rf"^jira:(?://)?({_KEY})/?$", resource)
    if match:
        return None, match.group(1)
    parts = urlsplit(resource)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    match = re.search(rf"/browse/({_KEY})/?$", parts.path)
    return (parts.netloc.lower(), match.group(1)) if match else None


class JiraSource(Source):
    name = "jira"
    settings = SETTINGS

    def __init__(self, env, http=None):
        super().__init__(env, http)
        self.base = (env.get("OKF_JIRA_URL") or "").strip().rstrip("/")
        self.host = urlsplit(self.base).netloc.lower()
        self.api = "3" if self.host.endswith(".atlassian.net") else "2"
        self._issues: dict[str, Issue] = {}

    def matches(self, resource: str) -> bool:
        return issue_ref(resource) is not None

    def unconfigured(self) -> str | None:
        return None if self.base else not_configured(self.settings)

    def problem(self, resource: str) -> str | None:
        if not self.base:
            return self.unconfigured()
        host = issue_ref(resource)[0]
        if host and host != self.host:
            return f"OKF_JIRA_URL is {self.host}, not {host}"
        return None

    def last_modified(self, resource: str) -> datetime | None:
        return self.issue(resource).updated

    def describe(self, resource: str) -> str:
        key = issue_ref(resource)[1]
        issue = self._issues.get(key)
        return f'Jira {issue.kind} {key} "{issue.summary}" ({issue.status})' if issue else f"Jira issue {key}"

    def signal(self, resource: str) -> Signal | None:
        issue = self.issue(resource)
        closed = issue.closed_at
        return Signal(closed, f"{issue.kind} {issue.key}", "closed", "recheck:closed") if closed else None

    def changes_since(self, resource: str, since: datetime) -> str | None:
        issue = self.issue(resource)
        moves = [entry for entry in issue.history if entry[0] > since]
        if not moves:
            return None
        lines = [f'Jira {issue.kind} {issue.key} "{issue.summary}", now {issue.status}; changes since {day(since)}:']
        for at, who, name, old, new in sorted(moves):
            lines.append(f"- {day(at)} {who}: {name}: {old or '(empty)'} -> {new or '(empty)'}")
        return "\n".join(lines)

    def issue(self, resource: str) -> Issue:
        key = issue_ref(resource)[1]
        if key not in self._issues:
            data = self._get(f"/rest/api/{self.api}/issue/{key}?fields={FIELDS}&expand=changelog")
            if not isinstance(data, dict) or not isinstance(data.get("fields"), dict):
                raise Unavailable(f"Jira {key}: unexpected answer")
            histories = list((data.get("changelog") or {}).get("histories") or [])
            total = (data.get("changelog") or {}).get("total")
            if self.api == "3" and isinstance(total, int) and total > len(histories):
                # Cloud returns only part of a long changelog with the issue: read its latest page
                page = self._get(f"/rest/api/3/issue/{key}/changelog?startAt={max(total - 100, 0)}&maxResults=100")
                histories += page.get("values") or []
            self._issues[key] = _issue(key, data["fields"], histories)
        return self._issues[key]

    def _get(self, path: str):
        return self.http.get_json(self.base + path, atlassian_headers(self.env))


def _issue(key: str, fields: dict, histories: list) -> Issue:
    status = fields.get("status") or {}
    category = (status.get("statusCategory") or {}).get("key")
    kind = ((fields.get("issuetype") or {}).get("name") or "issue").lower()
    entries, seen = [], set()
    for history in histories:
        if not isinstance(history, dict) or history.get("id") in seen:
            continue
        seen.add(history.get("id"))
        at = parse_time(history.get("created"))
        who = (history.get("author") or {}).get("displayName") or "someone"
        for item in history.get("items") or []:
            if at and isinstance(item, dict):
                entries.append((at, who, str(item.get("field") or ""), item.get("fromString") or "",
                                item.get("toString") or ""))
    return Issue(key, str(fields.get("summary") or key), kind, str(status.get("name") or "?"), category == "done",
                 parse_time(fields.get("updated")), parse_time(fields.get("resolutiondate")), sorted(entries))
