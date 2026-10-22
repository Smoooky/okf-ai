"""`okf fix --pr`: the Freshness Engine from the brief. The fixes go to a branch and a pull request.

The branch is `okf/update-<base>-<short sha>`, the commit holds the mechanical fixes and the accepted
LLM drafts, and the pull request (`gh pr create`) is titled `[OKF-Update] …` and says what changed,
why, and that a person confirms it with `okf verify`. If an `[OKF-Update]` pull request into the same
base is already open, its branch is replaced with the new commit and its text updated: there is
never a second one. The local checkout ends on the branch it started on.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from okf.fix import FixPlan, apply

TITLE = "[OKF-Update]"
MARK = "<!-- okf-update -->"
BOT = ("okf-ai", "okf-ai@users.noreply.github.com")


class PrError(RuntimeError):
    pass


@dataclass
class PullRequest:
    url: str
    branch: str
    updated: bool  # an open [OKF-Update] pull request was updated instead of opening a second one


def open_pr(plan: FixPlan, git_root: Path, now: datetime | None = None) -> PullRequest | None:
    """Commit the plan on its own branch, push it and open (or update) the pull request. None if nothing to fix."""
    drafts = [d for d in plan.drafts if not d.rejected]
    if not plan.edits and not drafts:
        return None
    if _git(git_root, "status", "--porcelain").strip():
        raise PrError("the working tree has uncommitted changes: commit or stash them first")
    start = _git(git_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = _git(git_root, "rev-parse", "HEAD").strip()
    base = start if start != "HEAD" else os.environ.get("GITHUB_REF_NAME", "")
    if not base:
        raise PrError("HEAD is detached: check out the branch the pull request should go into")
    sha = _git(git_root, "rev-parse", "--short", "HEAD").strip()
    existing = _open_update_pr(git_root, base)
    branch = existing["headRefName"] if existing else f"okf/update-{base}-{sha}"
    title, body = describe(plan, base, sha)
    _git(git_root, "switch", "-q", "-C", branch)
    try:
        try:
            apply(plan, git_root, now)
            _git(git_root, "add", "-A")
            _git(git_root, *_identity(git_root), "commit", "-q", "-m", f"{title}\n\n{_plain(body)}")
        except (OSError, PrError):
            _git(git_root, "reset", "-q", "--hard")  # the tree was clean: only okf's own writes are dropped
            raise
        _git(git_root, "push", "-q", "--force-with-lease", "origin", f"HEAD:refs/heads/{branch}")
        if existing:
            gh(git_root, "pr", "edit", str(existing["number"]), "--title", title, "--body", body)
            return PullRequest(existing["url"], branch, True)
        url = gh(git_root, "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body)
        return PullRequest(url.strip().splitlines()[-1] if url.strip() else "", branch, False)
    finally:
        _git(git_root, "checkout", "-q", start if start != "HEAD" else head)


def describe(plan: FixPlan, base: str, sha: str) -> tuple[str, str]:
    drafts = [d for d in plan.drafts if not d.rejected]
    units = list(dict.fromkeys([e.unit for e in plan.edits] + [d.unit for d in drafts]))
    title = f"{TITLE} {len(units)} {'section' if len(units) == 1 else 'sections'}: {', '.join(units)}"
    if len(title) > 120:
        title = title[:117] + "..."
    lines = [MARK, f"`okf fix` proposes these changes to agent instructions and knowledge on `{base}` at `{sha}`.",
             "", "**What changed and why**", ""]
    lines += [f"- `{e.unit}`: {e.reason} (mechanical, no AI)" for e in plan.edits]
    lines += [f"- `{d.unit}`: {d.summary} (draft by {d.by})" for d in drafts]
    if plan.manual:
        lines += ["", "**Needs a person** (not changed here)", ""]
        lines += [f"- `{m.unit}` (line {m.line}): {m.reason}" for m in plan.manual]
    quoted = " ".join(f'"{u}"' for u in units)
    lines += ["", "Generated, not verified: the trust map shows these sections as not verified until a person "
                  "reads them. Edit them in this pull request if needed, then confirm:", "",
              f"```bash\nokf verify {quoted}\n```"]
    return title, "\n".join(lines) + "\n"


def _open_update_pr(git_root: Path, base: str) -> dict | None:
    out = gh(git_root, "pr", "list", "--state", "open", "--base", base, "--json", "number,headRefName,url",
             "--limit", "100")
    try:
        found = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None
    prefix = f"okf/update-{base}-"
    return next((p for p in found if isinstance(p, dict) and str(p.get("headRefName", "")).startswith(prefix)), None)


def gh(cwd: Path, *args: str) -> str:
    """The GitHub CLI (tests replace this function)."""
    try:
        result = subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    except OSError as exc:
        raise PrError(f"cannot run gh (https://cli.github.com): {exc}") from None
    if result.returncode != 0:
        raise PrError(f"gh {args[0]} {args[1]} failed: {result.stderr.strip()}")
    return result.stdout


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        command = next(a for i, a in enumerate(args) if a != "-c" and (i == 0 or args[i - 1] != "-c"))
        raise PrError(f"git {command} failed: {result.stderr.strip()}")
    return result.stdout


def _identity(git_root: Path) -> list[str]:
    """okf-ai as the committer when git has no user (a fresh CI runner)."""
    configured = subprocess.run(["git", "config", "user.email"], cwd=git_root, capture_output=True, text=True)
    return [] if configured.stdout.strip() else ["-c", f"user.name={BOT[0]}", "-c", f"user.email={BOT[1]}"]


def _plain(body: str) -> str:
    return "\n".join(line for line in body.split("\n") if line != MARK and not line.startswith("```"))
