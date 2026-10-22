"""`okf stale`: documents whose `sources` changed, or past `stale_after`."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from okf import schema
from okf.bundle import Bundle, Document
from okf.report import INFO, WARNING, Issue

# https://github.com/<owner>/<repo>/blob/<ref>/<path>: the file is <path> in this repository.
_GITHUB_FILE_RE = re.compile(r"^https?://github\.com/[^/]+/[^/]+/(?:blob|tree)/[^/]+/(?P<path>[^?#]+)")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


class GitError(RuntimeError):
    pass


def find_stale(bundle: Bundle, changed: list[str], repo_root: Path, now: datetime) -> list[Issue]:
    repo_root = Path(repo_root).resolve()
    changed_paths = {normalize_repo_path(path) for path in changed if path.strip()}
    issues: list[Issue] = []
    for doc in bundle.concepts():
        if doc.meta is None:
            continue  # broken front matter is reported by `okf validate`
        issues.extend(_changed_sources(doc, bundle, changed_paths, repo_root))
        expires = schema.stale_after(doc)
        if expires is not None and now >= expires:
            issues.append(
                Issue(
                    WARNING,
                    doc.path,
                    "stale_after",
                    f"{doc.get('stale_after')} has passed (now {_utc(now)}); document is stale{_ask(doc)}",
                    doc.field_line("stale_after"),
                )
            )
    return issues


def _changed_sources(doc: Document, bundle: Bundle, changed_paths: set[str], repo_root: Path) -> list[Issue]:
    if not changed_paths:
        return []
    updated = _relative(doc.path, repo_root) in changed_paths
    issues = []
    for resource in schema.sources(doc):
        patterns = resource_paths(resource, doc, bundle.root, repo_root)
        matched = sorted(path for path in changed_paths if any(source_matches(p, path) for p in patterns))
        if not matched:
            continue
        what = f"Source {resource} changed"
        if matched != [resource]:
            what += f" ({', '.join(matched)})"
        if updated:
            issues.append(Issue(INFO, doc.path, "sources", f"{what}; document was updated in the same change"))
        else:
            issues.append(
                Issue(WARNING, doc.path, "sources", f"{what}; document may be outdated{_ask(doc)}", doc.field_line("sources"))
            )
    return issues


def resource_paths(resource: str, doc: Document, bundle_root: Path, repo_root: Path) -> list[str]:
    """Repository paths a `sources[].resource` may point to.

    `/path` is relative to the bundle root, `./path` and `../path` to the concept file,
    a bare `path` to either (the official examples write bundle-root paths that way),
    and a GitHub blob URL names `<path>` in this repository. Other URLs and scope
    descriptors point nowhere.
    """
    match = _GITHUB_FILE_RE.match(resource)
    if match:
        return [normalize_repo_path(unquote(match.group("path")))]
    if _SCHEME_RE.match(resource):
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
        relative = _relative(Path(os.path.normpath(candidate)), repo_root)
        if relative and not relative.startswith("..") and relative not in result:
            result.append(relative)
    return result


def source_matches(pattern: str, changed_path: str) -> bool:
    """A source is a file, a directory (matches everything under it) or a glob."""
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatchcase(changed_path, pattern)
    pattern = pattern.rstrip("/")
    return changed_path == pattern or changed_path.startswith(pattern + "/")


def normalize_repo_path(path: str) -> str:
    path = path.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.lstrip("/")


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return Path(os.path.relpath(path, repo_root)).as_posix()
    except ValueError:  # another drive on Windows
        return ""


def _ask(doc: Document) -> str:
    who = schema.reviewer(doc)
    return f", ask {who} to review it" if who else ""


def _utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_toplevel(path: Path) -> Path | None:
    try:
        return Path(_git(["rev-parse", "--show-toplevel"], cwd=path).strip())
    except GitError:
        return None


def git_changed_files(repo_root: Path, base: str) -> list[str]:
    """Files changed since the merge base with `base`, including uncommitted changes."""
    merge_base = _git(["merge-base", base, "HEAD"], cwd=repo_root).strip()
    output = _git(["diff", "--name-only", "--no-renames", "-z", merge_base], cwd=repo_root)
    return [path for path in output.split("\0") if path]


def _git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False
        )
    except OSError as exc:
        raise GitError(f"cannot run git: {exc}") from exc
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout
