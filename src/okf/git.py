"""The few git calls okf needs: repository root, the files a change touches, commit dates."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
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


SHALLOW_HINT = (
    "the git history is shallow (actions/checkout fetches one commit by default), so commit dates are unknown; "
    "fetch the whole history: actions/checkout with `fetch-depth: 0`, or `git fetch --unshallow`"
)


def is_shallow(repo_root: Path) -> bool:
    try:
        return _git(["rev-parse", "--is-shallow-repository"], cwd=repo_root).strip() == "true"
    except GitError:
        return False


def merge_base(repo_root: Path, base: str) -> str:
    try:
        return _git(["merge-base", base, "HEAD"], cwd=repo_root).strip()
    except GitError as exc:
        if is_shallow(repo_root):
            raise GitError(f"{exc}; {SHALLOW_HINT}") from exc
        raise


def changed_lines(repo_root: Path, commit: str, path: str) -> set[int]:
    """Lines of the current file that changed since `commit`; a pure deletion marks the lines around it."""
    try:
        output = _git(["diff", "-U0", "--no-color", "--no-ext-diff", commit, "--", path], cwd=repo_root)
    except GitError:
        return set()
    lines: set[int] = set()
    for match in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", output, re.M):
        start, count = int(match.group(1)), int(match.group(2) if match.group(2) is not None else 1)
        lines.update({start, start + 1} if count == 0 else range(start, start + count))
    return lines


def changes_since(repo_root: Path, base: str) -> list[Change]:
    """Changes since the merge base with `base`, uncommitted ones included, with renames detected."""
    output = _git(["diff", "--name-status", "-M", "-z", merge_base(repo_root, base)], cwd=repo_root)
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


class History:
    """Commit dates, cached: when a path last changed, when each line of a file was last edited.

    Uncommitted changes are dated by the file modification time. Dates are whole seconds, like
    the timestamps okf writes. Without a git repository, or with a shallow one (where the oldest
    commit seems to touch every file), every date is None.
    """

    def __init__(self, root: Path | None, now: datetime | None = None):
        self.root = Path(root).resolve() if root else None
        self.now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
        self.shallow = bool(self.root) and is_shallow(self.root)
        self._last: dict[str, datetime | None] = {}
        self._lines: dict[Path, list[datetime | None]] = {}
        self._moves: dict[str, tuple[Path, datetime | None] | None] = {}
        self._dirty: set[str] | None = None

    @property
    def dated(self) -> bool:
        return self.root is not None and not self.shallow

    def moved(self, path: Path) -> tuple[Path, datetime | None] | None:
        """Where a file that no longer exists went: (new path, when), following renames in history."""
        if not self.dated:
            return None
        relative = self.relative(path)
        if relative is None or relative.startswith("../"):
            return None
        if relative not in self._moves:
            self._moves[relative] = self._follow(relative)
        return self._moves[relative]

    def _follow(self, current: str) -> tuple[Path, datetime | None] | None:
        when = None
        for _ in range(5):  # a file renamed a few times
            try:
                last = _git(["log", "-1", "--format=%H %cI", "--", current], cwd=self.root).split()
                if len(last) != 2:
                    return None
                # Without a pathspec, so that git pairs the old and the new name.
                shown = _git(["show", "-M", "--name-status", "--format=", last[0]], cwd=self.root)
            except GitError:
                return None
            when = _instant(last[1])
            renamed = [p[2] for p in (line.split("\t") for line in shown.splitlines())
                       if len(p) == 3 and p[0].startswith("R") and p[1] == current]
            if not renamed:
                return None
            current = renamed[0]
            if (self.root / current).exists():
                return self.root / current, when
        return None

    def last_change(self, path: Path) -> datetime | None:
        """Last commit date (%cI) touching a file (following renames), a directory or a glob."""
        if not self.dated:
            return None
        relative = self.relative(path)
        if relative is None:
            return None
        if relative not in self._last:
            dirty = [d for d in self.dirty() if d == relative or d.startswith(relative.rstrip("/") + "/")]
            if dirty:
                self._last[relative] = max(self._modified(self.root / d) for d in dirty)
            else:
                spec = f":(glob){relative}" if any(ch in relative for ch in "*?[") else relative
                follow = ["--follow"] if (self.root / relative).is_file() else []
                try:
                    output = _git(["log", "-1", *follow, "--format=%cI", "--", spec], cwd=self.root).strip()
                except GitError:
                    output = ""
                self._last[relative] = _instant(output)
        return self._last[relative]

    def line_dates(self, path: Path) -> list[datetime | None]:
        """Per line of a file (index 0 is line 1): when it was last edited, from git blame."""
        path = Path(path).resolve()
        if path not in self._lines:
            dates: list[datetime | None] = []
            relative = self.relative(path)
            if self.dated and relative is not None:
                try:
                    blamed = _blame(_git(["blame", "--porcelain", "--", relative], cwd=self.root))
                    dates = [d or self._modified(path) for d in blamed]
                except GitError:  # not tracked yet: every line is as new as the file
                    lines = path.read_text(encoding="utf-8", errors="replace").count("\n") + 1
                    dates = [self._modified(path)] * lines
            self._lines[path] = dates
        return self._lines[path]

    def dirty(self) -> set[str]:
        """Uncommitted paths: modified, staged, untracked, both sides of renames."""
        if self._dirty is None:
            self._dirty = set()
            if self.root is not None:
                try:
                    output = _git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=self.root)
                except GitError:
                    output = ""
                parts, i = output.split("\0"), 0
                while i < len(parts) and parts[i]:
                    status, path = parts[i][:2], parts[i][3:]
                    self._dirty.add(path)
                    if status[0] in "RC" and i + 1 < len(parts):
                        self._dirty.add(parts[i + 1])
                        i += 1
                    i += 1
        return self._dirty

    def _modified(self, path: Path) -> datetime:
        try:
            return datetime.fromtimestamp(int(path.stat().st_mtime), timezone.utc)
        except OSError:  # deleted
            return self.now

    def relative(self, path: Path) -> str | None:
        try:
            return Path(os.path.relpath(Path(path).resolve() if "*" not in str(path) else path, self.root)).as_posix()
        except ValueError:  # another drive on Windows
            return None


def _instant(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(microsecond=0) if text else None
    except ValueError:
        return None


def _blame(output: str) -> list[datetime | None]:
    """Committer time per line; None for lines not committed yet."""
    times: dict[str, datetime] = {}
    by_line: dict[int, str] = {}
    commit, final = None, 0
    for line in output.split("\n"):
        header = re.match(r"^([0-9a-f]{40}) \d+ (\d+)", line)
        if header:
            commit, final = header.group(1), int(header.group(2))
        elif line.startswith("committer-time ") and commit and commit != "0" * 40:
            times[commit] = datetime.fromtimestamp(int(line.split()[1]), timezone.utc)
        elif line.startswith("\t") and commit:
            by_line[final] = commit
    return [times.get(by_line.get(number, ""), None) for number in range(1, max(by_line, default=0) + 1)]


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
