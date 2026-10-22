"""Find documents that may be outdated: their `git://` sources changed, or `stale_after` has passed."""

from __future__ import annotations

import fnmatch
import os
import subprocess
from datetime import date
from pathlib import Path

from okf.bundle import Bundle, Document, as_date
from okf.report import INFO, WARNING, Issue

GIT_SCHEME = "git://"


class GitError(RuntimeError):
    pass


def find_stale(bundle: Bundle, changed: list[str], repo_root: Path, today: date) -> list[Issue]:
    changed_paths = {normalize_repo_path(path) for path in changed if path.strip()}
    issues: list[Issue] = []
    for doc in bundle.knowledge():
        if doc.meta is None:
            continue  # broken front matter is reported by `okf validate`
        issues.extend(_changed_sources(doc, changed_paths, repo_root))
        stale_after = as_date(doc.get("freshness.stale_after", None))
        if stale_after is not None and stale_after < today:
            issues.append(
                Issue(
                    WARNING,
                    doc.path,
                    "freshness.stale_after",
                    f"Review date {stale_after} has passed (today is {today}); document is stale{_reviewer(doc)}",
                    doc.field_line("freshness.stale_after"),
                )
            )
    return issues


def _changed_sources(doc: Document, changed_paths: set[str], repo_root: Path) -> list[Issue]:
    sources = doc.get("provenance.sources", None)
    if not isinstance(sources, list) or not changed_paths:
        return []
    doc_updated = repo_relative(doc.path, repo_root) in changed_paths
    issues = []
    for source in sources:
        pattern = source_path(source)
        if pattern is None:
            continue
        matched = sorted(path for path in changed_paths if source_matches(pattern, path))
        if not matched:
            continue
        what = f"Source {source} changed"
        if matched != [pattern]:
            what += f" ({', '.join(matched)})"
        if doc_updated:
            issues.append(Issue(INFO, doc.path, "provenance.sources", f"{what}; document was updated in the same change"))
        else:
            issues.append(
                Issue(
                    WARNING,
                    doc.path,
                    "provenance.sources",
                    f"{what}; document may be outdated{_reviewer(doc)}",
                    doc.field_line("provenance.sources"),
                )
            )
    return issues


def _reviewer(doc: Document) -> str:
    verified_by = doc.get("trust.verified_by", None)
    return f", ask {verified_by} to review it" if isinstance(verified_by, str) and verified_by.strip() else ""


def source_path(source: object) -> str | None:
    """Repository path of a `git://` source; None for other kinds of sources (URLs, jira://, ...)."""
    if not isinstance(source, str) or not source.startswith(GIT_SCHEME):
        return None
    path = source[len(GIT_SCHEME) :].split("#", 1)[0].split("?", 1)[0]
    return normalize_repo_path(path) or None


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


def repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return Path(os.path.relpath(path, repo_root)).as_posix()


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
