"""Reading an OKF bundle: file discovery, YAML front matter, markdown links."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import unquote

import yaml

from okf.schema import GENERATED_FILES, RESERVED_FILES
from okf.values import MISSING, describe

# Directories no okf command looks into: version control, dependencies, virtual environments, caches,
# build output and vendored code (other projects' AGENTS.md are not this repository's instructions).
SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".tox", ".pytest_cache",
             ".mypy_cache", "vendor", "third_party", "third-party"}


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps dates as strings, so a bad date is a field error, not a YAML crash."""


_Loader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(text: str):
    """YAML with dates kept as strings, as everywhere in okf."""
    return yaml.load(text, Loader=_Loader)


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
        for line, number in _markdown_lines(self.body, self.body_line):
            match = HEADING_RE.match(line)
            if match and len(match.group(1)) == level:
                yield match.group(2), number

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
            line = CODE_SPAN_RE.sub("", line)
            for match in LINK_RE.finditer(line):
                yield match.group(1).strip("<>"), number
            match = REF_DEF_RE.match(line)
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
        if not target or target.startswith("#") or SCHEME_RE.match(target):
            return None
        path = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not path:
            return None
        base = self.root if path.startswith("/") else doc.path.parent
        return Path(os.path.normpath(base / path.lstrip("/")))


def walk(root: Path, keep_hidden: Iterable[str] = ()) -> Iterator[tuple[Path, list[str], list[str]]]:
    """os.walk in sorted order without SKIP_DIRS and hidden directories (except `keep_hidden`).
    The one way every command looks through a repository or a bundle; clearing the yielded
    directory list stops the walk below that directory."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and (not d.startswith(".") or d in keep_hidden))
        yield Path(dirpath), dirnames, sorted(filenames)


def discover(root: Path) -> list[Path]:
    return [directory / name for directory, _, filenames in walk(root) for name in filenames
            if name.lower().endswith(".md")]


def relative_path(path: Path, base: Path, fallback: str | None = None) -> str:
    """`path` from `base` with forward slashes; on another Windows drive, `fallback` (else the path itself)."""
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:
        return Path(path).as_posix() if fallback is None else fallback


def load_document(path: Path, root: Path) -> Document:
    doc = Document(path=path, rel=path.relative_to(root).as_posix())
    try:
        doc.text = path.read_text(encoding="utf-8").lstrip("﻿")
    except (OSError, UnicodeDecodeError) as exc:
        doc.read_error = f"Cannot read file as UTF-8 text: {exc}"
        return doc
    _parse_front_matter(doc)
    return doc


def opens_front_matter(line: str) -> bool:
    return line.lstrip("\ufeff").rstrip() == "---"


def front_matter_end(lines: list[str]) -> int:
    """1-based number of the line that closes the YAML front matter (`---` or `...`), 0 if the text
    has no front matter or it is not closed. The one rule for reading and for writing front matter."""
    if not lines or not opens_front_matter(lines[0]):
        return 0
    return next((i + 1 for i in range(1, len(lines)) if lines[i].rstrip() in ("---", "...")), 0)


def _parse_front_matter(doc: Document) -> None:
    lines = doc.text.split("\n")
    if not opens_front_matter(lines[0]):
        doc.body = doc.text
        return
    doc.has_front_matter = True
    end = front_matter_end(lines) - 1  # index of the closing line
    if end < 0:
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


FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([\w+-]*)")  # a code fence and its info word (the language)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
CODE_SPAN_RE = re.compile(r"(`+).+?\1")
LINK_RE = re.compile(
    r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]"  # [text], one level of nested brackets allowed
    r"\(\s*(<[^>\n]*>|[^)\s]+)"  # (target
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"  # optional "title")
)
REF_DEF_RE = re.compile(r"^\s{0,3}\[(?!\^)[^\]]+\]:\s*(<[^>\n]*>|\S+)")  # footnotes [^id]: are not links
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


def closes_fence(line: str, fence: str) -> bool:
    """A closing fence: the same character, at least as long, nothing after it."""
    match = FENCE_RE.match(line)
    return bool(match) and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
        and not line.strip()[len(match.group(1)):].strip()


def fenced(lines: list[str]) -> Iterator[tuple[int, str, str | None, bool]]:
    """(index, line, info, is_fence) per line: `info` is None outside fenced code, else the fence's
    language ("" without one); `is_fence` marks the opening and closing fence lines themselves."""
    fence, info = None, ""
    for index, line in enumerate(lines):
        if fence is None:
            match = FENCE_RE.match(line)
            if match:
                fence, info = match.group(1), match.group(2)
                yield index, line, info, True
            else:
                yield index, line, None, False
        elif closes_fence(line, fence):
            fence = None
            yield index, line, info, True
        else:
            yield index, line, info, False


def _markdown_lines(body: str, first_line: int) -> Iterator[tuple[str, int]]:
    """Body lines outside fenced code blocks."""
    for offset, line, info, _ in fenced(body.split("\n")):
        if info is None:
            yield line, first_line + offset
