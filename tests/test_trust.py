"""`okf trust` and `okf verify`: units, sources, dates from git, the sidecar, levels."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import REPO_ROOT, doc, meta
from okf.bundle import load_document
from okf.cli import main
from okf.git import Change, History
from okf.report import display_path as display
from okf.schema import verifications
from okf.trust import (
    Sidecar, TrustError, build_map, default_actor, section_hash, sections, verify,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class Repo:
    """A throwaway git repository with commits at chosen dates."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args, when=None):
        env = {**os.environ, **({"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else {})}
        result = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                                cwd=self.root, check=True, capture_output=True, text=True, env=env)
        return result.stdout

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

    def map(self, changes=None, now=NOW):
        return build_map(self.root, History(self.root, now), changes, now=now)

    def levels(self, **kwargs):
        return {unit.name: unit.level for unit in self.map(**kwargs).units}

    def unit(self, name, **kwargs):
        return next(u for u in self.map(**kwargs).units if u.name == name)

    def verify(self, target, by="human:ivan", when="2026-09-05T10:00:00Z"):
        return verify(target, by, at(when), self.root, self.root)


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo")


AGENTS = """# AGENTS.md

Intro without code.

## Auth

Login lives in `src/auth.py`.

## Billing

Prices are in `src/billing.py`; run `npm run test`.
"""


def code_repo(repo):
    repo.write({"src/auth.py": "TTL = 30\n", "src/billing.py": "FEE = 50\n",
                "package.json": json.dumps({"scripts": {"test": "pytest"}})})
    return repo.commit("2026-06-01T10:00:00Z", "code")


# --- sections ---


def test_sections_split_by_level_two_headings():
    assert sections(AGENTS) == [(None, 1, 4), ("Auth", 5, 8), ("Billing", 9, 11)]


def test_sections_without_level_two_headings_are_one_unit():
    assert sections("# Title\n\nJust text.\n\n### Deep\n") == [(None, 1, 5)]


def test_sections_ignore_code_fences_skip_empty_intro_and_number_repeats():
    text = "# T\n\n## A\n```md\n## not a heading\n```\n## A\ntext\n"
    assert sections(text) == [("A", 3, 6), ("A (2)", 7, 8)]


def test_section_hash_ignores_trailing_whitespace():
    assert section_hash(["## A  ", "text\t", ""]) == section_hash(["## A", "text"])
    assert section_hash(["## A", "text"]) != section_hash(["## A", "other"])


# --- sources and levels ---


def test_sources_come_from_paths_commands_and_links(repo):
    code_repo(repo).write({
        "Makefile": "migrate:\n\techo\n",
        "AGENTS.md": "## Work\n\n`src/auth.py`, [billing](src/billing.py), `src/`, `src/**/*.py`, "
                     "`npm run test`, `make migrate`\n",
    }).commit("2026-09-01T10:00:00Z")
    unit = repo.unit("AGENTS.md#Work")
    assert sorted(Path(s).relative_to(repo.root.resolve()).as_posix() for s in unit.sources) == [
        "src/auth.py", "src/billing.py",  # not the directory, the glob, nor the manifests behind the commands
    ]
    assert {link["type"]: link["status"] for link in unit.links}["npm-script"] == "ok"  # still checked to exist


def test_manifest_changes_do_not_ask_for_a_recheck(repo):
    code_repo(repo).write({"AGENTS.md": "## Test\n\nRun `npm run test` and `./gradlew build`.\n", "gradlew": "#!/bin/sh\n"})
    repo.commit("2026-09-01T10:00:00Z")
    repo.write({"package.json": json.dumps({"scripts": {"test": "pytest -q"}, "dependencies": {"x": "2"}}),
                "gradlew": "#!/bin/sh\n# 8.10\n"}).commit("2026-10-20T10:00:00Z")
    assert repo.unit("AGENTS.md#Test").level == "unverified"


def test_directory_mentions_do_not_ask_for_rechecks(repo):
    code_repo(repo).write({"AGENTS.md": "## Layout\n\nCode is in `src/`.\n"}).commit("2026-09-01T10:00:00Z")
    repo.write({"src/auth.py": "TTL = 7\n"}).commit("2026-10-20T10:00:00Z")
    assert repo.unit("AGENTS.md#Layout").level == "unverified"
    assert repo.map(changes=[Change("M", "src/auth.py")]).units[0].in_change == []
    shutil.rmtree(repo.root / "src")
    assert repo.unit("AGENTS.md#Layout").level == "broken"


def test_never_verified_and_nothing_changed_is_unverified(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    assert repo.levels() == {"AGENTS.md": "unverified", "AGENTS.md#Auth": "unverified",
                             "AGENTS.md#Billing": "unverified"}
    assert repo.unit("AGENTS.md").message == "not verified; last edited 2026-09-01; no code references found"


def test_code_changed_after_an_unverified_section_was_written(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.write({"src/auth.py": "TTL = 7\n"}).commit("2026-10-20T10:00:00Z")
    unit = repo.unit("AGENTS.md#Auth")
    assert (unit.level, unit.message) == (
        "recheck", "src/auth.py changed 2026-10-20, section last edited 2026-09-01 and never verified")
    assert repo.unit("AGENTS.md#Billing").level == "unverified"


def test_verified_after_the_code_is_current(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.verify("AGENTS.md#Auth")
    unit = repo.unit("AGENTS.md#Auth")
    assert (unit.level, unit.message) == ("human-verified", "verified 2026-09-05 by human:ivan; sources unchanged since")


def test_code_changed_after_verification_needs_a_recheck(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.verify("AGENTS.md#Auth")
    repo.write({"src/auth.py": "TTL = 7\n"}).commit("2026-10-20T10:00:00Z")
    unit = repo.unit("AGENTS.md#Auth")
    assert (unit.level, unit.message) == (
        "recheck", "src/auth.py changed 2026-10-20, last verified 2026-09-05 by human:ivan")
    repo.verify("AGENTS.md#Auth", when="2026-10-21T09:00:00Z")
    assert repo.unit("AGENTS.md#Auth").level == "human-verified"


def test_process_confirmation_after_the_change(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.verify("AGENTS.md#Auth", by="human:ivan", when="2026-09-05T10:00:00Z")
    repo.write({"src/auth.py": "TTL = 7\n"}).commit("2026-10-20T10:00:00Z")
    repo.verify("AGENTS.md#Auth", by="process:ci", when="2026-10-21T10:00:00Z")
    unit = repo.unit("AGENTS.md#Auth")
    assert (unit.level, unit.message) == ("process-verified", "verified 2026-10-21 by process:ci; sources unchanged since")


def test_section_edited_after_verification(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.verify("AGENTS.md#Auth")
    repo.write({"AGENTS.md": AGENTS.replace("Login lives", "Login now lives")})
    unit = repo.unit("AGENTS.md#Auth")
    assert (unit.level, unit.message) == ("recheck", "section edited after it was verified; last verified 2026-09-05 by human:ivan")
    assert repo.unit("AGENTS.md#Billing").level == "unverified"  # other sections are not affected


def test_broken_reference(repo):
    code_repo(repo).write({"AGENTS.md": "## Seed\n\nRun `./scripts/seed_db.sh` and `npm run nope`.\n"})
    repo.commit("2026-09-01T10:00:00Z")
    unit = repo.unit("AGENTS.md#Seed")
    assert (unit.level, unit.message) == ("broken", '"./scripts/seed_db.sh" does not exist (and 1 more)')


def test_uncommitted_edits_are_dated_by_file_time(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.write({"src/auth.py": "TTL = 7\n"})  # not committed, modified now
    assert repo.unit("AGENTS.md#Auth", now=datetime.now(timezone.utc)).level == "recheck"
    repo.verify("AGENTS.md#Auth", when=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert repo.unit("AGENTS.md#Auth", now=datetime.now(timezone.utc)).level == "human-verified"


def test_changes_since_base_mark_what_a_pull_request_touches(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.verify("AGENTS.md#Billing")
    repo.commit("2026-09-05T11:00:00Z")
    trust_map = repo.map(changes=[Change("M", "src/billing.py")])
    touched = [(u.name, u.level, u.message) for u in trust_map.units if u.in_change]
    assert touched == [("AGENTS.md#Billing", "recheck",
                        "src/billing.py changed in this change; last verified 2026-09-05 by human:ivan")]
    assert trust_map.summary().endswith("; 1 to recheck because of this change")


def test_glob_scopes_are_not_sources(repo):
    code_repo(repo).write({".cursor/rules/a.mdc": "---\nglobs: src/**/*.py\n---\nUse `src/billing.py`.\n"})
    repo.commit("2026-09-01T10:00:00Z")
    repo.write({"src/auth.py": "TTL = 7\n"}).commit("2026-10-20T10:00:00Z")
    assert repo.unit(".cursor/rules/a.mdc").level == "unverified"


def test_generated_router_is_not_a_unit(repo):
    code_repo(repo).write({"kb/AGENTS.md": "# AGENTS.md\n\n<!-- Generated by `okf agents` -->\n"})
    repo.commit("2026-09-01T10:00:00Z")
    assert repo.levels() == {}


# --- OKF knowledge units ---


def okf_doc(sources, **changes):
    return doc(meta(sources=[{"resource": r} for r in sources], **changes))


def test_knowledge_documents_are_units(repo):
    code_repo(repo).write({
        "kb/index.md": "# KB\n",
        "kb/auth.md": okf_doc(["../src/auth.py", "https://wiki.example/auth", "all queries in project X"]),
        "kb/gone.md": okf_doc(["../src/gone.py"]),
        "kb/regenerated.md": okf_doc([], **{"generated.at": "2026-11-01T00:00:00Z"}),
        "kb/expired.md": okf_doc([], stale_after="2026-10-01T00:00:00Z",
                                 verified=[{"by": "human:a", "at": "2026-10-19T11:00:00Z"}]),
        "notes/plain.md": "# no front matter\n",
    }).commit("2026-09-01T10:00:00Z")
    repo.write({"src/auth.py": "TTL = 7\n"}).commit("2026-10-20T10:00:00Z")
    units = {u.name: (u.level, u.message) for u in repo.map().units}
    assert units == {
        "kb/auth.md": ("recheck", "src/auth.py changed 2026-10-20, last verified 2026-10-19 by human:teamlead_ivan"),
        "kb/expired.md": ("recheck", "stale_after 2026-10-01 has passed; last verified 2026-10-19 by human:a"),
        "kb/gone.md": ("broken", 'source "../src/gone.py" does not exist'),
        "kb/regenerated.md": ("recheck", "content regenerated 2026-11-01 after it was verified; "
                                         "last verified 2026-10-19 by human:teamlead_ivan"),
    }


def test_verify_appends_to_okf_front_matter(repo):
    original = okf_doc(["../src/auth.py"])
    code_repo(repo).write({"kb/auth.md": original}).commit("2026-09-01T10:00:00Z")
    assert repo.verify("kb/auth.md", when="2026-10-21T09:00:00Z") == ["kb/auth.md"]
    document = load_document(repo.root / "kb/auth.md", repo.root / "kb")
    assert [(e["by"], e["at"]) for e in verifications(document)] == [
        ("human:teamlead_ivan", "2026-10-19T10:00:00Z"), ("human:ivan", "2026-10-21T09:00:00Z")]
    before = original.split("\n")
    after = (repo.root / "kb/auth.md").read_text(encoding="utf-8").split("\n")
    assert [line for line in after if line not in before] == [  # the block is rewritten in the OKF style
        "  - { by: human:teamlead_ivan, at: 2026-10-19T10:00:00Z }",
        "  - { by: human:ivan, at: 2026-10-21T09:00:00Z }",
    ]
    assert after[: after.index("verified:")] == before[: before.index("verified:")]  # the rest is untouched
    assert after[after.index("stale_after: '2027-10-19T00:00:00Z'"):] == before[before.index("stale_after: '2027-10-19T00:00:00Z'"):]


@pytest.mark.parametrize("verified", [
    "",
    "verified: { by: human:a, at: 2026-01-01T00:00:00Z }\n",
    "verified:\n  - { by: human:a, at: 2026-01-01T00:00:00Z }\n  - by: process:ci\n    at: 2026-02-01T00:00:00Z\n",
])
def test_verify_handles_every_shape_of_verified(repo, verified):
    text = f"---\ntype: Guide\n{verified}stale_after: 2027-01-01T00:00:00Z\n---\n# Guide\n"
    repo.write({"guide.md": text})
    repo.verify("guide.md", when="2026-10-21T09:00:00Z")
    document = load_document(repo.root / "guide.md", repo.root)
    assert len(verifications(document)) == verified.count("by:") + 1
    assert document.meta["stale_after"] == "2027-01-01T00:00:00Z"
    assert document.body == "# Guide\n"


# --- the sidecar and okf verify ---


def test_verify_writes_the_sidecar(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    assert repo.verify("AGENTS.md#auth") == ["AGENTS.md#Auth"]  # case-insensitive match
    repo.verify("AGENTS.md#Auth", by="process:ci", when="2026-09-06T10:00:00Z")
    record = Sidecar(repo.root / ".okf/trust.yml").record("AGENTS.md#Auth")
    assert record["sources"] == ["src/auth.py"]
    assert record["hash"] == section_hash(AGENTS.split("\n")[4:8])
    assert record["verified"] == [{"by": "human:ivan", "at": "2026-09-05T10:00:00Z"},
                                  {"by": "process:ci", "at": "2026-09-06T10:00:00Z"}]
    assert (repo.root / "AGENTS.md").read_text(encoding="utf-8") == AGENTS  # instructions are not touched


def test_verify_whole_file_or_only_the_intro(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    assert repo.verify("AGENTS.md") == ["AGENTS.md", "AGENTS.md#Auth", "AGENTS.md#Billing"]
    assert repo.verify("AGENTS.md#") == ["AGENTS.md"]


def test_nested_sidecar_keys_are_relative_to_it(repo):
    code_repo(repo).write({"svc/AGENTS.md": AGENTS, "svc/.okf/trust.yml": "units: []\n"}).commit("2026-09-01T10:00:00Z")
    repo.verify("svc/AGENTS.md#Auth")
    assert Sidecar(repo.root / "svc/.okf/trust.yml").record("AGENTS.md#Auth") is not None
    assert not (repo.root / ".okf").exists()
    assert repo.unit("svc/AGENTS.md#Auth").level == "human-verified"


def test_verify_errors(repo):
    code_repo(repo).write({"AGENTS.md": AGENTS, "notes.md": "# plain\n"}).commit("2026-09-01T10:00:00Z")
    with pytest.raises(TrustError, match='no section "Nope"'):
        repo.verify("AGENTS.md#Nope")
    with pytest.raises(TrustError, match="is not an actor"):
        repo.verify("AGENTS.md#Auth", by="ivan")
    with pytest.raises(TrustError, match="file not found"):
        repo.verify("MISSING.md")
    with pytest.raises(TrustError, match="neither an agent instruction file nor an OKF document"):
        repo.verify("notes.md")


def test_default_actor_from_git_config(repo):
    repo.git("config", "user.email", "emil@example.com")
    assert default_actor(repo.root) == "human:emil@example.com"


# --- command line ---


def run(capsys, *argv):
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out.splitlines(), err


def test_cli_trust_text_json_strict_and_github(repo, capsys):
    code_repo(repo).write({"AGENTS.md": AGENTS + "\n## Seed\n\n`./scripts/seed.sh`\n"}).commit("2026-09-01T10:00:00Z")
    code, out, err = run(capsys, "trust", str(repo.root), "--now", "2026-10-22")
    assert code == 0
    assert err.startswith("okf trust: 4 units: 0 verified and current, 0 to recheck, 1 broken, 3 not verified")
    assert out[0].startswith("[ERROR] ") and out[0].endswith('AGENTS.md#Seed: trust: "./scripts/seed.sh" does not exist')
    assert [line.split("] ")[0] for line in out] == ["[ERROR", "[INFO", "[INFO", "[INFO"]
    assert run(capsys, "trust", str(repo.root), "--strict")[0] == 1
    _, out, _ = run(capsys, "trust", str(repo.root), "--format", "github")
    assert len(out) == 1 and out[0].startswith("::error ")
    _, out, _ = run(capsys, "trust", str(repo.root), "--json")
    data = json.loads("\n".join(out))
    assert data["summary"] == {"units": 4, "verified": 0, "recheck": 0, "broken": 1, "unverified": 3, "in_change": None,
                               "history": "full"}
    assert data["units"][0]["unit"] == "AGENTS.md#Seed" and data["units"][0]["level"] == "broken"


def test_cli_verify(repo, capsys, monkeypatch):
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    monkeypatch.chdir(repo.root)
    code, _, err = run(capsys, "verify", "AGENTS.md#Auth", "--by", "human:ivan", "--at", "2026-09-05T10:00:00Z")
    assert code == 0 and "AGENTS.md#Auth verified by human:ivan at 2026-09-05T10:00:00Z" in err
    code, _, err = run(capsys, "verify", "--all-current", "--by", "human:ivan")
    assert code == 0 and err.count("verified by") == 2  # the intro and Billing; Auth was verified already
    assert run(capsys, "verify")[0] == 2


def test_cli_trust_since_strict_fails_on_what_the_change_broke(repo, capsys):
    code_repo(repo).write({"AGENTS.md": AGENTS + "\n## Old\n\nSee `src/gone.py`.\n"}).commit("2026-09-01T10:00:00Z")
    repo.git("checkout", "-q", "-b", "pr")
    repo.write({"README.txt": "x\n"}).commit("2026-10-01T10:00:00Z")
    code, out, _ = run(capsys, "trust", str(repo.root), "--since", "main", "--strict")
    assert (code, out) == (0, [])  # AGENTS.md#Old was broken before this change: not this change's problem
    repo.write({"AGENTS.md": AGENTS.replace("`src/auth.py`", "`src/auth.py` and `src/nope.py`")
                + "\n## Old\n\nSee `src/gone.py`.\n"}).commit("2026-10-02T10:00:00Z")
    code, out, _ = run(capsys, "trust", str(repo.root), "--since", "main", "--strict")
    assert code == 1
    assert [line.split(": trust: ")[0] for line in out] == [f"[ERROR] {display(repo.root / 'AGENTS.md')}#Auth"]


def test_cli_trust_since_needs_git(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("`src/a.py`\n", encoding="utf-8")
    code, _, err = run(capsys, "trust", str(tmp_path), "--since", "main")
    assert code == 2 and "needs a git repository" in err


# --- the demo history ---


def test_demo_history_tells_the_story(tmp_path):
    target = tmp_path / "wheelo"
    script = REPO_ROOT / "examples" / "make_demo_history.py"
    subprocess.run([sys.executable, str(script), str(target)], check=True, capture_output=True)
    history = History(target, NOW)
    levels = {u.name: u.level for u in build_map(target, history, now=NOW).units}
    assert levels["AGENTS.md#Команды"] == "recheck"  # seed_db.sh moved to seed.sh: edge case 8
    assert levels["AGENTS.md#Auth"] == "recheck"
    assert levels["AGENTS.md#Billing"] == "human-verified"
    assert levels["knowledge/auth_flow.md"] == "recheck"
    assert levels["CLAUDE.md"] == "broken"
    assert sorted(levels.values()).count("human-verified") == 9

    subprocess.run(["git", "switch", "-q", "pr/billing-tariff"], cwd=target, check=True)
    from okf.git import changes_since

    trust_map = build_map(target, History(target, NOW), changes_since(target, "main"), now=NOW)
    assert sorted(u.name for u in trust_map.units if u.in_change) == [
        ".cursor/rules/backend.mdc", "AGENTS.md#Billing", "knowledge/billing_service.md",
        "knowledge/payment_failures_runbook.md",
    ]
