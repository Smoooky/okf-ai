"""`okf import confluence`: Confluence pages become OKF documents in git, and live by its freshness rules.

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

import yaml

from okf.bundle import load_document
from okf.sources.confluence import ConfluenceSource, Page, markdown, page_ref
from okf.trust import _flow

IMPORT_ACTOR = "process:okf-import"
DEFAULT_TYPE = "Guide"
_PLAIN_RE = re.compile(r"[\w:@.+\-/]+")  # URLs, actors, timestamps: written without quotes
_CYRILLIC = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                     "a b v g d e e zh z i y k l m n o p r s t u f kh ts ch sh shch _ y _ e yu ya".split()))
_CYRILLIC.update({"ъ": "", "ь": ""})


@dataclass
class Imported:
    path: Path
    page: Page
    action: str  # "new", "updated" or "unchanged"


def import_confluence(source: ConfluenceSource, out: Path, space: str | None, page_ids: list[str],
                      kind: str | None, limit: int, now: datetime) -> list[Imported]:
    out.mkdir(parents=True, exist_ok=True)
    pages = [source.page(page_id) for page_id in page_ids] if page_ids else list(source.space_pages(space, limit))
    existing = _imported_files(out)
    taken = {p.name for p in out.glob("*.md")}
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = []
    for page in pages:
        path = existing.get(page.id)
        if path is None:
            path = out / _file_name(page, taken)
            taken.add(path.name)
        body = f"# {page.title}\n\n{markdown(page.body)}"
        meta = load_document(path, out).meta if path.exists() else None
        if meta and _recorded(meta, page.id) == _stamp(page.at) and path.read_text(encoding="utf-8").endswith(body):
            result.append(Imported(path, page, "unchanged"))
            continue
        path.write_text(_front_matter(meta or {}, page, kind, stamp) + "\n" + body, encoding="utf-8", newline="\n")
        result.append(Imported(path, page, "updated" if meta else "new"))
    _index(out, [item for item in result if item.action == "new"])
    return result


def _front_matter(meta: dict, page: Page, kind: str | None, stamp: str) -> str:
    meta = dict(meta)
    meta["type"] = kind or meta.get("type") or DEFAULT_TYPE
    meta["title"] = page.title
    meta.setdefault("description", f"Imported from Confluence page {page.id}.")
    meta.setdefault("status", "draft")
    meta["generated"] = {"by": IMPORT_ACTOR, "at": stamp}
    entry = {"id": "confluence", "resource": page.url, "title": page.title, "last_modified": _stamp(page.at)}
    if entry["last_modified"] is None:
        del entry["last_modified"]
    others = [s for s in meta.get("sources") or [] if not (isinstance(s, dict) and _page_id(s) == page.id)]
    meta["sources"] = [entry, *others]
    ordered = {key: meta.pop(key) for key in ("type", "title", "description", "status", "generated") if key in meta}
    ordered.update(meta)
    text = "\n".join(_dump(ordered))
    return f"---\n# Written by okf import from Confluence: the body is replaced on the next import.\n{text}\n---\n"


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


def _imported_files(out: Path) -> dict[str, Path]:
    """Page id -> a file okf import wrote for it (a document someone else wrote is never overwritten)."""
    found = {}
    for path in sorted(out.glob("*.md")):
        meta = load_document(path, out).meta
        generated = meta.get("generated") if meta else None
        if not isinstance(generated, dict) or generated.get("by") != IMPORT_ACTOR:
            continue
        for entry in meta.get("sources") or []:
            if isinstance(entry, dict) and _page_id(entry):
                found.setdefault(_page_id(entry), path)
    return found


def _page_id(entry: dict) -> str | None:
    ref = page_ref(str(entry.get("resource") or ""))
    return ref[1] if ref else None


def _recorded(meta: dict, page_id: str) -> str | None:
    for entry in meta.get("sources") or []:
        if isinstance(entry, dict) and _page_id(entry) == page_id:
            return str(entry.get("last_modified")) if entry.get("last_modified") else None
    return None


def _file_name(page: Page, taken: set[str]) -> str:
    text = "".join(_CYRILLIC.get(ch, ch) for ch in page.title.lower())
    slug = re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:60].strip("_") or f"page_{page.id}"
    name = f"{slug}.md"
    return name if name not in taken and name not in ("index.md", "log.md", "agents.md") else f"{slug}_{page.id}.md"


def _index(out: Path, new: list[Imported]) -> None:
    """Link new documents from the bundle's index.md, creating a bundle root index if there is none."""
    index = out / "index.md"
    lines = [f"- [{item.page.title}]({item.path.name})" for item in new]
    if not index.exists():
        index.write_text('---\nokf_version: "0.2"\n---\n\n# Imported from Confluence\n\n' + "\n".join(lines) + "\n",
                         encoding="utf-8", newline="\n")
    elif lines:
        text = index.read_text(encoding="utf-8")
        index.write_text(text.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _stamp(moment: datetime | None) -> str | None:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None
