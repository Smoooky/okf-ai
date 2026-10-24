"""`okf fix --pr` on a throwaway repository with a local bare remote and a mocked `gh`."""

import json
import shutil
import subprocess

import pytest

from conftest import NOW
from okf import pr as pr_module
from okf.cli import main
from okf.pr import PrError, describe, open_pr
from test_fix import FakeModel, drifted_repo, moved_repo

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


class FakeGh:
    """Records gh calls; `open_prs` is what `gh pr list` answers."""

    def __init__(self, open_prs=None):
        self.calls, self.open_prs = [], open_prs or []

    def __call__(self, cwd, *args):
        self.calls.append(args)
        if args[:2] == ("pr", "list"):
            return json.dumps(self.open_prs)
        if args[:2] == ("pr", "create"):
            return "https://github.com/acme/wheelo/pull/7\n"
        return ""


@pytest.fixture
def origin(repo, tmp_path):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    moved_repo(repo)
    repo.git("remote", "add", "origin", str(bare))
    repo.git("push", "-q", "origin", "main")
    return bare


def remote_file(bare, ref, path):
    return subprocess.run(["git", "--git-dir", str(bare), "show", f"{ref}:{path}"], capture_output=True, text=True,
                          encoding="utf-8").stdout


def test_pr_with_the_mechanical_fix(repo, origin, monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(pr_module, "gh", gh)
    sha = repo.git("rev-parse", "--short", "HEAD").strip()
    pull = open_pr(repo.plan(), repo.root, NOW)
    assert (pull.url, pull.branch, pull.updated) == ("https://github.com/acme/wheelo/pull/7",
                                                     f"okf/update-main-{sha}", False)
    assert repo.git("rev-parse", "--abbrev-ref", "HEAD").strip() == "main"  # back where it started
    assert "./scripts/seed_db.sh" in repo.read("AGENTS.md")  # main itself is untouched
    assert "./scripts/seed.sh" in remote_file(origin, pull.branch, "AGENTS.md")
    assert "process:okf-fix" in remote_file(origin, pull.branch, ".okf/trust.yml")
    create = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    title, body = create[create.index("--title") + 1], create[create.index("--body") + 1]
    assert create[create.index("--base") + 1] == "main" and title == "[OKF-Update] 1 section: AGENTS.md#Commands"
    assert "./scripts/seed_db.sh moved to ./scripts/seed.sh (mechanical, no AI)" in body
    assert 'okf verify "AGENTS.md#Commands"' in body and "not verified" in body
    message = subprocess.run(["git", "--git-dir", str(origin), "log", "-1", "--format=%B", pull.branch],
                             capture_output=True, text=True).stdout
    assert message.startswith("[OKF-Update] 1 section: AGENTS.md#Commands")


def test_an_open_okf_update_pr_is_updated_not_duplicated(repo, origin, monkeypatch):
    gh = FakeGh([{"number": 3, "headRefName": "okf/update-main-0000000", "url": "https://github.com/acme/wheelo/pull/3"},
                 {"number": 4, "headRefName": "feature/x", "url": "u"}])
    monkeypatch.setattr(pr_module, "gh", gh)
    pull = open_pr(repo.plan(), repo.root, NOW)
    assert (pull.url, pull.branch, pull.updated) == ("https://github.com/acme/wheelo/pull/3",
                                                     "okf/update-main-0000000", True)
    assert not any(c[:2] == ("pr", "create") for c in gh.calls)
    edit = next(c for c in gh.calls if c[:2] == ("pr", "edit"))
    assert edit[2] == "3" and "--body" in edit
    assert "./scripts/seed.sh" in remote_file(origin, "okf/update-main-0000000", "AGENTS.md")


def test_nothing_to_fix_opens_nothing(repo, origin, monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(pr_module, "gh", gh)
    repo.write({"AGENTS.md": repo.read("AGENTS.md").replace("seed_db.sh", "seed.sh")}).commit("2026-08-21T10:00:00Z")
    assert open_pr(repo.plan(), repo.root, NOW) is None and gh.calls == []


def test_a_dirty_tree_is_refused(repo, origin, monkeypatch):
    monkeypatch.setattr(pr_module, "gh", FakeGh())
    (repo.root / "notes.txt").write_text("mine\n", encoding="utf-8")
    with pytest.raises(PrError, match="uncommitted changes"):
        open_pr(repo.plan(), repo.root, NOW)
    assert (repo.root / "notes.txt").exists()


def test_drafts_are_in_the_pr_and_named_by_their_model(repo, monkeypatch):
    drifted_repo(repo)
    model = FakeModel({"section": "## Auth\n\nLogin: `src/auth.py`, 7-day tokens.\n", "summary": "tokens live 7 days",
                       "changed": True})
    title, body = describe(repo.plan(provider=model), "main", "abc1234")
    assert title == "[OKF-Update] 1 section: AGENTS.md#Auth"
    assert "- `AGENTS.md#Auth`: tokens live 7 days (draft by test-model/1)" in body


def test_cli_fix_pr(repo, origin, monkeypatch, capsys):
    monkeypatch.setattr(pr_module, "gh", FakeGh())
    assert main(["fix", str(repo.root), "--pr", "--now", "2026-10-22T12:00:00Z"]) == 0
    assert "okf fix: opened a pull request from okf/update-main-" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["fix", str(repo.root), "--pr", "--apply"])


@pytest.mark.parametrize("workflow", [".github/workflows/okf.yml", "src/okf/templates/okf.yml"])
def test_auto_pr_job_is_off_by_default(workflow):
    import yaml

    from conftest import REPO_ROOT

    data = yaml.safe_load((REPO_ROOT / workflow).read_text(encoding="utf-8"))
    job = data["jobs"]["auto-pr"]
    assert "vars.OKF_AUTO_PR == 'true'" in job["if"] and "github.event_name == 'push'" in job["if"]
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    assert data[True]["workflow_dispatch"]["inputs"]["okf-auto-pr"]["default"] is False  # YAML reads "on" as True
    run = job["steps"][-1]["run"]
    assert 'okf fix "$OKF_REPO" --pr $draft' in run and job["steps"][-1]["env"]["GH_TOKEN"] == "${{ github.token }}"
