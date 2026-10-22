"""Markdown to HTML for knowledge documents: what OKF bundles use, no external libraries.

Headings, paragraphs, nested lists, fenced code, quotes, tables, links, emphasis and footnotes
(`[^id]`; a footnote can point to the document's source with the same id). `javascript:` and other
non-web links are dropped.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Callable

from okf.bundle import SCHEME_RE

_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([\w+-]*)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_FOOTNOTE = re.compile(r"^\[\^([^\]]+)\]:\s*(.*)$")
_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_CODE = re.compile(r"(`+)(.+?)\1")
_LINK = re.compile(r"!?\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(\s*<?([^)\s>]+)>?(?:\s+(?:&quot;.*?&quot;|'.*?'))?\s*\)")


def esc(value) -> str:
    return html.escape(str(value), quote=True)


@dataclass
class _Context:
    href: Callable[[str], str]
    notes: dict[str, int] = field(default_factory=dict)  # footnote id -> its number


def markdown_html(text: str, href: Callable[[str], str] = lambda target: target,
                  footnote: Callable[[str], str | None] | None = None) -> str:
    """`href` rewrites local link targets; `footnote(id)` gives the HTML of the source a footnote cites."""
    lines = text.split("\n")
    ids = [m.group(1) for m in (_FOOTNOTE.match(line) for line in lines) if m]
    ctx = _Context(href, {note: i + 1 for i, note in enumerate(dict.fromkeys(ids))})
    body, notes = _blocks(lines, ctx)
    if notes:
        items = []
        for note, text_ in notes:
            source = footnote(note) if footnote else None
            link = f" — {source}" if source else ""
            items.append(f'<li id="fn-{esc(slug(note))}">{_inline(text_, ctx)}{link} '
                         f'<a href="#fnref-{esc(slug(note))}" aria-label="Назад к тексту">↩</a></li>')
        body.append(f'<section class="footnotes" aria-label="Сноски"><hr><ol>{"".join(items)}</ol></section>')
    return "\n".join(body)


def _blocks(lines: list[str], ctx: _Context) -> tuple[list[str], list[tuple[str, str]]]:
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
            out.append(f'<h{level} id="{esc(slug(title))}">{_inline(title, ctx)}</h{level}>')
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
            inner, _ = _blocks(quoted, ctx)
            out.append(f"<blockquote>{''.join(inner)}</blockquote>")
            continue
        if "|" in line and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            rows = [line]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(lines[i])
                i += 1
            out.append(_table(rows, ctx))
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
            out.append(_list(items, ctx))
            continue
        paragraph = []
        while i < len(lines) and lines[i].strip() and not _block_start(lines, i):
            paragraph.append(lines[i].strip())
            i += 1
        out.append(f"<p>{'<br>'.join(_inline(p, ctx) for p in _join_soft(paragraph))}</p>")
    return out, notes


def _join_soft(lines: list[str]) -> list[str]:
    """Lines of a paragraph; a line ending with a backslash is a hard break."""
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


def _list(items: list[list], ctx: _Context) -> str:
    parts, stack = [], []  # stack of (indent, tag)
    for indent, ordered, text in items:
        tag = "ol" if ordered else "ul"
        while stack and indent < stack[-1][0]:
            parts.append(f"</li></{stack.pop()[1]}>")
        if not stack or indent > stack[-1][0]:
            parts.append(f"<{tag}><li>")
            stack.append((indent, tag))
        else:
            parts.append("</li><li>")
        parts.append(_inline(text, ctx))
    while stack:
        parts.append(f"</li></{stack.pop()[1]}>")
    return "".join(parts)


def _table(rows: list[str], ctx: _Context) -> str:
    def cells(row: str) -> list[str]:
        row = row.strip().strip("|")
        return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]

    head = "".join(f"<th>{_inline(c, ctx)}</th>" for c in cells(rows[0]))
    body = "".join("<tr>" + "".join(f"<td>{_inline(c, ctx)}</td>" for c in cells(r)) + "</tr>" for r in rows[1:])
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _inline(text: str, ctx: _Context) -> str:
    """Code spans as they are; links, emphasis and footnote marks in the rest."""
    result, last = [], 0
    for match in _CODE.finditer(text):
        result.append(_inline_text(text[last : match.start()], ctx))
        result.append(f"<code>{esc(match.group(2).strip())}</code>")
        last = match.end()
    result.append(_inline_text(text[last:], ctx))
    return "".join(result)


def _inline_text(text: str, ctx: _Context) -> str:
    text = esc(text)

    def link(match: re.Match) -> str:
        target = html.unescape(match.group(2))
        if SCHEME_RE.match(target) and not re.match(r"^(https?|mailto):", target, re.I):
            return match.group(1)  # javascript: and other schemes are not links here
        return f'<a href="{esc(ctx.href(target))}">{match.group(1)}</a>'

    def note(match: re.Match) -> str:
        key = html.unescape(match.group(1))
        number = ctx.notes.get(key, key)
        return f'<sup id="fnref-{esc(slug(key))}"><a href="#fn-{esc(slug(key))}">{esc(number)}</a></sup>'

    text = _LINK.sub(link, text)
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"\[\^([^\]]+)\]", note, text)


def slug(text: str) -> str:
    return re.sub(r"[\s]+", "-", re.sub(r"[^\w\s-]", "", text.strip().lower()))
