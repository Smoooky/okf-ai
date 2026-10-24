"""Notion pages as sources: when a page was edited, its text, and `okf import notion`.

Resources: https://www.notion.so/<slug>-<id> (also <workspace>.notion.site and notion.so/<workspace>/…)
and notion://<id>, the id being 32 hex digits with or without dashes.

Settings: OKF_NOTION_TOKEN (an internal integration secret; share the pages with the integration).
`last_modified` is the page's `last_edited_time`. `changes_since` compares the text of the page and
its child blocks (all pages of them) with the snapshot `okf import notion` saved in
.okf/snapshots/notion/<id>.md, when there is one; otherwise it says the page was edited after the check.
The API allows about three requests a second: requests are spaced, and 429 waits for Retry-After.
"""

from __future__ import annotations

import difflib
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from okf.sources.base import Signal, Source, Unavailable, day, not_configured, parse_time

API = "https://api.notion.com"
VERSION = "2022-06-28"
MIN_INTERVAL = 0.34  # seconds between requests: ~3 a second
SNAPSHOTS = Path(".okf") / "snapshots" / "notion"
_ID = re.compile(r"([0-9a-f]{32})$|([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.I)


@dataclass
class NotionPage:
    id: str
    title: str
    url: str
    at: datetime | None
    text: str  # Markdown of the blocks
    children: list[tuple[str, str]]  # (id, title) of child pages


def page_id(resource: str) -> str | None:
    """The page id as a dashed UUID, from a notion.so / notion.site URL or notion://<id>, else None."""
    resource = resource.strip()
    if resource.lower().startswith("notion:"):
        tail = re.sub(r"^notion:(//)?", "", resource, flags=re.I).strip("/")
    else:
        parts = urlsplit(resource)
        host = parts.netloc.lower()
        if parts.scheme not in ("http", "https") or not (host in ("notion.so", "www.notion.so")
                                                           or host.endswith(".notion.site")):
            return None
        tail = parts.path.rstrip("/").rsplit("/", 1)[-1]
    match = _ID.search(tail)
    if not match:
        return None
    raw = (match.group(1) or match.group(2)).replace("-", "").lower()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


class NotionSource(Source):
    name = "notion"
    settings = "OKF_NOTION_TOKEN"

    def __init__(self, env, http=None, sleep=time.sleep, clock=time.monotonic):
        super().__init__(env, http)
        self.token = (env.get("OKF_NOTION_TOKEN") or "").strip()
        self.base = (env.get("OKF_NOTION_URL") or API).rstrip("/")
        self.sleep, self.clock = sleep, clock
        self._last = None
        self._pages: dict[str, NotionPage] = {}

    def matches(self, resource: str) -> bool:
        return page_id(resource) is not None

    def unconfigured(self) -> str | None:
        return None if self.token else not_configured(self.settings)

    def last_modified(self, resource: str) -> datetime | None:
        return self.page(resource, blocks=False).at

    def describe(self, resource: str) -> str:
        page = self._pages.get(page_id(resource) or "")
        return f'Notion page "{page.title}"' if page else f"Notion page {page_id(resource)}"

    def signal(self, resource: str) -> Signal | None:
        page = self.page(resource, blocks=False)
        return Signal(page.at, self.describe(resource), "changed", "recheck:source-changed") if page.at else None

    def changes_since(self, resource: str, since: datetime) -> str | None:
        page = self.page(resource, blocks=False)
        if page.at is None or page.at <= since:
            return None
        snapshot = self.root / SNAPSHOTS / f"{page.id}.md" if self.root else None
        if snapshot is None or not snapshot.is_file():
            return f'Notion page "{page.title}" {page.url} was edited {day(page.at)}, after {day(since)}; ' \
                   "there is no saved snapshot to compare with (okf import notion saves one)."
        page = self.page(resource)
        before = snapshot.read_text(encoding="utf-8").rstrip("\n").split("\n")
        after = page.text.rstrip("\n").split("\n")
        diff = difflib.unified_diff(before, after, f"{page.title} (snapshot)", f"{page.title} ({day(page.at)})",
                                    lineterm="")
        return f"Notion page {page.url}\n" + "\n".join(diff)

    # --- REST ---------------------------------------------------------------------

    def page(self, resource: str, blocks: bool = True) -> NotionPage:
        pid = page_id(resource) or resource
        cached = self._pages.get(pid)
        if cached and (cached.text or not blocks):
            return cached
        if cached is None:
            data = self._get(f"/v1/pages/{pid}")
            if not isinstance(data, dict) or data.get("object") == "error":
                raise Unavailable(f"Notion page {pid}: unexpected answer")
            if data.get("archived") or data.get("in_trash"):
                raise Unavailable(f"Notion page {pid} is in the trash")
            cached = NotionPage(pid, _title(data) or pid, data.get("url") or f"https://www.notion.so/{pid.replace('-', '')}",
                                parse_time(data.get("last_edited_time")), "", [])
            self._pages[pid] = cached
        if blocks:
            lines, children = [], []
            self._blocks(pid, 0, lines, children)
            cached.text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
            cached.children = children
        return cached

    def _blocks(self, block_id: str, depth: int, lines: list[str], children: list) -> None:
        cursor = None
        for _ in range(100):  # pages of 100 blocks
            query = "page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
            data = self._get(f"/v1/blocks/{block_id}/children?{query}")
            for block in data.get("results") or []:
                _render(block, depth, lines, children)
                kind = block.get("type")
                if block.get("has_children") and kind not in ("child_page", "child_database"):
                    self._blocks(block["id"], depth + 1 if kind in _NESTING else depth, lines, children)
            if not data.get("has_more"):
                return
            cursor = data.get("next_cursor")

    def _get(self, path: str):
        if self._last is not None:
            wait = MIN_INTERVAL - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()
        return self.http.get_json(self.base + path, {"Authorization": f"Bearer {self.token}",
                                                     "Notion-Version": VERSION})


_NESTING = {"bulleted_list_item", "numbered_list_item", "to_do", "toggle"}


def _title(data: dict) -> str:
    for prop in (data.get("properties") or {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return _text(prop.get("title") or [], plain=True)
    return ""


def _text(rich: list, plain: bool = False) -> str:
    out = []
    for part in rich:
        text = part.get("plain_text") or ""
        if plain or not text:
            out.append(text)
            continue
        notes = part.get("annotations") or {}
        if notes.get("code"):
            text = f"`{text}`"
        if notes.get("bold"):
            text = f"**{text}**"
        if notes.get("italic"):
            text = f"*{text}*"
        href = part.get("href")
        out.append(f"[{text}]({href})" if href else text)
    return "".join(out)


def _render(block: dict, depth: int, lines: list[str], children: list) -> None:
    kind = block.get("type")
    body = block.get(kind) or {}
    text = _text(body.get("rich_text") or [])
    indent = "  " * depth
    if kind in ("heading_1", "heading_2", "heading_3"):
        lines += ["", "#" * int(kind[-1]) + " " + text, ""]
    elif kind == "paragraph":
        lines += [indent + text, ""] if text else [""]
    elif kind == "bulleted_list_item":
        lines.append(f"{indent}- {text}")
    elif kind == "numbered_list_item":
        lines.append(f"{indent}1. {text}")
    elif kind == "to_do":
        lines.append(f"{indent}- [{'x' if body.get('checked') else ' '}] {text}")
    elif kind == "toggle":
        lines.append(f"{indent}- {text}")
    elif kind in ("quote", "callout"):
        icon = (body.get("icon") or {}).get("emoji", "") if kind == "callout" else ""
        lines += [f"> {icon + ' ' if icon else ''}{text}", ""]
    elif kind == "code":
        lines += ["", f"```{body.get('language', '') if body.get('language') != 'plain text' else ''}",
                  _text(body.get("rich_text") or [], plain=True), "```", ""]
    elif kind == "divider":
        lines += ["", "---", ""]
    elif kind == "child_page":
        children.append((block.get("id"), body.get("title") or ""))
        lines.append(f"{indent}- Page: {body.get('title') or block.get('id')}")
    elif kind == "table_row":
        cells = [_text(cell).replace("|", "\\|") for cell in body.get("cells") or []]
        first = not lines or not lines[-1].startswith("|")
        lines.append("| " + " | ".join(cells) + " |")
        if first:
            lines.append("|" + "---|" * len(cells))
    elif kind in ("bookmark", "link_preview", "embed"):
        url = body.get("url") or ""
        lines += [f"{indent}[{url}]({url})", ""] if url else []
    elif kind in ("image", "file", "pdf", "video"):
        lines.append(f"{indent}[{kind}]")
