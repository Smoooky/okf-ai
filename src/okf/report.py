"""Issues and the `[LEVEL] file: field: message` output format."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"

_GITHUB_COMMANDS = {ERROR: "error", WARNING: "warning", INFO: "notice"}


@dataclass(frozen=True)
class Issue:
    level: str
    path: Path
    field: str
    message: str
    line: int | None = None


def display_path(path: Path) -> str:
    """Path relative to the working directory when possible, always with forward slashes."""
    try:
        return Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def format_text(issue: Issue) -> str:
    return f"[{issue.level}] {display_path(issue.path)}: {issue.field}: {issue.message}"


def format_github(issue: Issue) -> str:
    """GitHub Actions workflow command, shown as an annotation on the PR."""
    props = f"file={_escape_property(display_path(issue.path))},line={issue.line or 1}"
    props += f",title={_escape_property('okf ' + issue.field)}"
    return f"::{_GITHUB_COMMANDS[issue.level]} {props}::{_escape_data(issue.message)}"


def format_issue(issue: Issue, fmt: str = "text") -> str:
    return format_github(issue) if fmt == "github" else format_text(issue)


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")
