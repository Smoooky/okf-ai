"""Build a demo git repository with history for `okf trust`.

    python examples/make_demo_history.py /tmp/wheelo-demo

Copies examples/demo into a new repository and replays a story with fixed dates:

- 2026-06-01  first version of the code and the OKF knowledge (seed script: scripts/seed_db.sh)
- 2026-08-20  the seed script is renamed to scripts/seed.sh
- 2026-09-01  AGENTS.md, CLAUDE.md and a Cursor rule are written, still naming seed_db.sh
- 2026-09-05  the team lead verifies AGENTS.md#Auth, the backend lead AGENTS.md#Billing
- 2026-10-20  src/auth.py changes (lockouts are now logged): Auth needs a recheck
- (fixtures, not committed) 2026-10-14  Jira epic WHL-42 behind the conversion metric is closed
- branch pr/billing-tariff, 2026-10-22: the per-minute price goes up in src/billing.py

Then `okf trust` in that repository shows the map, and `okf trust --since main` on the
branch shows what the pull request makes to recheck. The script needs only git.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from okf.trust import verify  # noqa: E402

DEMO = HERE / "demo"
INSTRUCTIONS = ("AGENTS.md", "CLAUDE.md", ".cursor")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("target", help="directory for the new repository (must not exist or be empty)")
    target = Path(parser.parse_args(argv).target).resolve()
    if target.exists() and any(target.iterdir()):
        print(f"make_demo_history: {target} is not empty", file=sys.stderr)
        return 2
    build(target)
    print(f"Demo repository with history: {target}")
    print(f"  cd {target}")
    print("  okf trust                                   # the trust map")
    print("  git switch pr/billing-tariff && okf trust --since main && git switch main")
    print("  okf fix                                     # mechanical fixes as a diff")
    print("  okf fix --draft --only AGENTS.md#Auth --replay .okf/auth_draft.example.json   # a saved example answer")
    print("  OKF_SOURCES_FIXTURES=.okf/atlassian-fixtures OKF_CONFLUENCE_URL=https://wheelo.atlassian.net/wiki \\")
    print("    OKF_JIRA_URL=https://wheelo.atlassian.net okf trust   # Confluence and Jira from hand-written fixtures")
    return 0


def build(target: Path) -> None:
    shutil.copytree(DEMO, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".okf", "__pycache__"))
    for name in INSTRUCTIONS:
        _remove(target / name)
    (target / "scripts" / "seed.sh").rename(target / "scripts" / "seed_db.sh")
    makefile = target / "Makefile"
    makefile.write_text(makefile.read_text(encoding="utf-8").replace("seed.sh", "seed_db.sh"), encoding="utf-8")

    git = _Git(target)
    git("init", "-q", "-b", "main")
    git.commit("2026-06-01T10:00:00Z", "Wheelo: first version", "human:teamlead_ivan")

    git("mv", "scripts/seed_db.sh", "scripts/seed.sh")
    shutil.copy(DEMO / "Makefile", makefile)
    git.commit("2026-08-20T12:00:00Z", "Rename the seed script", "human:data_oleg")

    for name in INSTRUCTIONS:
        source = DEMO / name
        if source.is_dir():
            shutil.copytree(source, target / name)
        else:
            shutil.copy(source, target / name)
    git.commit("2026-09-01T09:00:00Z", "Instructions for AI agents", "human:teamlead_ivan")

    verify("AGENTS.md#Auth", "human:teamlead_ivan", _at("2026-09-05T10:00:00Z"), target, target)
    verify("AGENTS.md#Billing", "human:maria_backend", _at("2026-09-05T11:30:00Z"), target, target)
    git.commit("2026-09-05T12:00:00Z", "Review of agent instructions", "human:teamlead_ivan")

    auth = target / "src" / "auth.py"
    text = auth.read_text(encoding="utf-8")
    text = text.replace("import secrets\n", "import logging\nimport secrets\n", 1)
    text = text.replace('_attempts: dict[str, list[float]] = {}\n',
                        '_attempts: dict[str, list[float]] = {}\nlog = logging.getLogger("wheelo.auth")\n', 1)
    text = text.replace('    if is_locked(phone):\n',
                        '    if is_locked(phone):\n        log.warning("login locked for %s", phone)\n', 1)
    auth.write_text(text, encoding="utf-8")
    git.commit("2026-10-20T15:00:00Z", "Log locked logins", "human:maria_backend")

    git("checkout", "-q", "-b", "pr/billing-tariff")
    billing = target / "src" / "billing.py"
    billing.write_text(billing.read_text(encoding="utf-8").replace("PER_MINUTE_RUB = 8", "PER_MINUTE_RUB = 9"),
                       encoding="utf-8")
    git.commit("2026-10-22T09:00:00Z", "Raise the per-minute price to 9 RUB", "human:maria_backend")
    git("checkout", "-q", "main")
    # A hand-written example of a model answer for `okf fix --draft --replay` (not committed).
    shutil.copy(HERE / "demo-pr" / "auth_draft.example.json", target / ".okf" / "auth_draft.example.json")
    # Hand-written answers in the shape of Confluence and Jira REST, for OKF_SOURCES_FIXTURES (not committed).
    shutil.copytree(HERE / "atlassian-fixtures", target / ".okf" / "atlassian-fixtures")


class _Git:
    def __init__(self, root: Path):
        self.root = root

    def __call__(self, *args: str, env: dict | None = None) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, env=env)

    def commit(self, when: str, message: str, author: str) -> None:
        name = author.split(":", 1)[1]
        env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        self("add", "-A")
        self("-c", f"user.name={name}", "-c", f"user.email={name}@wheelo.example", "commit", "-q", "-m", message,
             env=env)


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


if __name__ == "__main__":
    sys.exit(main())
