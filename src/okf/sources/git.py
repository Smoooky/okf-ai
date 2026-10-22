"""Files of this repository: the git connector, the one every other connector is measured against."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from okf.bundle import SCHEME_RE, Document
from okf.git import History, commit_at, diff_since, is_glob, source_matches
from okf.sources.base import Source

__all__ = ["GITHUB_FILE_RE", "GitSource", "is_glob", "normalize_repo_path", "relative_path", "resource_paths",
           "source_matches"]

# https://github.com/<owner>/<repo>/blob/<ref>/<path>: the file is <path> in this repository.
GITHUB_FILE_RE = re.compile(r"^https?://github\.com/[^/]+/[^/]+/(?:blob|tree)/[^/]+/(?P<path>[^?#]+)")


class GitSource(Source):
    """A path in the repository (or a GitHub link to one); its history is `git log`.

    The resources it answers about are repository paths: `resource_paths` turns what an OKF
    document wrote (`/x` from the bundle root, `./x` from the document, a GitHub URL) into them.
    """

    name = "git"

    def __init__(self, root: Path | None = None, history: History | None = None, env=None, http=None):
        super().__init__(env or {}, http)
        self.root = Path(root).resolve() if root else None
        self.history = history

    def matches(self, resource: str) -> bool:
        return bool(GITHUB_FILE_RE.match(resource)) or not SCHEME_RE.match(resource)

    def paths(self, resource: str, doc: Document, bundle_root: Path, repo_root: Path) -> list[str]:
        return resource_paths(resource, doc, bundle_root, repo_root)

    def last_modified(self, resource: str) -> datetime | None:
        if self.history is None or self.root is None:
            return None
        return self.history.last_change(self.root / resource)

    def changes_since(self, resource: str | list[str], since: datetime | str) -> str | None:
        """`git diff` of one path or several since a moment, or since a commit (the base of a pull request)."""
        if self.history is None or self.history.root is None:
            return None
        paths = [resource] if isinstance(resource, str) else list(resource)
        commit = since if isinstance(since, str) else commit_at(self.history.root, since)
        return diff_since(self.history.root, commit or "", paths) or None

    def describe(self, resource: str) -> str:
        return resource


def resource_paths(resource: str, doc: Document, bundle_root: Path, repo_root: Path) -> list[str]:
    """Repository paths a `sources[].resource` may point to.

    `/path` is relative to the bundle root, `./path` and `../path` to the concept file,
    a bare `path` to either (the official examples write bundle-root paths that way),
    and a GitHub blob URL names `<path>` in this repository. Other URLs and scope
    descriptors point nowhere.
    """
    match = GITHUB_FILE_RE.match(resource)
    if match:
        return [normalize_repo_path(unquote(match.group("path")))]
    if SCHEME_RE.match(resource):
        return []
    path = unquote(resource.split("#", 1)[0].split("?", 1)[0]).strip()
    if not path:
        return []
    if path.startswith("/"):
        candidates = [bundle_root / path.lstrip("/")]
    elif path.startswith(("./", "../")):
        candidates = [doc.path.parent / path]
    else:
        candidates = [doc.path.parent / path, bundle_root / path]
    result = []
    for candidate in candidates:
        relative = relative_path(Path(os.path.normpath(candidate)), repo_root)
        if relative and not relative.startswith("..") and relative not in result:
            result.append(relative)
    return result


def normalize_repo_path(path: str) -> str:
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def relative_path(path: Path, repo_root: Path) -> str:
    try:
        return Path(os.path.relpath(path, repo_root)).as_posix()
    except ValueError:  # another drive on Windows
        return ""
