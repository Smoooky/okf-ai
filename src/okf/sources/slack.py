"""Pinned Slack messages as sources: a decision pinned in a channel that a document relies on.

Resources: slack://<channel>/<ts> (e.g. slack://C0123ABCD/1729500000.123456) and permalinks
https://<workspace>.slack.com/archives/<channel>/p<ts without the dot>.

Settings: OKF_SLACK_TOKEN (a bot token with channels:history, groups:history and pins:read; the bot
must be in the channel). The trust signal: the message was edited (`edited.ts`) after the document
was checked, or it is no longer pinned or no longer there. Slack does not say when a message was
unpinned, so an unpinned message asks for a recheck until the document stops relying on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from okf.sources.base import Signal, Source, Unavailable, day, not_configured

API = "https://slack.com/api"


@dataclass
class Message:
    channel: str
    ts: str
    text: str
    edited: datetime | None
    pinned: bool
    exists: bool

    @property
    def posted(self) -> datetime:
        return _time(self.ts)


def message_ref(resource: str) -> tuple[str, str] | None:
    """(channel id, message ts) of a Slack message resource, else None."""
    resource = resource.strip()
    match = re.match(r"^slack://([A-Z0-9]+)/(\d{9,11}\.\d{6})/?$", resource)
    if match:
        return match.group(1), match.group(2)
    parts = urlsplit(resource)
    if parts.scheme != "https" or not parts.netloc.lower().endswith(".slack.com"):
        return None
    match = re.match(r"^/archives/([A-Z0-9]+)/p(\d{9,11})(\d{6})/?$", parts.path)
    return (match.group(1), f"{match.group(2)}.{match.group(3)}") if match else None


class SlackSource(Source):
    name = "slack"
    settings = "OKF_SLACK_TOKEN"

    def __init__(self, env, http=None, now=None):
        super().__init__(env, http)
        self.token = (env.get("OKF_SLACK_TOKEN") or "").strip()
        self.base = (env.get("OKF_SLACK_API_URL") or API).rstrip("/")
        self.now = now or datetime.now(timezone.utc)
        self._messages: dict[tuple[str, str], Message] = {}
        self._pins: dict[str, set[str]] = {}

    def matches(self, resource: str) -> bool:
        return message_ref(resource) is not None

    def unconfigured(self) -> str | None:
        return None if self.token else not_configured(self.settings)

    def last_modified(self, resource: str) -> datetime | None:
        message = self.message(resource)
        return message.edited or message.posted

    def describe(self, resource: str) -> str:
        channel, ts = message_ref(resource)
        return f"Slack message {ts} in {channel}"

    def signal(self, resource: str) -> Signal | None:
        message = self.message(resource)
        if not message.exists:
            return Signal(self.now, self.describe(resource), "is gone, seen", "recheck:source-gone")
        if not message.pinned:
            return Signal(self.now, self.describe(resource), "is no longer pinned, seen", "recheck:unpinned")
        if message.edited:
            return Signal(message.edited, self.describe(resource), "was edited", "recheck:source-changed")
        return None

    def changes_since(self, resource: str, since: datetime) -> str | None:
        message = self.message(resource)
        if not message.exists:
            return f"{self.describe(resource)} was deleted; nothing to compare."
        notes = []
        if not message.pinned:
            notes.append("it is no longer pinned")
        if message.edited and message.edited > since:
            notes.append(f"it was edited {day(message.edited)} (Slack keeps no earlier text)")
        if not notes:
            return None
        return f"{self.describe(resource)}: {'; '.join(notes)}. Its text now:\n{message.text}"

    # --- Web API ------------------------------------------------------------------

    def message(self, resource: str) -> Message:
        channel, ts = message_ref(resource)
        key = (channel, ts)
        if key not in self._messages:
            data = self._get(f"/conversations.history?channel={quote(channel)}&latest={ts}&inclusive=true&limit=1")
            found = next((m for m in data.get("messages") or [] if m.get("ts") == ts), None)
            if channel not in self._pins:
                pins = self._get(f"/pins.list?channel={quote(channel)}")
                self._pins[channel] = {str((item.get("message") or {}).get("ts")) for item in pins.get("items") or []}
            edited = (found or {}).get("edited") or {}
            self._messages[key] = Message(channel, ts, (found or {}).get("text") or "",
                                          _time(edited["ts"]) if edited.get("ts") else None,
                                          ts in self._pins[channel], found is not None)
        return self._messages[key]

    def _get(self, path: str) -> dict:
        data = self.http.get_json(self.base + path, {"Authorization": f"Bearer {self.token}"})
        if not isinstance(data, dict):
            raise Unavailable("Slack: unexpected answer")
        if not data.get("ok"):
            error = data.get("error") or "unknown error"
            hint = {"not_in_channel": ": invite the bot to the channel",
                    "invalid_auth": ": check OKF_SLACK_TOKEN", "not_authed": ": check OKF_SLACK_TOKEN",
                    "missing_scope": ": the token needs channels:history, groups:history and pins:read"}.get(error, "")
            raise Unavailable(f"Slack: {error}{hint}")
        return data


def _time(ts: str) -> datetime:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc)
