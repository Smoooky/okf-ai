"""`okf notify`: remind the people who confirmed a section that it needs a recheck.

Units "to recheck" are grouped by who confirmed them last (`verified[].by`); each person gets one
message with every unit, the reason, a link to the line on GitHub and the one command that confirms
them all after reading (`okf verify …`). Units nobody confirmed yet go to one message for the channel.
Slack and Microsoft Teams take incoming webhooks; `--dry-run` prints the messages instead.

Webhook URLs are secrets: they are never printed, errors name only the HTTP status.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from okf import __version__
from okf.sources.http import HttpFailure, fetch
from okf.bundle import relative_path as _relative
from okf.git import line_url
from okf.trust import TrustMap, Unit

NOBODY = "nobody yet"


class NotifyError(RuntimeError):
    pass


@dataclass
class Reminder:
    who: str  # the last verifier, or NOBODY
    units: list[Unit] = field(default_factory=list)


def reminders(trust_map: TrustMap) -> list[Reminder]:
    groups: dict[str, Reminder] = {}
    for unit in trust_map.units:
        if unit.level != "recheck":
            continue
        who = max(unit.verifications)[1] if unit.verifications else NOBODY
        groups.setdefault(who, Reminder(who)).units.append(unit)
    return sorted(groups.values(), key=lambda r: (r.who == NOBODY, r.who))


def verify_command(units: list[Unit], root: Path) -> str:
    names = [_relative(u.path, root) + (f"#{u.section}" if u.section else "") for u in units]
    return "okf verify " + " ".join(f'"{n}"' for n in names)


def _link(unit: Unit, web: str | None, git_root: Path | None) -> str | None:
    return line_url(web, git_root, unit.path, unit.line)


def slack_message(reminder: Reminder, root: Path, web: str | None, git_root: Path | None,
                  people: dict | None = None) -> dict:
    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    slack_id = ((people or {}).get(reminder.who) or {}).get("slack")
    who = f"<@{slack_id}>" if slack_id else f"*{esc(reminder.who)}*"
    count = len(reminder.units)
    head = (f"{who}, {count} {'section' if count == 1 else 'sections'} you confirmed need a recheck"
            if reminder.who != NOBODY else f"{count} never confirmed {'section needs' if count == 1 else 'sections need'}"
                                          " a recheck")
    lines = [f":mag: okf-ai: {head}"]
    for unit in reminder.units:
        link = _link(unit, web, git_root)
        name = f"<{link}|{esc(unit.name)}>" if link else f"`{esc(unit.name)}`"
        lines.append(f"• {name}: {esc(unit.message)}")
    lines.append(f"After reading, confirm in one command: `{esc(verify_command(reminder.units, root))}`")
    return {"text": "\n".join(lines)}


def teams_message(reminder: Reminder, root: Path, web: str | None, git_root: Path | None) -> dict:
    """An Adaptive Card, the format Teams Workflows webhooks take."""
    count = len(reminder.units)
    title = (f"{reminder.who}: {count} {'section' if count == 1 else 'sections'} you confirmed need a recheck"
             if reminder.who != NOBODY else f"{count} never confirmed sections need a recheck")
    body = [{"type": "TextBlock", "text": f"okf-ai: {title}", "weight": "Bolder", "wrap": True}]
    for unit in reminder.units:
        link = _link(unit, web, git_root)
        name = f"[{unit.name}]({link})" if link else unit.name
        body.append({"type": "TextBlock", "text": f"- {name}: {unit.message}", "wrap": True})
    body.append({"type": "TextBlock", "text": "After reading, confirm in one command:", "wrap": True})
    body.append({"type": "TextBlock", "text": verify_command(reminder.units, root), "fontType": "Monospace",
                 "wrap": True})
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard",
            "version": "1.4", "body": body}
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
                                                "content": card}]}


def plain(message: dict) -> str:
    """What --dry-run prints."""
    if "text" in message:
        return message["text"]
    blocks = message["attachments"][0]["content"]["body"]
    return "\n".join(block["text"] for block in blocks)


def load_people(path: Path) -> dict:
    """.okf/people.yml: `human:ivan: {slack: U0123ABC}` to mention people in Slack."""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def send(url: str, message: dict, retries: int = 3, sleep=time.sleep, timeout: float = 10) -> None:
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8", "User-Agent": f"okf-ai/{__version__}"})
    try:
        fetch(request, timeout, retries, sleep)
    except HttpFailure as failure:
        if failure.status is not None:
            raise NotifyError(f"the webhook answered HTTP {failure.status}") from None
        raise NotifyError(f"cannot reach the webhook: {type(failure.reason).__name__}") from None
