"""The few git calls okf needs: repository root, the files a change touches, commit dates."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class GitError(RuntimeError):
    pass


def is_glob(path: str) -> bool:
    return any(ch in path for ch in "*?[")


def source_matches(pattern: str, changed_path: str) -> bool:
    """Does a source (a file, a directory: everything under it, or a glob) cover a changed path?
    Both are relative to the same root, with forward slashes. The one rule every command uses."""
    if is_glob(pattern):
        return fnmatch.fnmatchcase(changed_path, pattern)
    pattern = pattern.rstrip("/")
    return changed_path == pattern or changed_path.startswith(pattern + "/")


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
        return Path(run_git(["rev-parse", "--show-toplevel"], cwd=path).strip())
    except GitError:
        return None


SHALLOW_HINT = (
    "the git history is shallow (actions/checkout fetches one commit by default), so commit dates are unknown; "
    "fetch the whole history: actions/checkout with `fetch-depth: 0`, or `git fetch --unshallow`"
)


def is_shallow(repo_root: Path) -> bool:
    try:
        return run_git(["rev-parse", "--is-shallow-repository"], cwd=repo_root).strip() == "true"
    except GitError:
        return False


def merge_base(repo_root: Path, base: str) -> str:
    try:
        return run_git(["merge-base", base, "HEAD"], cwd=repo_root).strip()
    except GitError as exc:
        if is_shallow(repo_root):
            raise GitError(f"{exc}; {SHALLOW_HINT}") from exc
        raise


def changed_lines(repo_root: Path, commit: str, path: str) -> set[int]:
    """Lines of the current file that changed since `commit`; a pure deletion marks the lines around it."""
    try:
        output = run_git(["diff", "-U0", "--no-color", "--no-ext-diff", commit, "--", path], cwd=repo_root)
    except GitError:
        return set()
    lines: set[int] = set()
    for match in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", output, re.M):
        start, count = int(match.group(1)), int(match.group(2) if match.group(2) is not None else 1)
        lines.update({start, start + 1} if count == 0 else range(start, start + count))
    return lines


def changes_since(repo_root: Path, base: str) -> list[Change]:
    """Changes since the merge base with `base`, uncommitted ones included, with renames detected."""
    output = run_git(["diff", "--name-status", "-M", "-z", merge_base(repo_root, base)], cwd=repo_root)
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
                last = run_git(["log", "-1", "--format=%H %cI", "--", current], cwd=self.root).split()
                if len(last) != 2:
                    return None
                # Without a pathspec, so that git pairs the old and the new name.
                shown = run_git(["show", "-M", "--name-status", "--format=", last[0]], cwd=self.root)
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
            dirty = [d for d in self.dirty() if source_matches(relative, d)]
            if dirty:
                self._last[relative] = max(self._modified(self.root / d) for d in dirty)
            else:
                spec = f":(glob){relative}" if is_glob(relative) else relative
                follow = ["--follow"] if (self.root / relative).is_file() else []
                try:
                    output = run_git(["log", "-1", *follow, "--format=%cI", "--", spec], cwd=self.root).strip()
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
                    blamed = _blame(run_git(["blame", "--porcelain", "--", relative], cwd=self.root))
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
                    output = run_git(["status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=self.root)
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


EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # what a diff "since before the first commit" starts from


def commit_at(repo_root: Path, moment: datetime) -> str:
    """The last commit on HEAD at `moment` (the empty tree if the history starts later)."""
    try:
        found = run_git(["rev-list", "-1", f"--before={moment.astimezone(timezone.utc).isoformat()}", "HEAD"],
                     cwd=repo_root).strip()
    except GitError:
        found = ""
    return found or EMPTY_TREE


def diff_since(repo_root: Path, commit: str, paths: list[str]) -> str:
    """What changed in `paths` from `commit` to the working tree."""
    if not paths:
        return ""
    try:
        return run_git(["diff", "--no-color", "--no-ext-diff", "-M", commit, "--", *paths], cwd=repo_root)
    except GitError:
        return ""


def file_at(repo_root: Path, commit: str, path: str) -> str | None:
    try:
        return run_git(["show", f"{commit}:{path}"], cwd=repo_root)
    except GitError:
        return None


def commits_changing_count(repo_root: Path, text: str, path: str) -> list[str]:
    """Commits that added or removed `text` in `path`, newest first (`git log -S`)."""
    try:
        return run_git(["log", "--format=%H", f"-S{text}", "--", path], cwd=repo_root).split()
    except GitError:
        return []


def head_info(repo_root: Path | None) -> tuple[str | None, str | None]:
    """(branch, short commit) of the checkout, for page headers; Nones outside git."""
    if repo_root is None:
        return None, None
    try:
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root).strip()
        sha = run_git(["rev-parse", "--short", "HEAD"], cwd=repo_root).strip()
    except GitError:
        return None, None
    return (None if branch == "HEAD" else branch), sha


def line_url(web: str | None, git_root: Path | None, path: Path, line: int) -> str | None:
    """https://github.com/<repo>/blob/<commit>/<path>#L<line>, or None off GitHub."""
    if not web or git_root is None:
        return None
    return f"{web}/{Path(os.path.relpath(path, git_root)).as_posix()}#L{line}"


def web_base(repo_root: Path | None, env=None) -> str | None:
    """https://github.com/<owner>/<repo>/blob/<commit> for links to lines: from the GitHub Actions
    environment, else from the origin remote and HEAD. None if the repository is not on GitHub."""
    env = os.environ if env is None else env
    if env.get("GITHUB_REPOSITORY") and env.get("GITHUB_SHA"):
        server = (env.get("GITHUB_SERVER_URL") or "https://github.com").rstrip("/")
        return f"{server}/{env['GITHUB_REPOSITORY']}/blob/{env['GITHUB_SHA']}"
    if repo_root is None:
        return None
    try:
        remote = run_git(["remote", "get-url", "origin"], cwd=repo_root).strip()
        commit = run_git(["rev-parse", "HEAD"], cwd=repo_root).strip()
    except GitError:
        return None
    match = re.match(r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)"
                     r"([\w.-]+/[\w.-]+?)(?:\.git)?/?$", remote)
    return f"https://github.com/{match.group(1)}/blob/{commit}" if match else None


# --- Running git and gh: every okf command goes through these --------------------------


def _run(tool: str, args: list[str], cwd: Path | None, timeout: float | None = None,
         env: dict | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run([tool, *args], cwd=cwd, capture_output=True, stdin=subprocess.DEVNULL,
                              timeout=timeout, env=env, check=False)
    except OSError as exc:
        hint = " (https://cli.github.com)" if tool == "gh" else ""
        raise GitError(f"cannot run {tool}{hint}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"{tool} {_command(args)} took longer than {timeout:g} s") from exc


def _command(args: list[str]) -> str:
    """The subcommand for messages: `git -c user.name=x commit -m ...` -> `commit`."""
    words = [a for i, a in enumerate(args) if a != "-c" and (i == 0 or args[i - 1] != "-c")]
    return " ".join(words[:2]) if words and words[0] in ("pr", "api", "auth", "worktree") else (words or [""])[0]


def run_git(args: list[str], cwd: Path | None, *, timeout: float | None = None, env: dict | None = None) -> str:
    """git's stdout; a failure raises GitError("git <subcommand> failed: <stderr>")."""
    result = _run("git", args, cwd, timeout, env)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise GitError(f"git {_command(args)} failed: {stderr}")
    return result.stdout.decode("utf-8", "replace")


def git_ok(args: list[str], cwd: Path | None) -> bool:
    """Did git succeed (exit 0)? False if git cannot run."""
    try:
        return _run("git", args, cwd).returncode == 0
    except GitError:
        return False


def git_bytes(args: list[str], cwd: Path | None) -> bytes | None:
    """Raw stdout (e.g. `ls-files -z`), None on any failure."""
    try:
        result = _run("git", args, cwd)
    except GitError:
        return None
    return result.stdout if result.returncode == 0 else None


def git_config(key: str, cwd: Path | None) -> str | None:
    """A git setting (`user.email`), or None when it is not set or git cannot run."""
    try:
        return run_git(["config", key], cwd).strip() or None
    except GitError:
        return None


def run_gh(args: list[str], cwd: Path | None = None, rate_limit_waits: int = 0,
           sleep=None) -> str:
    """The GitHub CLI's stdout; a failure raises GitError("gh <subcommand> failed: <stderr>").
    With `rate_limit_waits`, a rate-limited call waits 30 s and tries again that many times."""
    for attempt in range(rate_limit_waits + 1):
        result = _run("gh", args, cwd)
        if result.returncode == 0:
            return result.stdout.decode("utf-8", "replace")
        stderr = result.stderr.decode("utf-8", "replace").strip()
        if "rate limit" in stderr.lower() and attempt < rate_limit_waits:
            (sleep or _sleep)(30)
            continue
        raise GitError(f"gh {_command(args)} failed: {stderr}")
    raise GitError(f"gh {_command(args)} failed")  # not reached


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
