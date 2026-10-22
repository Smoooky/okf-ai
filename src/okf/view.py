"""Pages for people: `okf trust --html report.html` and `okf view <repo> --out site/`.

Both are plain files with inline CSS and JS and no external requests: they open offline, from
a CI artifact or a laptop, in light or dark theme, on a phone too.
"""

from __future__ import annotations

import html
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from okf import schema
from okf.agents import freshness_status
from okf.bundle import SCHEME_RE, Bundle, Document
from okf.trust import TrustMap, Unit

LEVELS = {  # level -> (label, css class)
    "broken": ("broken", "broken"),
    "recheck": ("to recheck", "recheck"),
    "human-verified": ("verified by a person", "verified"),
    "process-verified": ("verified by a process", "verified"),
    "unverified": ("not verified", "unverified"),
}
FILTERS = (("broken", "broken"), ("recheck", "to recheck"), ("verified", "verified"), ("unverified", "not verified"))

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--text:#1d1d1b;--muted:#66665f;--line:#e2e2dc;--accent:#2f5bd3;
--green:#1f8a4c;--green-bg:#e6f4ec;--yellow:#9a6a00;--yellow-bg:#fdf3d7;--red:#c0362c;--red-bg:#fbe6e3;
--gray:#6b6b66;--gray-bg:#eeeeea;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--card:#1e1e1c;--text:#ecece6;--muted:#a3a39b;--line:#33332f;
--accent:#86a6ff;--green:#5fd08e;--green-bg:#183324;--yellow:#e8bf55;--yellow-bg:#352b12;--red:#ff8a7f;
--red-bg:#3a1c19;--gray:#b0b0a8;--gray-bg:#2a2a27}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}a{color:var(--accent)}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 10px}.muted{color:var(--muted)}
code,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px}
pre{background:var(--gray-bg);padding:12px;border-radius:8px;overflow-x:auto}
code{background:var(--gray-bg);padding:1px 4px;border-radius:4px}pre code{background:none;padding:0}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:18px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.stat b{display:block;font-size:26px;line-height:1.1}.stat.broken b{color:var(--red)}
.stat.recheck b{color:var(--yellow)}.stat.verified b{color:var(--green)}.stat.unverified b{color:var(--gray)}
.tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0 16px}
.tools input{flex:1 1 220px;min-width:0;padding:8px 10px;border:1px solid var(--line);border-radius:8px;
background:var(--card);color:var(--text);font:inherit}
.chip{border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:999px;padding:6px 12px;
font:inherit;cursor:pointer}.chip[aria-pressed=false]{opacity:.45}
.unit{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--gray);border-radius:10px;
padding:12px 14px;margin:10px 0;overflow-wrap:anywhere}
.unit.broken{border-left-color:var(--red)}.unit.recheck{border-left-color:var(--yellow)}
.unit.verified{border-left-color:var(--green)}.unit h3{font-size:15px;margin:0 0 4px}
.badge{display:inline-block;font-size:12px;font-weight:600;border-radius:999px;padding:1px 8px;margin-left:6px;
vertical-align:1px}.badge.broken{background:var(--red-bg);color:var(--red)}
.badge.recheck{background:var(--yellow-bg);color:var(--yellow)}.badge.verified{background:var(--green-bg);color:var(--green)}
.badge.unverified{background:var(--gray-bg);color:var(--gray)}
.unit dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 12px;margin:8px 0 0;font-size:14px}
.unit dt{color:var(--muted)}.unit dd{margin:0}.hidden{display:none}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid var(--line);
padding:6px 8px;text-align:left;vertical-align:top}.table{overflow-x:auto}
article{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 18px 16px}
.meta{font-size:14px}.tags a{margin-right:6px}svg text{fill:var(--text);font-size:11px}
svg line{stroke:var(--line);stroke-width:1.5}.node.broken{fill:var(--red)}.node.recheck{fill:var(--yellow)}
.node.verified{fill:var(--green)}.node.unverified{fill:var(--gray)}
blockquote{margin:0;padding:0 12px;border-left:3px solid var(--line);color:var(--muted)}
@media (max-width:560px){main{padding:16px 12px 48px}.summary{grid-template-columns:repeat(2,1fr)}
.unit dl{grid-template-columns:1fr}.unit dt{margin-top:4px}}
"""

FILTER_JS = """
(function(){var q=document.getElementById('q'),chips=document.querySelectorAll('.chip'),
cards=document.querySelectorAll('[data-level]');function apply(){var on={},t=q.value.toLowerCase();
chips.forEach(function(c){on[c.dataset.filter]=c.getAttribute('aria-pressed')==='true'});
cards.forEach(function(e){var ok=on[e.dataset.level]&&(!t||e.textContent.toLowerCase().indexOf(t)>=0);
e.classList.toggle('hidden',!ok)});document.querySelectorAll('section[data-group]').forEach(function(s){
s.classList.toggle('hidden',!s.querySelector('[data-level]:not(.hidden)'))})}
chips.forEach(function(c){c.addEventListener('click',function(){c.setAttribute('aria-pressed',
c.getAttribute('aria-pressed')==='true'?'false':'true');apply()})});q.addEventListener('input',apply)})();
"""


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def _page(title: str, body: str, script: str = "") -> str:
    tail = f"<script>{script}</script>" if script else ""
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f"<style>{CSS}</style></head><body><main>{body}</main>{tail}</body></html>\n")


def _day(moment: datetime | None) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d") if moment else ""


def css_level(level: str) -> str:
    return LEVELS[level][1]


# --- okf trust --html ---------------------------------------------------------------


def trust_html(trust_map: TrustMap, root: Path, now: datetime, shown: list[Unit] | None = None,
               web: str | None = None, git_root: Path | None = None) -> str:
    """The trust map as one self-contained page. `web`: https://github.com/<repo>/blob/<commit> for line links."""
    units = trust_map.units if shown is None else shown
    counts = {key: sum(css_level(u.level) == key for u in trust_map.units) for key, _ in FILTERS}
    since = f"; {len(trust_map.in_change())} to recheck because of this change" if trust_map.since else ""
    parts = [f"<h1>Trust map: {esc(root.name)}</h1>",
             f'<p class="muted">{len(trust_map.units)} units, generated {now.astimezone(timezone.utc):%Y-%m-%d %H:%M} '
             f"UTC by okf trust{esc(since)}. Which agent instructions and knowledge can be relied on now.</p>"]
    if trust_map.shallow:
        parts.append('<p class="badge recheck">shallow git history: dates are unknown, fetch it with fetch-depth: 0</p>')
    parts.append('<div class="summary">' + "".join(
        f'<div class="stat {key}"><b>{counts[key]}</b>{esc(label)}</div>' for key, label in FILTERS) + "</div>")
    parts.append('<div class="tools"><input id="q" type="search" placeholder="Search units, files, reasons" '
                 'aria-label="Search">' + "".join(
                     f'<button class="chip" type="button" data-filter="{key}" aria-pressed="true">{esc(label)} '
                     f"({sum(css_level(u.level) == key for u in units)})</button>" for key, label in FILTERS) + "</div>")
    for key, label in FILTERS:
        group = [u for u in units if css_level(u.level) == key]
        if not group:
            continue
        parts.append(f'<section data-group="{key}"><h2>{esc(label.capitalize())} ({len(group)})</h2>')
        parts.extend(_unit_card(u, root, web, git_root) for u in group)
        parts.append("</section>")
    if trust_map.notes:
        parts.append("<h2>Not checked here</h2><ul>" + "".join(
            f"<li><code>{esc(_rel(p, root))}</code>: {esc(n)}</li>" for p, n in trust_map.notes) + "</ul>")
    return _page(f"Trust map: {root.name}", "".join(parts), FILTER_JS)


def _unit_card(unit: Unit, root: Path, web: str | None, git_root: Path | None) -> str:
    key = css_level(unit.level)
    where = f"{_rel(unit.path, root)}:{unit.line}"
    if web and git_root:
        where_html = f'<a href="{esc(web)}/{esc(_rel(unit.path, git_root))}#L{unit.line}">{esc(where)}</a>'
    else:
        where_html = f"<code>{esc(where)}</code>"
    rows = [("where", where_html), ("why", esc(unit.message))]
    changed = [f"<code>{esc(label)}</code> {esc(_day(at))}" for label, at in unit.changed]
    changed += [f"{esc(r.signal.subject)} {esc(r.signal.verb)} {esc(_day(r.signal.at))}"
                for r in unit.remote if r.signal]
    if changed:
        rows.append(("changed", "<br>".join(changed)))
    if unit.in_change:
        rows.append(("in this change", ", ".join(f"<code>{esc(p)}</code>" for p in unit.in_change)))
    if unit.sources:
        rows.append(("sources", ", ".join(f"<code>{esc(_rel(s, root))}</code>" for s in unit.sources[:12])
                     + (f" and {len(unit.sources) - 12} more" if len(unit.sources) > 12 else "")))
    remote = [f"{esc(r.resource)}: {esc(r.status)}" + ("" if r.status == "ok" else f", {esc(r.message)}")
              for r in unit.remote if r.connector]
    if remote:
        rows.append(("remote", "<br>".join(remote)))
    if unit.verifications:
        rows.append(("verified", "<br>".join(f"{esc(by)}, {esc(_day(at))}"
                                            for at, by in sorted(unit.verifications, reverse=True)[:5])))
    if unit.generated_by:
        rows.append(("written by", esc(unit.generated_by) + (f", {esc(_day(unit.generated_at))}"
                                                            if unit.generated_at else "")))
    body = "".join(f"<dt>{name}</dt><dd>{value}</dd>" for name, value in rows)
    return (f'<div class="unit {key}" data-level="{key}"><h3>{esc(unit.name)}'
            f'<span class="badge {key}">{esc(LEVELS[unit.level][0])}</span></h3><dl>{body}</dl></div>')


# --- okf view: a static site of the knowledge base -----------------------------------


def find_bundles(path: Path) -> list[Path]:
    """`path` itself if it is a bundle (a root index.md), else every bundle under it."""
    path = Path(path).resolve()
    if _is_root_index(path / "index.md"):
        return [path]
    found = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "venv"))
        if "index.md" in filenames and _is_root_index(Path(dirpath) / "index.md"):
            found.append(Path(dirpath))
            dirnames[:] = []
    return found


def _is_root_index(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return text.startswith("---") and "okf_version" in text.split("---", 2)[1] if text.count("---") >= 2 else False


def build_site(bundle: Bundle, out: Path, units: dict[Path, Unit], now: datetime) -> list[Path]:
    """index.html (documents by index.md and by tag, a graph of links) and one page per document."""
    out.mkdir(parents=True, exist_ok=True)
    docs = bundle.concepts()
    written = []
    for doc in bundle.documents:  # log.md and the AGENTS.md router get plain pages, so links to them work
        if doc.rel == "index.md" or doc.text is None or (not doc.is_concept and doc.meta is None and doc.rel != "log.md"
                                                          and doc.name != "AGENTS.md"):
            continue
        target = out / (Path(doc.rel).with_suffix(".html"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_doc_page(bundle, doc, units.get(doc.path), now, target, out), encoding="utf-8",
                          newline="\n")
        written.append(target)
    index = out / "index.html"
    index.write_text(_index_page(bundle, docs, units, now, out), encoding="utf-8", newline="\n")
    return [index, *written]


def _doc_href(bundle: Bundle, doc: Document, target: str, page: Path, out: Path) -> str:
    path = bundle.resolve_link(doc, target)
    if path is None or path.suffix.lower() != ".md":
        return target
    anchor = "#" + target.split("#", 1)[1] if "#" in target else ""
    try:
        rel = path.relative_to(bundle.root)
    except ValueError:
        return target
    name = "index.html" if rel.name == "index.md" and len(rel.parts) == 1 else rel.with_suffix(".html").as_posix()
    return os.path.relpath(out / name, page.parent).replace(os.sep, "/") + anchor


def _level(unit: Unit | None) -> tuple[str, str]:
    if unit is None:
        return "unverified", "not in the trust map"
    return css_level(unit.level), LEVELS[unit.level][0]


def _doc_page(bundle: Bundle, doc: Document, unit: Unit | None, now: datetime, page: Path, out: Path) -> str:
    key, label = _level(unit)
    home = os.path.relpath(out / "index.html", page.parent).replace(os.sep, "/")
    if not doc.is_concept:
        body = markdown_html(doc.body, lambda target: _doc_href(bundle, doc, target, page, out))
        return _page(doc.rel, f'<p><a href="{esc(home)}">← {esc(_bundle_title(bundle))}</a></p><article>{body}</article>')
    meta = doc.meta or {}
    rows = [("type", esc(meta.get("type", ""))), ("status", esc(schema.status(doc))),
            ("freshness", esc(freshness_status(doc, now)))]
    rows.append(("trust", f'<span class="badge {key}">{esc(label)}</span>' + (f" {esc(unit.message)}" if unit else "")))
    verified = schema.verifications(doc)
    if verified:
        rows.append(("verified", "<br>".join(f"{esc(v.get('by'))}, {esc(v.get('at'))}" for v in verified)))
    if schema.generated_by(doc):
        rows.append(("written by", esc(schema.generated_by(doc))))
    if meta.get("stale_after"):
        rows.append(("stale_after", esc(meta.get("stale_after"))))
    sources = [e for e in meta.get("sources") or [] if isinstance(e, dict)]
    if sources:
        rows.append(("sources", "<br>".join(_source(e) for e in sources)))
    tags = _tags(doc)
    if tags:
        rows.append(("tags", ", ".join(esc(t) for t in tags)))
    head = "".join(f"<dt>{name}</dt><dd>{value}</dd>" for name, value in rows)
    text = re.sub(rf"^\s*#\s+{re.escape(doc.title)}\s*\n", "", doc.body, count=1)  # the page title already says it
    body = markdown_html(text, lambda target: _doc_href(bundle, doc, target, page, out))
    return _page(doc.title, f'<p><a href="{esc(home)}">← {esc(_bundle_title(bundle))}</a></p><h1>{esc(doc.title)}</h1>'
                 f'<p class="muted">{esc(meta.get("description", ""))}</p>'
                 f'<div class="unit {key}"><dl class="meta">{head}</dl></div><article>{body}</article>')


def _source(entry: dict) -> str:
    resource = str(entry.get("resource", ""))
    title = str(entry.get("title") or "")
    shown = f'<a href="{esc(resource)}">{esc(resource)}</a>' if re.match(r"^https?://", resource) else \
        f"<code>{esc(resource)}</code>"
    return shown + (f" — {esc(title)}" if title else "")


def _tags(doc: Document) -> list[str]:
    value = (doc.meta or {}).get("tags")
    if isinstance(value, str):
        value = [t.strip() for t in value.split(",")]
    return [str(t) for t in value or [] if str(t).strip()] if isinstance(value, list) else []


def _index_page(bundle: Bundle, docs: list[Document], units: dict[Path, Unit], now: datetime, out: Path) -> str:
    index_doc = next((d for d in bundle.documents if d.rel == "index.md"), None)
    parts = [f"<h1>{esc(_bundle_title(bundle))}</h1>",
             f'<p class="muted">{len(docs)} OKF documents, generated {now.astimezone(timezone.utc):%Y-%m-%d} by '
             "okf view.</p>"]
    if index_doc and index_doc.body.strip():
        body = re.sub(r"^\s*# .*\n", "", index_doc.body, count=1)  # its title is the page title
        parts.append("<article>" + markdown_html(
            body, lambda t: _doc_href(bundle, index_doc, t, out / "index.html", out)) + "</article>")
    rows = []
    for doc in sorted(docs, key=lambda d: d.title.lower()):
        key, label = _level(units.get(doc.path))
        href = Path(doc.rel).with_suffix(".html").as_posix()
        rows.append(f'<tr data-level="{key}"><td><a href="{esc(href)}">{esc(doc.title)}</a></td>'
                    f"<td>{esc((doc.meta or {}).get('type', ''))}</td><td>{esc(freshness_status(doc, now))}</td>"
                    f'<td><span class="badge {key}">{esc(label)}</span></td></tr>')
    parts.append('<h2>Documents</h2><div class="tools"><input id="q" type="search" placeholder="Search documents" '
                 'aria-label="Search">' + "".join(
                     f'<button class="chip" type="button" data-filter="{key}" aria-pressed="true">{esc(label)}</button>'
                     for key, label in FILTERS) + "</div>")
    parts.append('<div class="table"><table><thead><tr><th>Document</th><th>Type</th><th>Freshness</th>'
                 f"<th>Trust</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>")
    by_tag: dict[str, list[Document]] = {}
    for doc in docs:
        for tag in _tags(doc):
            by_tag.setdefault(tag, []).append(doc)
    if by_tag:
        parts.append("<h2>By tag</h2>")
        for tag in sorted(by_tag):
            links = ", ".join(f'<a href="{esc(Path(d.rel).with_suffix(".html").as_posix())}">{esc(d.title)}</a>'
                              for d in sorted(by_tag[tag], key=lambda d: d.title.lower()))
            parts.append(f'<p class="tags"><b>{esc(tag)}</b>: {links}</p>')
    parts.append("<h2>Links between documents</h2>" + graph_svg(bundle, docs, units))
    return _page(_bundle_title(bundle), "".join(parts), FILTER_JS)


def _bundle_title(bundle: Bundle) -> str:
    """The first heading of the bundle's index.md, else the folder name."""
    index_doc = next((d for d in bundle.documents if d.rel == "index.md"), None)
    heading = next(index_doc.headings(level=1), None) if index_doc else None
    return heading[0] if heading else f"Knowledge: {bundle.root.name}"


def graph_svg(bundle: Bundle, docs: list[Document], units: dict[Path, Unit]) -> str:
    """Documents on a circle, a line for every link between two of them, colored by trust level."""
    if not docs:
        return '<p class="muted">No documents.</p>'
    by_path = {d.path: i for i, d in enumerate(docs)}
    edges = set()
    for i, doc in enumerate(docs):
        for target, _ in doc.links():
            j = by_path.get(bundle.resolve_link(doc, target))
            if j is not None and j != i:
                edges.add((min(i, j), max(i, j)))
    size, radius = 640, 230 if len(docs) > 1 else 0
    points = [(size / 2 + radius * math.cos(2 * math.pi * i / len(docs) - math.pi / 2),
               size / 2 + radius * math.sin(2 * math.pi * i / len(docs) - math.pi / 2)) for i in range(len(docs))]
    lines = "".join(f'<line x1="{points[a][0]:.1f}" y1="{points[a][1]:.1f}" x2="{points[b][0]:.1f}" '
                    f'y2="{points[b][1]:.1f}"/>' for a, b in sorted(edges))
    nodes = []
    for i, doc in enumerate(docs):
        x, y = points[i]
        key, label = _level(units.get(doc.path))
        anchor = "start" if x > size / 2 + 1 else "end" if x < size / 2 - 1 else "middle"
        dx = 12 if anchor == "start" else -12 if anchor == "end" else 0
        dy = 4 if anchor != "middle" else (-14 if y < size / 2 else 22)
        href = Path(doc.rel).with_suffix(".html").as_posix()
        nodes.append(f'<a href="{esc(href)}"><title>{esc(doc.title)}: {esc(label)}</title>'
                     f'<circle class="node {key}" cx="{x:.1f}" cy="{y:.1f}" r="8"/>'
                     f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" text-anchor="{anchor}">{esc(_short(doc.title))}</text></a>')
    return (f'<svg viewBox="-150 0 {size + 300} {size}" width="100%" role="img" '
            f'aria-label="Links between {len(docs)} documents, {len(edges)} links">{lines}{"".join(nodes)}</svg>'
            f'<p class="muted">{len(edges)} links between {len(docs)} documents; colors are trust levels.</p>')


def _short(text: str, limit: int = 28) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --- Markdown to HTML (what knowledge documents use; no external libraries) -----------

_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([\w+-]*)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_FOOTNOTE = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")


def markdown_html(text: str, href: Callable[[str], str] = lambda target: target) -> str:
    lines = text.split("\n")
    out, notes, i = [], [], 0
    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            mark, language, code = fence.group(1), fence.group(2), []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(mark[0] * len(mark)):
                code.append(lines[i])
                i += 1
            css = f' class="language-{esc(language)}"' if language else ""
            out.append(f"<pre><code{css}>{esc(chr(10).join(code))}</code></pre>")
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            out.append(f'<h{level} id="{esc(_slug(title))}">{_inline(title, href)}</h{level}>')
            i += 1
            continue
        if _HR.match(line):
            out.append("<hr>")
            i += 1
            continue
        note = _FOOTNOTE.match(line)
        if note:
            notes.append((note.group(1), note.group(2)))
            i += 1
            continue
        if line.lstrip().startswith(">"):
            quoted = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quoted.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{markdown_html(chr(10).join(quoted), href)}</blockquote>")
            continue
        if "|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            rows = [line]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(lines[i])
                i += 1
            out.append(_table(rows, href))
            continue
        if _LIST.match(line):
            items = []
            while i < len(lines):
                match = _LIST.match(lines[i])
                if match:
                    item = [len(match.group(1).expandtabs(4)), match.group(2)[0].isdigit(), match.group(3)]
                    if items and item[0] <= items[0][0] and item[1] != items[0][1]:
                        break  # a bulleted list after a numbered one (or back) is a new list
                    items.append(item)
                elif lines[i].strip() and lines[i][:1] in (" ", "\t") and items:
                    items[-1][2] += " " + lines[i].strip()
                elif not lines[i].strip() and i + 1 < len(lines) and _LIST.match(lines[i + 1]):
                    pass
                else:
                    break
                i += 1
            out.append(_list(items, href))
            continue
        paragraph = []
        while i < len(lines) and lines[i].strip() and not _block_start(lines, i):
            paragraph.append(lines[i].strip())
            i += 1
        out.append(f"<p>{'<br>'.join(_inline(p, href) for p in _join_soft(paragraph))}</p>")
    if notes:
        out.append("<hr><ol>" + "".join(f'<li id="fn-{esc(_slug(n))}">{_inline(t, href)}</li>' for n, t in notes)
                   + "</ol>")
    return "\n".join(out)


def _join_soft(lines: list[str]) -> list[str]:
    """Lines of a paragraph; a line ending with two spaces or a backslash is a hard break."""
    result, current = [], []
    for line in lines:
        current.append(line.rstrip("\\"))
        if line.endswith("\\"):
            result.append(" ".join(current))
            current = []
    if current:
        result.append(" ".join(current))
    return result


def _block_start(lines: list[str], i: int) -> bool:
    line = lines[i]
    return bool(_FENCE.match(line) or _HEADING.match(line) or _LIST.match(line) or _HR.match(line)
                or line.lstrip().startswith(">") or _FOOTNOTE.match(line)
                or ("|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1])))


def _list(items: list[list], href) -> str:
    html_parts, stack = [], []  # stack of (indent, tag)
    for indent, ordered, text in items:
        tag = "ol" if ordered else "ul"
        while stack and indent < stack[-1][0]:
            html_parts.append(f"</li></{stack.pop()[1]}>")
        if not stack or indent > stack[-1][0]:
            html_parts.append(f"<{tag}><li>")
            stack.append((indent, tag))
        else:
            html_parts.append("</li><li>")
        html_parts.append(_inline(text, href))
    while stack:
        html_parts.append(f"</li></{stack.pop()[1]}>")
    return "".join(html_parts)


def _table(rows: list[str], href) -> str:
    def cells(row: str) -> list[str]:
        row = row.strip().strip("|")
        return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]

    head = "".join(f"<th>{_inline(c, href)}</th>" for c in cells(rows[0]))
    body = "".join("<tr>" + "".join(f"<td>{_inline(c, href)}</td>" for c in cells(r)) + "</tr>" for r in rows[1:])
    return f'<div class="table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


_CODE = re.compile(r"(`+)(.+?)\1")
_LINK = re.compile(r"!?\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(\s*<?([^)\s>]+)>?(?:\s+(?:&quot;.*?&quot;|'.*?'))?\s*\)")


def _inline(text: str, href) -> str:
    """Code spans as they are; links, emphasis and footnote marks in the rest."""
    result, last = [], 0
    for match in _CODE.finditer(text):
        result.append(_inline_text(text[last : match.start()], href))
        result.append(f"<code>{esc(match.group(2).strip())}</code>")
        last = match.end()
    result.append(_inline_text(text[last:], href))
    return "".join(result)


def _inline_text(text: str, href) -> str:
    text = esc(text)

    def link(match: re.Match) -> str:
        target = html.unescape(match.group(2))
        if SCHEME_RE.match(target) and not re.match(r"^(https?|mailto):", target, re.I):
            return match.group(1)  # javascript: and other schemes are not links here
        return f'<a href="{esc(href(target))}">{match.group(1)}</a>'

    text = _LINK.sub(link, text)
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"\[\^([^\]]+)\]", lambda m: f'<sup><a href="#fn-{_slug(m.group(1))}">{m.group(1)}</a></sup>', text)
    return text


def _slug(text: str) -> str:
    return re.sub(r"[\s]+", "-", re.sub(r"[^\w\s-]", "", text.strip().lower()))


def _rel(path: Path, base: Path) -> str:
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:
        return Path(path).as_posix()
