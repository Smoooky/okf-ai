"""Reading an OKF bundle: file discovery, YAML front matter, markdown links."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import unquote

import yaml

from okf.schema import GENERATED_FILES, RESERVED_FILES
from okf.values import MISSING, describe

IGNORED_DIRS = {"node_modules", "__pycache__", "venv"}


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps dates as strings, so a bad date is a field error, not a YAML crash."""


_Loader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


@dataclass
class Document:
    path: Path  # absolute
    rel: str  # relative to the bundle root, forward slashes
    text: str | None = None  # None if the file could not be read
    read_error: str | None = None
    has_front_matter: bool = False
    meta: dict | None = None  # parsed front matter if it is a valid mapping
    meta_error: str | None = None
    meta_error_line: int | None = None
    front_matter_lines: list[str] = field(default_factory=list)
    body: str = ""
    body_line: int = 1  # 1-based line where the body starts

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_reserved(self) -> bool:
        """index.md or log.md at any level (OKF §3.1)."""
        return self.name in RESERVED_FILES

    @property
    def is_generated(self) -> bool:
        return self.rel in GENERATED_FILES

    @property
    def is_concept(self) -> bool:
        return not (self.is_reserved or self.is_generated)

    @property
    def title(self) -> str:
        if self.meta and isinstance(self.meta.get("title"), str) and self.meta["title"].strip():
            return self.meta["title"].strip()
        for heading, _ in self.headings(level=1):
            return heading
        return self.path.stem.replace("_", " ").replace("-", " ")

    def headings(self, level: int) -> Iterator[tuple[str, int]]:
        """ATX headings of one level in the body, with line numbers (code is skipped)."""
        pattern = re.compile(rf"^#{{{level}}}\s+(.+?)\s*#*\s*$")
        for line, number in _markdown_lines(self.body, self.body_line):
            match = pattern.match(line)
            if match:
                yield match.group(1), number

    def get(self, dotted: str, default: Any = MISSING) -> Any:
        """Nested front matter value by dotted path, e.g. `generated.by`."""
        value: Any = self.meta if self.meta is not None else {}
        for part in dotted.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    def field_line(self, dotted: str) -> int | None:
        """Best-effort line number of a front matter key, for CI annotations."""
        found = None
        start, indent = 0, -1
        for part in re.sub(r"\[\d+\]", "", dotted).split("."):
            pattern = re.compile(rf"^(\s*)(?:-\s+)?[\"']?{re.escape(part)}[\"']?\s*:")
            for i in range(start, len(self.front_matter_lines)):
                match = pattern.match(self.front_matter_lines[i])
                if match and len(match.group(1)) > indent:
                    found, start, indent = i + 2, i + 1, len(match.group(1))
                    break
            else:
                break
        return found

    def links(self) -> Iterator[tuple[str, int]]:
        """Markdown link targets in the body with their line numbers (code is skipped)."""
        for line, number in _markdown_lines(self.body, self.body_line):
            line = _CODE_SPAN_RE.sub("", line)
            for match in _INLINE_LINK_RE.finditer(line):
                yield match.group(1).strip("<>"), number
            match = _REF_DEF_RE.match(line)
            if match:
                yield match.group(1).strip("<>"), number


@dataclass
class Bundle:
    root: Path
    documents: list[Document]

    @classmethod
    def load(cls, root: Path | str) -> "Bundle":
        root = Path(root).resolve()
        return cls(root, [load_document(path, root) for path in discover(root)])

    def concepts(self) -> list[Document]:
        return [doc for doc in self.documents if doc.is_concept]

    def resolve_link(self, doc: Document, target: str) -> Path | None:
        """Absolute path a local link points to, or None for external links and anchors."""
        if not target or target.startswith("#") or _SCHEME_RE.match(target):
            return None
        path = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not path:
            return None
        base = self.root if path.startswith("/") else doc.path.parent
        return Path(os.path.normpath(base / path.lstrip("/")))


def discover(root: Path) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in IGNORED_DIRS)
        found.extend(Path(dirpath) / name for name in sorted(filenames) if name.lower().endswith(".md"))
    return found


def load_document(path: Path, root: Path) -> Document:
    doc = Document(path=path, rel=path.relative_to(root).as_posix())
    try:
        doc.text = path.read_text(encoding="utf-8").lstrip("﻿")
    except (OSError, UnicodeDecodeError) as exc:
        doc.read_error = f"Cannot read file as UTF-8 text: {exc}"
        return doc
    _parse_front_matter(doc)
    return doc


def _parse_front_matter(doc: Document) -> None:
    lines = doc.text.split("\n")
    if lines[0].rstrip() != "---":
        doc.body = doc.text
        return
    doc.has_front_matter = True
    for end in range(1, len(lines)):
        if lines[end].rstrip() in ("---", "..."):
            break
    else:
        doc.meta_error = "Front matter is not closed with '---'"
        doc.meta_error_line = 1
        return
    doc.front_matter_lines = lines[1:end]
    doc.body = "\n".join(lines[end + 1 :])
    doc.body_line = end + 2
    try:
        meta = yaml.load("\n".join(doc.front_matter_lines), Loader=_Loader)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        doc.meta_error = f"Invalid YAML: {exc.problem or exc.context}"
        doc.meta_error_line = mark.line + 2 if mark else 1
        return
    except (yaml.YAMLError, ValueError, TypeError) as exc:
        doc.meta_error, doc.meta_error_line = f"Invalid YAML: {exc}", 1
        return
    if meta is None:
        doc.meta_error, doc.meta_error_line = "Front matter is empty", 1
    elif not isinstance(meta, dict):
        doc.meta_error = f"Front matter must be a YAML mapping (key: value), got {describe(meta)}"
        doc.meta_error_line = 2
    else:
        doc.meta = meta


_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_CODE_SPAN_RE = re.compile(r"(`+).+?\1")
_INLINE_LINK_RE = re.compile(
    r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]"  # [text], one level of nested brackets allowed
    r"\(\s*(<[^>\n]*>|[^)\s]+)"  # (target
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"  # optional "title")
)
_REF_DEF_RE = re.compile(r"^\s{0,3}\[(?!\^)[^\]]+\]:\s*(<[^>\n]*>|\S+)")  # footnotes [^id]: are not links
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


def _markdown_lines(body: str, first_line: int) -> Iterator[tuple[str, int]]:
    """Body lines outside fenced code blocks."""
    fence = None
    for offset, line in enumerate(body.split("\n")):
        match = _FENCE_RE.match(line)
        if fence is None and match:
            fence = match.group(1)
        elif fence is not None:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
                fence = None
        else:
            yield line, first_line + offset
