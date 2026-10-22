"""Edge cases 1–8 of the PRD (Skills-Results/okf-ai/product-requirements): one group of tests each."""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT
from okf.cli import main
from okf.git import History, changes_since, merge_base
from okf.instructions import check_repository, discover, is_placeholder
from okf.trust import build_map

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
CODE = {"src/auth.py": "TTL = 30\n", "src/billing.py": "FEE = 50\n",
        "package.json": json.dumps({"scripts": {"test": "pytest"}})}


class Repo:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args, when=None):
        env = {**os.environ, **({"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else {})}
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=self.root,
                              check=True, capture_output=True, text=True, env=env).stdout

    def write(self, files):
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return self

    def commit(self, when, message="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, when=when)
        return self

    def units(self, **kwargs):
        trust_map = build_map(self.root, History(self.root, NOW), now=NOW, **kwargs)
        return {u.name: u for u in trust_map.units}

    def check(self):
        report = check_repository(self.root, False, None, self.root)
        return [(i.level, i.path.relative_to(self.root.resolve()).as_posix(), i.field, i.message)
                for i in report.issues]


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo")


def links(unit):
    return {link["source"]: link["status"] for link in unit.links}


# --- 1. Placeholders and example paths are "unclear", not broken ---


@pytest.mark.parametrize("path", ["path/to/file.ts", "src/foo.py", "your-project/src/app.ts", "lib/bar/baz.js",
                                  "example/config.yml", "src/.../x.py"])
def test_placeholder_paths(path):
    assert is_placeholder(path)


@pytest.mark.parametrize("path", ["src/auth.py", "examples/demo/AGENTS.md", "food/menu.md", "src/barrel.ts"])
def test_real_paths_are_not_placeholders(path):
    assert not is_placeholder(path)


def test_placeholders_are_not_broken(repo):
    repo.write({**CODE, "AGENTS.md": "## Layout\n\nPut files like `path/to/file.ts` or `src/foo.py` next to "
                                     "`src/auth.py`; never `src/gone.py`.\n"}).commit("2026-09-01T10:00:00Z")
    unit = repo.units()["AGENTS.md#Layout"]
    assert links(unit) == {"path/to/file.ts": "unclear", "src/foo.py": "unclear", "src/auth.py": "ok",
                           "src/gone.py": "broken"}
    assert unit.broken == ['"src/gone.py" does not exist']
    issues = repo.check()
    assert [(level, message.split(" (line")[0]) for level, _, _, message in issues] == [
        ("INFO", '"path/to/file.ts" looks like a placeholder, not checked'),
        ("INFO", '"src/foo.py" looks like a placeholder, not checked'),
        ("WARNING", '"src/gone.py" does not exist'),
    ]


def test_an_existing_placeholder_like_path_is_just_ok(repo):
    repo.write({**CODE, "examples/foo.py": "", "AGENTS.md": "## X\n\n`examples/foo.py`\n"}).commit("2026-09-01T10:00:00Z")
    assert links(repo.units()["AGENTS.md#X"]) == {"examples/foo.py": "ok"}


# --- 2. Paths ignored by git (build outputs) are "unknown", not broken ---


def test_gitignored_and_build_paths_are_unknown(repo):
    repo.write({**CODE, ".gitignore": "/generated/\n*.log\n", "web/.gitignore": "out-web/\n",
                "AGENTS.md": "## Build\n\nOutputs: `dist/app.js`, `.env`, `node_modules/x/index.js`, `generated/api.ts`, "
                             "`web/out-web/index.html`, `debug.log`; missing `src/real.ts`.\n"})
    repo.commit("2026-09-01T10:00:00Z")
    unit = repo.units()["AGENTS.md#Build"]
    statuses = links(unit)
    assert statuses.pop("src/real.ts") == "broken"
    assert set(statuses.values()) == {"unknown"}, statuses
    assert len(unit.broken) == 1
    assert sum(level == "WARNING" for level, *_ in repo.check()) == 1


# --- 3. Shallow history: no false dates, an explicit warning, fetch-depth: 0 in the workflow ---


def test_shallow_clone_has_no_dates_and_warns(repo, tmp_path, capsys):
    repo.write({**CODE, "AGENTS.md": "## Auth\n\n`src/auth.py`\n"}).commit("2026-06-01T10:00:00Z")
    repo.write({"src/auth.py": "TTL = 7\n"}).commit("2026-10-20T10:00:00Z")
    assert repo.units()["AGENTS.md#Auth"].level == "recheck"  # full history: the code changed after the section

    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{repo.root.as_posix()}", str(shallow)],
                   check=True, capture_output=True)
    history = History(shallow, NOW)
    assert history.shallow and history.last_change(shallow / "src/auth.py") is None
    trust_map = build_map(shallow, history, now=NOW)
    assert trust_map.shallow
    assert {u.name: u.level for u in trust_map.units} == {"AGENTS.md#Auth": "unverified"}

    assert main(["trust", str(shallow)]) == 0
    err = capsys.readouterr().err
    assert "shallow" in err and "fetch-depth: 0" in err


def test_shallow_base_error_suggests_fetch_depth(repo, tmp_path):
    repo.write(CODE).commit("2026-06-01T10:00:00Z")
    repo.git("checkout", "-q", "-b", "feature")
    repo.write({"src/auth.py": "TTL = 7\n"}).commit("2026-10-20T10:00:00Z")
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--no-single-branch", f"file://{repo.root.as_posix()}",
                    str(shallow)], check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-q", "feature"], cwd=shallow, check=True, capture_output=True)
    with pytest.raises(Exception, match="fetch-depth: 0"):
        merge_base(shallow, "origin/main")


def test_workflow_fetches_the_whole_history():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/okf.yml").read_text(encoding="utf-8"))
    checkout = next(s for s in workflow["jobs"]["knowledge"]["steps"] if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0


# --- 4. A pull request that changes the code and the section describing it ---


AGENTS = "# AGENTS.md\n\n## Auth\n\nLogin: `src/auth.py`.\n\n## Billing\n\nPrices: `src/billing.py`.\n"


def test_section_updated_with_its_code_is_not_flagged(repo):
    repo.write({**CODE, "AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.git("checkout", "-q", "-b", "pr")
    repo.write({"src/auth.py": "TTL = 7\n", "src/billing.py": "FEE = 60\n",
                "AGENTS.md": AGENTS.replace("Login: `src/auth.py`.", "Login (7-day tokens): `src/auth.py`.")})
    repo.commit("2026-10-20T10:00:00Z")
    base = merge_base(repo.root, "main")
    trust_map = build_map(repo.root, History(repo.root, NOW), changes_since(repo.root, "main"), now=NOW,
                          base_commit=base)
    units = {u.name: u for u in trust_map.units}
    assert units["AGENTS.md#Auth"].updated_in_change and units["AGENTS.md#Auth"].level != "recheck"
    assert not units["AGENTS.md#Billing"].updated_in_change and units["AGENTS.md#Billing"].level == "recheck"
    assert [u.name for u in trust_map.in_change()] == ["AGENTS.md#Billing"]


def test_cli_shows_the_updated_section_as_info(repo, capsys, monkeypatch):
    repo.write({**CODE, "AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.git("checkout", "-q", "-b", "pr")
    repo.write({"src/auth.py": "TTL = 7\n", "AGENTS.md": AGENTS.replace("Login:", "Login now:")})
    repo.commit("2026-10-20T10:00:00Z")
    assert main(["trust", str(repo.root), "--since", "main", "--strict"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1 and out[0].startswith("[INFO] ")
    assert out[0].endswith("AGENTS.md#Auth: trust: src/auth.py and this section changed together in this change")


# --- 5. Nested instructions in a monorepo ---


def test_nested_paths_resolve_from_the_instruction_folder_then_the_root(repo):
    repo.write({
        "packages/api/AGENTS.md": "## API\n\n`src/server.ts`, `scripts/release.sh`, `src/gone.ts`\n",
        "packages/api/src/server.ts": "", "scripts/release.sh": "", "src/server.ts": "",
    }).commit("2026-09-01T10:00:00Z")
    unit = repo.units()["packages/api/AGENTS.md#API"]
    assert links(unit) == {"packages/api/src/server.ts": "ok", "scripts/release.sh": "ok:root",
                           "src/gone.ts": "broken"}


# --- 6. CLAUDE.md as a symlink, a one-line pointer or an @AGENTS.md import ---


def test_claude_md_pointing_to_agents_md_is_checked_once(repo):
    repo.write({**CODE, "AGENTS.md": AGENTS, "CLAUDE.md": "AGENTS.md"}).commit("2026-09-01T10:00:00Z")
    files = {f.path.name: f for f in discover(repo.root)}
    assert files["CLAUDE.md"].alias_of == (repo.root / "AGENTS.md").resolve()
    assert sorted(repo.units()) == ["AGENTS.md#Auth", "AGENTS.md#Billing"]
    assert repo.check() == [("INFO", "CLAUDE.md", "file", "Link to AGENTS.md; its sections are checked there")]


def test_claude_md_symlink(repo):
    repo.write({**CODE, "AGENTS.md": AGENTS})
    try:
        os.symlink("AGENTS.md", repo.root / "CLAUDE.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available here")
    assert sorted(repo.units()) == ["AGENTS.md#Auth", "AGENTS.md#Billing"]


def test_claude_md_importing_agents_md(repo):
    repo.write({**CODE, "AGENTS.md": "## Test\n\nRun `npm test`.\n",
                "CLAUDE.md": "@AGENTS.md\n\n## Claude\n\nAlso `npm run lint`.\n",
                "package.json": json.dumps({"scripts": {"test": "x", "lint": "y"}})}).commit("2026-09-01T10:00:00Z")
    repo.write({"AGENTS.md": "## Test\n\nRun `npm test` with coverage.\n"}).commit("2026-10-01T10:00:00Z")
    units = repo.units()
    assert sorted(units) == ["AGENTS.md#Test", "CLAUDE.md", "CLAUDE.md#Claude"]
    assert units["CLAUDE.md"].sources == [] and units["CLAUDE.md"].level == "unverified"  # the import is not code
    assert [i for i in repo.check() if i[2] == "consistency"] == []


# --- 7. Rules generated by Ruler or rulesync ---


def test_ruler_copies_point_to_their_source(repo):
    repo.write({
        **CODE,
        ".ruler/instructions.md": "## Auth\n\nLogin: `src/auth.py`; missing `src/gone.py`.\n",
        "AGENTS.md": "<!-- Source: .ruler/instructions.md -->\n\n## Auth\n\nLogin: `src/auth.py`; missing `src/gone.py`.\n",
        ".gitignore": "# START Ruler Generated Files\n/CLAUDE.md\n# END Ruler Generated Files\n",
        "CLAUDE.md": "## Auth\n\nLogin: `src/auth.py`; missing `src/gone.py`.\n",
        ".cursor/rules/sync.mdc": "<!-- Generated by rulesync. Do not edit. -->\n`src/gone.py`\n",
    }).commit("2026-09-01T10:00:00Z")
    files = {f.path.relative_to(repo.root).as_posix(): f.generated_from for f in discover(repo.root)}
    assert files == {".ruler/instructions.md": None, "AGENTS.md": ".ruler/ (Ruler)", "CLAUDE.md": ".ruler/ (Ruler)",
                     ".cursor/rules/sync.mdc": ".rulesync/ (rulesync)"}
    trust_map = build_map(repo.root, History(repo.root, NOW), now=NOW)
    assert [u.name for u in trust_map.units] == [".ruler/instructions.md#Auth"]  # flagged once, in the source
    assert trust_map.units[0].level == "broken"
    assert sorted(note for _, note in trust_map.notes) == [
        "Generated from .ruler/ (Ruler); its sections are checked there",
        "Generated from .ruler/ (Ruler); its sections are checked there",
        "Generated from .rulesync/ (rulesync); its sections are checked there",
    ]
    assert [(level, path) for level, path, field, _ in repo.check() if level == "WARNING"] == [
        ("WARNING", ".ruler/instructions.md")]


# --- 8. A file that moved: "recheck, moved to", not "broken" ---


def test_moved_file_is_a_recheck_with_the_new_path(repo):
    repo.write({**CODE, "src/config.py": "DEBUG = False\nPORT = 8000\n",
                "AGENTS.md": "## Config\n\nSettings: `src/config.py`.\n"}).commit("2026-09-01T10:00:00Z")
    repo.git("mv", "src/config.py", "src/settings.py")
    repo.commit("2026-09-20T10:00:00Z", "rename")
    (repo.root / "src/conf").mkdir()
    repo.git("mv", "src/settings.py", "src/conf/settings.py")
    repo.commit("2026-10-01T10:00:00Z", "move")
    unit = repo.units()["AGENTS.md#Config"]
    assert (unit.level, unit.message) == ("recheck", "src/config.py moved to src/conf/settings.py on 2026-10-01; "
                                                     "never verified")
    assert links(unit) == {"src/config.py": "moved"}
    [(level, _, field, message)] = repo.check()
    assert (level, field, message) == ("WARNING", "path",
                                       '"src/config.py" was moved to src/conf/settings.py on 2026-10-01 (line 3)')


def test_follow_keeps_history_across_a_rename(repo):
    repo.write({"src/config.py": "DEBUG = False\nPORT = 8000\n"}).commit("2026-06-01T10:00:00Z")
    repo.git("mv", "src/config.py", "src/settings.py")
    repo.commit("2026-09-20T10:00:00Z", "rename")
    assert History(repo.root, NOW).last_change(repo.root / "src/settings.py").date().isoformat() == "2026-09-20"
