"""The few git calls okf needs: repository root and the files a change touches."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Change:
    status: str  # A added, M modified, D deleted, R renamed, C copied, T type changed
    path: str  # repository-relative, forward slashes; the new path for R and C
    old_path: str | None = None  # the old path for R and C


def changed_paths(changes: list[Change]) -> list[str]:
    """Every path a change touches, old and new names of renames included."""
    paths = []
    for change in changes:
        paths.append(change.path)
        if change.old_path:
            paths.append(change.old_path)
    return paths


def toplevel(path: Path) -> Path | None:
    try:
        return Path(_git(["rev-parse", "--show-toplevel"], cwd=path).strip())
    except GitError:
        return None


def changes_since(repo_root: Path, base: str) -> list[Change]:
    """Changes since the merge base with `base`, uncommitted ones included, with renames detected."""
    merge_base = _git(["merge-base", base, "HEAD"], cwd=repo_root).strip()
    output = _git(["diff", "--name-status", "-M", "-z", merge_base], cwd=repo_root)
    parts = output.split("\0")
    result, i = [], 0
    while i < len(parts) and parts[i]:
        status = parts[i][0]
        if status in "RC":
            result.append(Change(status, parts[i + 2], parts[i + 1]))
            i += 3
        else:
            result.append(Change(status, parts[i + 1]))
            i += 2
    return result


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
