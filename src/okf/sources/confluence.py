"""Confluence pages as sources: when a page changed, what changed in it, and its text for `okf import`.

Resources:
- https://<site>.atlassian.net/wiki/spaces/<KEY>/pages/<id>/<title> (Cloud)
- https://<host>/pages/viewpage.action?pageId=<id> (Server/Data Center)
- confluence://<id>

Settings: OKF_CONFLUENCE_URL (https://<site>.atlassian.net/wiki, or the Server/DC address), and
OKF_ATLASSIAN_EMAIL + OKF_ATLASSIAN_TOKEN (Cloud) or OKF_ATLASSIAN_PAT (Server/DC). Cloud
(*.atlassian.net) is read through REST v2, Server/DC through REST v1.
"""

from __future__ import annotations

import difflib
import html
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Iterator
from urllib.parse import parse_qs, quote, urlsplit

from okf.sources.base import Signal, Source, Unavailable, day, not_configured, parse_time
from okf.sources.http import atlassian_headers

_CLOUD_PAGE_RE = re.compile(r"/spaces/[^/]+/pages/(?:edit-v2/)?(\d+)(?:/|$)")
SETTINGS = "OKF_CONFLUENCE_URL"  # credentials: OKF_ATLASSIAN_EMAIL + OKF_ATLASSIAN_TOKEN, or OKF_ATLASSIAN_PAT
MAX_VERSIONS_BACK = 30  # Server/DC: how many older versions to walk to find the one at a date


@dataclass
class Page:
    id: str
    title: str
    version: int
    at: datetime | None
    body: str  # storage format (XHTML)
    url: str  # the page in a browser


def page_ref(resource: str) -> tuple[str | None, str] | None:
    """(host or None, page id) of a Confluence page resource, else None."""
    resource = resource.strip()
    match = re.match(r"^confluence:(?://)?(\d+)/?$", resource, re.IGNORECASE)
    if match:
        return None, match.group(1)
    parts = urlsplit(resource)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    match = _CLOUD_PAGE_RE.search(parts.path)
    if match:
        return parts.netloc.lower(), match.group(1)
    if parts.path.endswith("/pages/viewpage.action"):
        page_id = parse_qs(parts.query).get("pageId", [""])[0]
        if page_id.isdigit():
            return parts.netloc.lower(), page_id
    return None


class ConfluenceSource(Source):
    name = "confluence"
    settings = SETTINGS

    def __init__(self, env, http=None):
        super().__init__(env, http)
        base = (env.get("OKF_CONFLUENCE_URL") or "").strip().rstrip("/")
        parts = urlsplit(base)
        self.host = parts.netloc.lower()
        self.cloud = self.host.endswith(".atlassian.net")
        if self.cloud and not parts.path.rstrip("/").endswith("/wiki"):
            base += "/wiki"
        self.base = base
        self._pages: dict[tuple[str, int | None], Page] = {}

    def matches(self, resource: str) -> bool:
        return page_ref(resource) is not None

    def unconfigured(self) -> str | None:
        return None if self.base else not_configured(self.settings)

    def problem(self, resource: str) -> str | None:
        if not self.base:
            return self.unconfigured()
        host = page_ref(resource)[0]
        if host and host != self.host:
            return f"OKF_CONFLUENCE_URL is {self.host}, not {host}"
        return None

    def last_modified(self, resource: str) -> datetime | None:
        return self.page(resource).at

    def describe(self, resource: str) -> str:
        page = self._pages.get((page_ref(resource)[1], None))
        return f'Confluence page "{page.title}" (v{page.version})' if page else f"Confluence page {page_ref(resource)[1]}"

    def signal(self, resource: str) -> Signal | None:
        page = self.page(resource)
        return Signal(page.at, self.describe(resource), "changed", "recheck:source-changed") if page.at else None

    def changes_since(self, resource: str, since: datetime) -> str | None:
        page = self.page(resource)
        if page.at is None or page.at <= since:
            return None
        old = self.version_at(page, since)
        before = markdown(old.body).rstrip("\n").split("\n") if old else []
        after = markdown(page.body).rstrip("\n").split("\n")
        was = f"v{old.version} ({day(old.at)})" if old and old.at else "nothing (created later)"
        diff = difflib.unified_diff(before, after, f"{page.title} {was}", f"{page.title} v{page.version} "
                                    f"({day(page.at)})", lineterm="")
        return f"Confluence page {page.id} {page.url}\n" + "\n".join(diff)

    # --- REST ---------------------------------------------------------------------

    def page(self, resource: str, version: int | None = None) -> Page:
        page_id = page_ref(resource)[1] if not resource.isdigit() else resource
        key = (page_id, version)
        if key not in self._pages:
            if self.cloud:
                query = "body-format=storage" + (f"&version={version}" if version else "")
                data = self._get(f"/api/v2/pages/{page_id}?{query}")
            else:
                query = "expand=version,body.storage" + (f"&status=historical&version={version}" if version else "")
                data = self._get(f"/rest/api/content/{page_id}?{query}")
            self._pages[key] = self._page(data, page_id)
        return self._pages[key]

    def version_at(self, page: Page, moment: datetime) -> Page | None:
        """The page as it was at `moment`: its latest version created then or before."""
        if self.cloud:
            versions, url = [], f"/api/v2/pages/{page.id}/versions?limit=50&sort=-modified-date"
            for _ in range(10):
                data = self._get(url)
                versions += [(v.get("number"), parse_time(v.get("createdAt"))) for v in data.get("results") or []]
                url = (data.get("_links") or {}).get("next")
                if not url or any(at and at <= moment for _, at in versions):
                    break
                url = url[len("/wiki"):] if url.startswith("/wiki/") else url
            older = [n for n, at in versions if isinstance(n, int) and at and at <= moment]
            return self.page(page.id, max(older)) if older else None
        for number in range(page.version - 1, max(page.version - 1 - MAX_VERSIONS_BACK, 0), -1):
            old = self.page(page.id, number)
            if old.at and old.at <= moment:
                return old
        return None

    def space_pages(self, space: str, limit: int) -> Iterator[Page]:
        if self.cloud:
            found = self._get(f"/api/v2/spaces?keys={quote(space)}").get("results") or []
            if not found:
                raise Unavailable(f"no Confluence space {space}")
            url = f"/api/v2/spaces/{found[0]['id']}/pages?body-format=storage&limit=50"
        else:
            url = f"/rest/api/content?spaceKey={quote(space)}&type=page&expand=version,body.storage&limit=50"
        count = 0
        while url and count < limit:
            data = self._get(url)
            for item in data.get("results") or []:
                page = self._page(item, str(item.get("id")))
                self._pages[(page.id, None)] = page
                count += 1
                yield page
                if count >= limit:
                    return
            url = (data.get("_links") or {}).get("next")
            if url and self.cloud and url.startswith("/wiki/"):
                url = url[len("/wiki"):]

    def _get(self, path: str):
        return self.http.get_json(self.base + path, atlassian_headers(self.env))

    def _page(self, data: dict, page_id: str) -> Page:
        if not isinstance(data, dict):
            raise Unavailable(f"Confluence page {page_id}: unexpected answer")
        version = data.get("version") or {}
        body = ((data.get("body") or {}).get("storage") or {}).get("value") or ""
        links = data.get("_links") or {}
        webui = links.get("webui") or ""
        if self.cloud:
            url = self.base + webui if webui.startswith("/spaces/") else f"confluence://{page_id}"
            at = parse_time(version.get("createdAt"))
        else:
            url = f"{self.base}/pages/viewpage.action?pageId={page_id}"
            at = parse_time(version.get("when"))
        number = version.get("number") if isinstance(version.get("number"), int) else 0
        return Page(str(data.get("id") or page_id), str(data.get("title") or page_id), number, at, body, url)


# --- Storage format to Markdown ------------------------------------------------------


def markdown(storage: str) -> str:
    """Confluence storage XHTML as Markdown: headings, lists, code, links and tables; the rest as text."""
    storage = re.sub(r"<!\[CDATA\[(.*?)\]\]>", lambda m: html.escape(m.group(1), quote=False), storage, flags=re.S)
    parser = _Storage()
    parser.feed(storage)
    parser.close()
    parser.flush()
    text = "\n".join(line.rstrip() for line in parser.lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


class _Storage(HTMLParser):
    _SKIP = {"ac:task-id", "ac:task-status", "ac:placeholder", "ac:emoticon", "ri:attachment"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.inline: list[str] = []
        self.heading = 0
        self.lists: list[list] = []  # [tag, items so far]
        self.items = 0  # open <li>
        self.marker: str | None = None  # the list marker the next line of an item starts with
        self.pre: list[str] | None = None
        self.macros: list[dict] = []
        self.param: tuple[str, list[str]] | None = None
        self.links: list[tuple[str, int]] = []
        self.link_title = ""
        self.row: list[str] | None = None
        self.rows = 0
        self.cell = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self._SKIP:
            self.skip += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.heading = int(tag[1])
        elif tag in ("p", "div", "blockquote") and self.cell is None:
            self.flush()
        elif tag == "br":
            self.inline.append(" " if self.cell is not None else "\n")
        elif tag in ("ul", "ol"):
            self.flush()
            self.lists.append([tag, 0])
        elif tag in ("li", "ac:task"):
            self.flush()
            if not self.lists:
                self.lists.append(["ul", 0])
            self.lists[-1][1] += 1
            self.items += 1
            kind, number = self.lists[-1]
            self.marker = f"{number}. " if kind == "ol" else "- "
        elif tag in ("strong", "b"):
            self.inline.append("**")
        elif tag in ("em", "i"):
            self.inline.append("*")
        elif tag == "code" and self.pre is None:
            self.inline.append("`")
        elif tag == "a":
            self.links.append((attrs.get("href") or "", len(self.inline)))
        elif tag == "ac:link":
            self.links.append(("", len(self.inline)))
            self.link_title = ""
        elif tag in ("ri:page", "ri:space", "ri:user"):
            self.link_title = attrs.get("ri:content-title") or attrs.get("ri:space-key") or self.link_title
        elif tag == "pre":
            self.flush()
            self.pre = []
        elif tag == "ac:structured-macro":
            self.macros.append({"name": attrs.get("ac:name", ""), "params": {}})
            if self.macros[-1]["name"] in ("code", "noformat"):
                self.flush()
        elif tag == "ac:parameter":
            self.param = (attrs.get("ac:name", ""), [])
        elif tag == "ac:plain-text-body":
            self.pre = []
        elif tag == "table":
            self.flush()
            self.rows = 0
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = len(self.inline)

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self.skip = max(self.skip - 1, 0)
        elif re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.heading = 0
        elif tag in ("p", "div", "blockquote") and self.cell is None:
            self.flush()
        elif tag in ("ul", "ol"):
            self.flush()
            if self.lists:
                self.lists.pop()
            if not self.lists:
                self.lines.append("")
        elif tag in ("li", "ac:task"):
            self.flush()
            self.items = max(self.items - 1, 0)
            if tag == "ac:task" and self.lists and not self.items:
                self.lists.pop()
                self.lines.append("")
        elif tag in ("strong", "b"):
            self.inline.append("**")
        elif tag in ("em", "i"):
            self.inline.append("*")
        elif tag == "code" and self.pre is None:
            self.inline.append("`")
        elif tag in ("a", "ac:link") and self.links:
            href, start = self.links.pop()
            text = "".join(self.inline[start:]).strip() or (self.link_title if tag == "ac:link" else href)
            self.inline[start:] = [f"[{text}]({href})" if href and text != href else text]
        elif tag == "pre" and self.pre is not None:
            self._code("".join(self.pre), "")
            self.pre = None
        elif tag == "ac:plain-text-body" and self.pre is not None:
            if self.macros:
                self.macros[-1]["body"] = "".join(self.pre)
            self.pre = None
        elif tag == "ac:parameter" and self.param is not None:
            if self.macros:
                self.macros[-1]["params"][self.param[0]] = "".join(self.param[1]).strip()
            self.param = None
        elif tag == "ac:structured-macro" and self.macros:
            macro = self.macros.pop()
            if macro["name"] in ("code", "noformat"):
                self._code(macro.get("body", ""), macro["params"].get("language", ""))
            elif macro["name"] == "jira" and macro["params"].get("key"):
                self.inline.append(macro["params"]["key"])
        elif tag in ("td", "th") and self.row is not None and self.cell is not None:
            text = re.sub(r"\s+", " ", "".join(self.inline[self.cell:])).strip().replace("|", "\\|")
            del self.inline[self.cell:]
            self.row.append(text)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.lines.append("| " + " | ".join(self.row) + " |")
            if self.rows == 0:
                self.lines.append("|" + "---|" * len(self.row))
            self.rows += 1
            self.row = None
        elif tag == "table":
            self.lines.append("")

    def handle_data(self, data):
        if self.param is not None:
            self.param[1].append(data)
        elif self.pre is not None:
            self.pre.append(data)
        elif not self.skip:
            self.inline.append(data)

    def _code(self, code: str, language: str) -> None:
        self.flush()
        self.lines += ["", "```" + language, *code.strip("\n").split("\n"), "```", ""]

    def flush(self) -> None:
        text = "".join(self.inline).replace("\xa0", " ")
        self.inline = []
        parts = [re.sub(r"\s+", " ", part).strip() for part in text.split("\n")]
        parts = [part for part in parts if part]
        if not parts:
            return
        if self.heading:
            self.lines += ["", "#" * self.heading + " " + " ".join(parts), ""]
            return
        if self.items:
            indent = "  " * (len(self.lists) - 1)
            for part in parts:
                self.lines.append(indent + (self.marker or "  ") + part)
                self.marker = None
            return
        self.lines += [*parts, ""]
