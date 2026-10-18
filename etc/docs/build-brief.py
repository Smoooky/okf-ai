#!/usr/bin/env python3
"""Собирает PDF из Markdown через headless Chrome.

Использование:
    ./build-brief.py                 # BRIEF.md -> brief.pdf
    ./build-brief.py docs/BRIEF.md docs/brief.pdf
    CHROME_BIN=/path/to/chrome ./build-brief.py

Поддерживается GitHub-flavored Markdown: заголовки, списки (включая
вложенные), таблицы, блоки кода, ссылки, выделение, цитаты, разделители.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
)

LIST_ITEM_RE = re.compile(r"^(\s*)([*+-]|\d+[.)])\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
HR_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
# Цветные эмодзи не встраиваются в PDF движком Chrome и превращаются
# в пустые глифы, поэтому убираем их из вывода.
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\uFE0F\u200D]")


def find_chrome(explicit: str | None = None) -> str:
    candidates = [explicit, os.environ.get("CHROME_BIN")] + list(CHROME_CANDIDATES)
    for name in candidates:
        if not name:
            continue
        path = shutil.which(name) or (name if Path(name).is_file() else None)
        if path:
            return path
    raise SystemExit(
        "Не найден Google Chrome / Chromium. Установите браузер "
        "или задайте CHROME_BIN=/путь/к/chrome."
    )


def strip_emoji(markdown: str) -> tuple[str, int]:
    cleaned, count = EMOJI_RE.subn("", markdown)
    return cleaned, count


def split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line)]


def is_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", cell) for cell in cells)


def is_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    if FENCE_RE.match(line) or HEADING_RE.match(line) or HR_RE.fullmatch(line):
        return True
    if line.lstrip().startswith(">"):
        return True
    if LIST_ITEM_RE.match(line):
        return True
    return "|" in line and index + 1 < len(lines) and is_separator(lines[index + 1])


def render_inline(text: str) -> str:
    """Инлайн-разметка. Код прячем до экранирования, чтобы не портить его."""
    code_spans: dict[str, str] = {}

    def keep_code(match: re.Match[str]) -> str:
        key = f"\x00CODE{len(code_spans)}\x00"
        code_spans[key] = f"<code>{html.escape(match.group(2), quote=False)}</code>"
        return key

    text = re.sub(r"(`+)(.+?)\1", keep_code, text)
    text = html.escape(text, quote=False)

    text = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+[\"']([^\"']*)[\"'])?\)",
        lambda m: (
            f'<img src="{m.group(2)}" alt="{m.group(1)}"'
            + (f' title="{m.group(3)}"' if m.group(3) else "")
            + ">"
        ),
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)(?:\s+[\"']([^\"']*)[\"'])?\)",
        lambda m: (
            f'<a href="{m.group(2)}"'
            + (f' title="{m.group(3)}"' if m.group(3) else "")
            + f">{m.group(1)}</a>"
        ),
        text,
    )
    text = re.sub(
        r"&lt;(https?://[^\s&]+?)&gt;",
        lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>',
        text,
    )

    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<em>\1</em>", text)

    for key, value in code_spans.items():
        text = text.replace(key, value)
    return text


def parse_list(lines: list[str], start: int) -> tuple[str, int]:
    """Разбирает список с поддержкой вложенности и пустых строк между пунктами."""
    first = LIST_ITEM_RE.match(lines[start])
    assert first is not None
    base_indent = len(first.group(1))
    ordered = first.group(2)[0].isdigit()
    items: list[str] = []
    i = start
    n = len(lines)

    while i < n:
        match = LIST_ITEM_RE.match(lines[i])
        if not match:
            break

        indent = len(match.group(1))
        if indent < base_indent:
            break
        if indent > base_indent:
            nested, i = parse_list(lines, i)
            if items:
                items[-1] += nested
            else:
                items.append(nested)
            continue

        marker = match.group(2)
        if marker[0].isdigit() != ordered:
            break

        parts = [match.group(3)]
        i += 1

        # Продолжение пункта: строки без маркера списка.
        while i < n and lines[i].strip() and not LIST_ITEM_RE.match(lines[i]):
            parts.append(lines[i].strip())
            i += 1

        items.append(render_inline(" ".join(parts)))

        # Пустая строка между пунктами не завершает список.
        if i < n and not lines[i].strip():
            j = i
            while j < n and not lines[j].strip():
                j += 1
            next_item = LIST_ITEM_RE.match(lines[j]) if j < n else None
            if (
                next_item
                and len(next_item.group(1)) == base_indent
                and next_item.group(2)[0].isdigit() == ordered
            ):
                i = j
                continue
            break

    tag = "ol" if ordered else "ul"
    return f"<{tag}>" + "".join(f"<li>{item}</li>" for item in items) + f"</{tag}>", i


def markdown_to_html(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            language = fence.group(2)
            i += 1
            code: list[str] = []
            while i < n and not re.fullmatch(rf"\s*{re.escape(marker)}\s*", lines[i]):
                code.append(lines[i])
                i += 1
            if i < n:
                i += 1
            language_class = f' class="language-{language}"' if language else ""
            escaped = html.escape("\n".join(code), quote=False)
            output.append(f"<pre><code{language_class}>{escaped}</code></pre>")
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            output.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if HR_RE.fullmatch(line):
            output.append("<hr>")
            i += 1
            continue

        if "|" in line and i + 1 < n and is_separator(lines[i + 1]):
            headers = split_table_row(line)
            alignment_cells = split_table_row(lines[i + 1])
            alignments: list[str] = []
            for cell in alignment_cells:
                if cell.startswith(":") and cell.endswith(":"):
                    alignments.append("center")
                elif cell.endswith(":"):
                    alignments.append("right")
                elif cell.startswith(":"):
                    alignments.append("left")
                else:
                    alignments.append("")

            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                rows.append(split_table_row(lines[i]))
                i += 1

            def render_cell(tag: str, value: str, column: int) -> str:
                align = alignments[column] if column < len(alignments) else ""
                style = f' style="text-align:{align}"' if align else ""
                return f"<{tag}{style}>{render_inline(value)}</{tag}>"

            head = "<tr>" + "".join(
                render_cell("th", value, column)
                for column, value in enumerate(headers)
            ) + "</tr>"
            body = "".join(
                "<tr>"
                + "".join(
                    render_cell("td", value, column)
                    for column, value in enumerate(row)
                )
                + "</tr>"
                for row in rows
            )
            output.append(
                f"<table><thead>{head}</thead><tbody>{body}</tbody></table>"
            )
            continue

        if line.lstrip().startswith(">"):
            quote: list[str] = []
            while i < n and lines[i].lstrip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            output.append(
                "<blockquote>" + markdown_to_html("\n".join(quote)) + "</blockquote>"
            )
            continue

        if LIST_ITEM_RE.match(line):
            rendered_list, i = parse_list(lines, i)
            output.append(rendered_list)
            continue

        paragraph = [line.strip()]
        i += 1
        while i < n and lines[i].strip() and not is_block_start(lines, i):
            paragraph.append(lines[i].strip())
            i += 1
        output.append("<p>" + render_inline(" ".join(paragraph)) + "</p>")

    return "\n".join(output)


def document_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        heading = HEADING_RE.match(line)
        if heading and len(heading.group(1)) == 1:
            title = re.sub(r"[*_`~\[\]]", "", heading.group(2)).strip()
            if title:
                return title
    return fallback


def build_html(markdown: str, base_dir: Path, title: str) -> str:
    body = markdown_to_html(markdown)
    base_href = base_dir.resolve().as_uri().rstrip("/") + "/"
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<base href="{base_href}">
<title>{html.escape(title)}</title>
<style>
  @page {{
    size: A4;
    margin: 18mm 16mm 20mm;
  }}

  * {{ box-sizing: border-box; }}
  html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}

  body {{
    margin: 0;
    font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif, "Noto Color Emoji";
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1f2328;
    hyphens: auto;
  }}

  h1, h2, h3, h4, h5, h6 {{
    font-weight: 700;
    line-height: 1.25;
    color: #111111;
    break-after: avoid;
    page-break-after: avoid;
  }}

  h1 {{
    font-size: 23pt;
    text-align: center;
    margin: 0 0 8mm;
    padding-bottom: 4mm;
    border-bottom: 3px solid #1f6feb;
  }}

  h2 {{
    font-size: 15.5pt;
    margin: 8mm 0 3mm;
    padding-bottom: 1.5mm;
    border-bottom: 1px solid #d0d7de;
  }}

  h3 {{
    font-size: 12pt;
    margin: 5mm 0 2mm;
    color: #0b3d91;
  }}

  h4 {{ font-size: 11pt; margin: 4mm 0 2mm; }}

  p {{
    margin: 0 0 3mm;
    text-align: left;
    orphans: 3;
    widows: 3;
  }}

  strong {{ font-weight: 700; }}
  em {{ font-style: italic; }}

  a {{
    color: #0b57d0;
    text-decoration: none;
    overflow-wrap: break-word;
  }}

  hr {{
    border: 0;
    border-top: 1px solid #d0d7de;
    margin: 6mm 0;
  }}

  ul, ol {{
    margin: 0 0 3mm;
    padding-left: 6mm;
  }}

  li {{ margin: 0 0 1.5mm; }}
  li > ul, li > ol {{ margin-top: 1.5mm; }}

  code {{
    font-family: "DejaVu Sans Mono", "Liberation Mono", monospace;
    font-size: 0.9em;
    background: #f6f8fa;
    padding: 0.1em 0.3em;
    border-radius: 3px;
  }}

  pre {{
    margin: 3mm 0;
    padding: 3mm 4mm;
    background: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 5px;
    white-space: pre-wrap;
    overflow-wrap: break-word;
    break-inside: avoid;
    page-break-inside: avoid;
  }}

  pre code {{
    padding: 0;
    background: none;
    font-size: 8.5pt;
    line-height: 1.4;
  }}

  blockquote {{
    margin: 3mm 0;
    padding: 2mm 4mm;
    border-left: 4px solid #d0d7de;
    background: #f8fafc;
    color: #4b5563;
  }}

  table {{
    width: 100%;
    margin: 3mm 0 4mm;
    border-collapse: collapse;
    font-size: 9pt;
    line-height: 1.4;
  }}

  thead {{ display: table-header-group; }}
  tr {{ break-inside: avoid; page-break-inside: avoid; }}

  th, td {{
    padding: 1.5mm 2mm;
    border: 1px solid #c9d1d9;
    vertical-align: top;
    text-align: left;
    overflow-wrap: break-word;
  }}

  th {{ background: #eef2f7; font-weight: 700; }}
  tbody tr:nth-child(even) td {{ background: #fafbfc; }}

  img {{
    max-width: 100%;
    height: auto;
  }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def print_to_pdf(chrome: str, html_path: Path, pdf_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="okf-pdf-") as temp_dir:
        user_data_dir = Path(temp_dir) / "profile"
        command = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            f"--user-data-dir={user_data_dir}",
            "--no-pdf-header-footer",
            "--virtual-time-budget=5000",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0 or not pdf_path.exists():
            message = result.stderr.strip() or result.stdout.strip()
            raise SystemExit(f"Chrome не смог собрать PDF:\n{message}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Собирает PDF из Markdown через headless Chrome."
    )
    parser.add_argument("input", nargs="?", default="BRIEF.md", help="входной .md")
    parser.add_argument("output", nargs="?", default="brief.pdf", help="выходной .pdf")
    parser.add_argument("--chrome", help="путь к Google Chrome / Chromium")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_path.is_file():
        raise SystemExit(f"Файл не найден: {input_path}")

    chrome = find_chrome(args.chrome)
    markdown, emoji_count = strip_emoji(input_path.read_text(encoding="utf-8"))
    if emoji_count:
        print(
            f"Удалено эмодзи: {emoji_count} "
            "(Chrome не встраивает цветные эмодзи в PDF)."
        )
    title = document_title(markdown, input_path.stem)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="okf-html-") as temp_dir:
        html_path = Path(temp_dir) / "document.html"
        html_path.write_text(
            build_html(markdown, input_path.parent, title),
            encoding="utf-8",
        )
        print_to_pdf(chrome, html_path, output_path)

    size_kb = output_path.stat().st_size / 1024
    print(f"{input_path.name} -> {output_path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
