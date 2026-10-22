"""`okf import confluence` and `okf import notion`: pages become OKF documents in git, and live by its
freshness rules.

Each page becomes `<slug>.md` with `type` (Guide unless the file already has one or `--type` says
otherwise), `title`, `status: draft`, `sources: [{resource: <page>, last_modified: <its version>}]`
and `generated: {by: process:okf-import, at}`, never `verified`: the trust map shows it as not
verified until a person runs `okf verify`, and as "to recheck" once the page changes again.
The body is the page in Markdown. Importing again updates the files okf import wrote (found by the
page id in their sources) and leaves pages that did not change alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from okf.bundle import load_document
from okf.sources.confluence import ConfluenceSource, markdown, page_ref
from okf.sources.notion import SNAPSHOTS, NotionSource, page_id as notion_id
from okf.trust import _flow

IMPORT_ACTOR = "process:okf-import"
DEFAULT_TYPE = "Guide"
_PLAIN_RE = re.compile(r"[\w:@.+\-/]+")  # URLs, actors, timestamps: written without quotes
_CYRILLIC = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                     "a b v g d e e zh z i y k l m n o p r s t u f kh ts ch sh shch _ y _ e yu ya".split()))
_CYRILLIC.update({"ъ": "", "ь": ""})


@dataclass
class Item:
    """A page from any system, ready to be written as an OKF document."""

    id: str
    title: str
    url: str
    at: datetime | None
    body: str  # Markdown
    label: str  # "page 131073 v7", for messages


@dataclass
class Imported:
    path: Path
    page: Item
    action: str  # "new", "updated" or "unchanged"


def import_confluence(source: ConfluenceSource, out: Path, space: str | None, page_ids: list[str],
                      kind: str | None, limit: int, now: datetime) -> list[Imported]:
    pages = [source.page(page_id) for page_id in page_ids] if page_ids else list(source.space_pages(space, limit))
    items = [Item(p.id, p.title, p.url, p.at, markdown(p.body), f"page {p.id} v{p.version}") for p in pages]
    return write_items(items, out, kind, now, "Confluence", _confluence_key)


def import_notion(source: NotionSource, out: Path, page_ids: list[str], recursive: bool, kind: str | None,
                  limit: int, now: datetime, root: Path) -> list[Imported]:
    """Notion pages (with --recursive, their child pages too); the text of each is also saved as the
    snapshot that later `changes_since` compares against."""
    queue, seen, items = [notion_id(i) or notion_id(f"notion://{i}") or i for i in page_ids], set(), []
    while queue and len(items) < limit:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        page = source.page(current)
        items.append(Item(page.id, page.title, page.url, page.at, page.text, f"Notion page {page.id}"))
        snapshot = root / SNAPSHOTS / f"{page.id}.md"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(page.text, encoding="utf-8", newline="\n")
        if recursive:
            queue += [child for child, _ in page.children]
    return write_items(items, out, kind, now, "Notion", lambda r: notion_id(r))


def write_items(items: list[Item], out: Path, kind: str | None, now: datetime, system: str,
                key: Callable[[str], str | None]) -> list[Imported]:
    out.mkdir(parents=True, exist_ok=True)
    existing = _imported_files(out, key)
    taken = {p.name for p in out.glob("*.md")}
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = []
    for item in items:
        path = existing.get(item.id)
        if path is None:
            path = out / _file_name(item, taken)
            taken.add(path.name)
        body = f"# {item.title}\n\n{item.body}"
        meta = load_document(path, out).meta if path.exists() else None
        if meta and _recorded(meta, item.id, key) == _stamp(item.at) and \
                path.read_text(encoding="utf-8").endswith(body):
            result.append(Imported(path, item, "unchanged"))
            continue
        path.write_text(_front_matter(meta or {}, item, kind, stamp, system, key) + "\n" + body, encoding="utf-8",
                        newline="\n")
        result.append(Imported(path, item, "updated" if meta else "new"))
    _index(out, [i for i in result if i.action == "new"], system)
    return result


def _confluence_key(resource: str) -> str | None:
    ref = page_ref(resource)
    return ref[1] if ref else None


def _front_matter(meta: dict, item: Item, kind: str | None, stamp: str, system: str, key) -> str:
    meta = dict(meta)
    meta["type"] = kind or meta.get("type") or DEFAULT_TYPE
    meta["title"] = item.title
    meta.setdefault("description", f"Imported from {system} ({item.label}).")
    meta.setdefault("status", "draft")
    meta["generated"] = {"by": IMPORT_ACTOR, "at": stamp}
    entry = {"id": system.lower(), "resource": item.url, "title": item.title, "last_modified": _stamp(item.at)}
    if entry["last_modified"] is None:
        del entry["last_modified"]
    others = [s for s in meta.get("sources") or []
              if not (isinstance(s, dict) and key(str(s.get("resource") or "")) == item.id)]
    meta["sources"] = [entry, *others]
    ordered = {k: meta.pop(k) for k in ("type", "title", "description", "status", "generated") if k in meta}
    ordered.update(meta)
    text = "\n".join(_dump(ordered))
    return f"---\n# Written by okf import from {system}: the body is replaced on the next import.\n{text}\n---\n"


def _dump(meta: dict) -> list[str]:
    """Front matter in the style of the hand-written documents: flow mappings, block `sources`."""
    lines = []
    for key, value in meta.items():
        if isinstance(value, dict) and all(_flat(v) for v in value.values()):
            lines.append(f"{key}: {_flow(value)}")
        elif isinstance(value, list) and value and all(isinstance(e, dict) and all(_flat(v) for v in e.values())
                                                       for e in value):
            lines.append(f"{key}:")
            for entry in value:
                if key == "sources":
                    lines += [("  - " if i == 0 else "    ") + _line(k, v) for i, (k, v) in enumerate(entry.items())]
                else:
                    lines.append(f"  - {_flow(entry)}")
        else:
            lines.append(_line(key, value))
    return lines


def _line(key: str, value) -> str:
    if isinstance(value, str) and _PLAIN_RE.fullmatch(value) and value[:1] not in "-?:@":
        return f"{key}: {value}"
    return yaml.safe_dump({key: value}, allow_unicode=True, sort_keys=False, width=1000,
                          default_flow_style=False).rstrip("\n")


def _flat(value) -> bool:
    return not isinstance(value, (dict, list))


def _imported_files(out: Path, key) -> dict[str, Path]:
    """Page id -> a file okf import wrote for it (a document someone else wrote is never overwritten)."""
    found = {}
    for path in sorted(out.glob("*.md")):
        meta = load_document(path, out).meta
        generated = meta.get("generated") if meta else None
        if not isinstance(generated, dict) or generated.get("by") != IMPORT_ACTOR:
            continue
        for entry in meta.get("sources") or []:
            page = key(str(entry.get("resource") or "")) if isinstance(entry, dict) else None
            if page:
                found.setdefault(page, path)
    return found


def _recorded(meta: dict, page: str, key) -> str | None:
    for entry in meta.get("sources") or []:
        if isinstance(entry, dict) and key(str(entry.get("resource") or "")) == page:
            return str(entry.get("last_modified")) if entry.get("last_modified") else None
    return None


def slug(title: str) -> str:
    """An ASCII file name stem: "Тарифы и биллинг" -> "tarify_i_billing"."""
    text = "".join(_CYRILLIC.get(ch, ch) for ch in title.lower())
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:60].strip("_")


def _file_name(item: Item, taken: set[str]) -> str:
    short = item.id.replace("-", "")[:8]
    slug_text = slug(item.title) or f"page_{short}"
    name = f"{slug_text}.md"
    return name if name not in taken and name not in ("index.md", "log.md", "agents.md") else f"{slug_text}_{short}.md"


def _index(out: Path, new: list[Imported], system: str) -> None:
    """Link new documents from the bundle's index.md, creating a bundle root index if there is none."""
    index = out / "index.md"
    lines = [f"- [{item.page.title}]({item.path.name})" for item in new]
    if not index.exists():
        index.write_text(f'---\nokf_version: "0.2"\n---\n\n# Imported from {system}\n\n' + "\n".join(lines) + "\n",
                         encoding="utf-8", newline="\n")
    elif lines:
        text = index.read_text(encoding="utf-8")
        index.write_text(text.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _stamp(moment: datetime | None) -> str | None:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None
