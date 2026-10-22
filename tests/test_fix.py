"""`okf fix`: mechanical fixes (layer 1) and LLM drafts (layer 2, with a mocked model)."""

import json
import os
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from conftest import doc, meta
from okf.bundle import load_document
from okf.cli import main
from okf.fix import (
    FIX_ACTOR, AnthropicProvider, FixError, OpenAICompatibleProvider, Provider, _actor, _replace_token, apply,
    plan_drafts, plan_fixes, provider_from_env, render,
)
from okf.git import Change, History
from okf.schema import verifications
from okf.trust import Sidecar, build_map, verify

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


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
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")
        return self

    def commit(self, when, message="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, when=when)
        return self

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def plan(self, changes=None, only=None, provider=None, now=NOW, **draft_options):
        history = History(self.root, now)
        trust_map = build_map(self.root, history, changes, now=now)
        plan = plan_fixes(self.root, history, trust_map, changes, only)
        if provider:
            plan_drafts(plan, trust_map, history, provider, only, **draft_options)
        return plan

    def units(self, now=NOW):
        return {u.name: u for u in build_map(self.root, History(self.root, now), now=now).units}


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo")


def moved_repo(repo):
    repo.write({"scripts/seed_db.sh": "#!/bin/sh\necho seed\n", "src/auth.py": "TTL = 30\n",
                "AGENTS.md": "# AGENTS\n\n## Commands\n\n```bash\n./scripts/seed_db.sh      # test data\n```\n\n"
                             "## Auth\n\nLogin: `src/auth.py`.\n"}).commit("2026-06-01T10:00:00Z")
    repo.git("mv", "scripts/seed_db.sh", "scripts/seed.sh")
    return repo.commit("2026-08-20T10:00:00Z", "rename")


# --- Layer 1: mechanical fixes ---


@pytest.mark.parametrize("line, expected", [
    ("cp src/config.py.bak src/config.py", "cp src/config.py.bak src/settings.py"),
    ("`src/config.py_old` and `src/config.py`", "`src/config.py_old` and `src/settings.py`"),
    ("src/config.py-x src/config.py/ src/config.py", "src/config.py-x src/config.py/ src/settings.py"),
    ("Settings live in src/config.py.", "Settings live in src/settings.py."),
])
def test_replace_token_never_touches_a_longer_name(line, expected):
    assert _replace_token(line, "src/config.py", "src/settings.py") == expected
    assert _replace_token("only src/config.py.bak here", "src/config.py", "src/settings.py") is None


def test_replace_token_keeps_alignment_and_whole_paths():
    assert _replace_token("./scripts/seed_db.sh      # data", "./scripts/seed_db.sh", "./scripts/seed.sh") == \
        "./scripts/seed.sh         # data"
    assert _replace_token("see `src/a.py` and `src/a.pyc`", "src/a.py", "lib/a.py") == "see `lib/a.py` and `src/a.pyc`"
    assert _replace_token("vendor/src/a.py", "src/a.py", "lib/a.py") is None


def test_moved_file_gets_its_new_path(repo):
    plan = moved_repo(repo).plan()
    [edit] = plan.edits
    assert (edit.unit, edit.old, edit.new) == ("AGENTS.md#Commands", "./scripts/seed_db.sh", "./scripts/seed.sh")
    mechanical, drafted = render(plan)
    assert "-./scripts/seed_db.sh      # test data\n+./scripts/seed.sh         # test data" in mechanical
    assert mechanical.startswith("--- a/AGENTS.md\n+++ b/AGENTS.md\n") and drafted == ""
    assert repo.read("AGENTS.md").count("seed_db.sh") == 1  # a diff only, nothing written


def test_apply_writes_and_lowers_trust_until_verified(repo):
    moved_repo(repo)
    before = repo.units()["AGENTS.md#Commands"]
    assert before.level == "recheck"
    assert apply(repo.plan(), repo.root, NOW) == ["AGENTS.md#Commands"]
    assert "./scripts/seed.sh         # test data" in repo.read("AGENTS.md")
    record = Sidecar(repo.root / ".okf/trust.yml").record("AGENTS.md#Commands")
    assert record["generated"] == {"by": FIX_ACTOR, "at": "2026-10-22T12:00:00Z"} and "verified" not in record
    unit = repo.units()["AGENTS.md#Commands"]
    assert (unit.level, unit.message) == ("unverified", "edited by process:okf-fix on 2026-10-22; not verified")
    verify("AGENTS.md#Commands", "human:ivan", datetime(2026, 10, 22, 12, 5, tzinfo=timezone.utc), repo.root, repo.root)
    assert repo.units()["AGENTS.md#Commands"].level == "human-verified"


def test_nested_and_root_relative_paths_keep_their_style(repo):
    repo.write({"packages/api/AGENTS.md": "## Run\n\n`scripts/start.sh` and [docs](/docs/api.md)\n",
                "packages/api/scripts/start.sh": "", "docs/api.md": ""}).commit("2026-06-01T10:00:00Z")
    (repo.root / "packages/api/bin").mkdir()
    repo.git("mv", "packages/api/scripts/start.sh", "packages/api/bin/start.sh")
    (repo.root / "docs/reference").mkdir()
    repo.git("mv", "docs/api.md", "docs/reference/api.md")
    repo.commit("2026-08-20T10:00:00Z")
    assert sorted((e.old, e.new) for e in repo.plan().edits) == [
        ("/docs/api.md", "/docs/reference/api.md"), ("scripts/start.sh", "bin/start.sh")]


def test_file_renamed_in_the_pull_request(repo):
    repo.write({"src/config.py": "", "AGENTS.md": "## Config\n\n`src/config.py`\n"}).commit("2026-06-01T10:00:00Z")
    (repo.root / "src/config.py").rename(repo.root / "src/settings.py")
    [edit] = repo.plan(changes=[Change("R", "src/settings.py", "src/config.py")]).edits
    assert (edit.old, edit.new) == ("src/config.py", "src/settings.py")


def test_renamed_npm_script_gets_its_new_name(repo):
    repo.write({"package.json": json.dumps({"scripts": {"test:unit": "vitest run", "lint": "eslint ."}}),
                "AGENTS.md": "## Test\n\nRun `npm run test:unit`.\n"}).commit("2026-06-01T10:00:00Z")
    repo.write({"package.json": json.dumps({"scripts": {"unit": "vitest run", "lint": "eslint ."}})})
    repo.commit("2026-08-01T10:00:00Z")
    [edit] = repo.plan().edits
    assert (edit.old, edit.new, edit.reason) == ("test:unit", "unit", 'script "test:unit" is now "unit" in package.json')
    apply(repo.plan(), repo.root, NOW)
    assert "Run `npm run unit`." in repo.read("AGENTS.md")


@pytest.mark.parametrize("scripts", [
    {"unit": "vitest run", "unit:again": "vitest run"},  # two candidates: not obvious
    {"unit": "vitest"},  # the command changed too
])
def test_unclear_script_renames_need_a_person(repo, scripts):
    repo.write({"package.json": json.dumps({"scripts": {"test:unit": "vitest run"}}),
                "AGENTS.md": "## Test\n\n`npm run test:unit`\n"}).commit("2026-06-01T10:00:00Z")
    repo.write({"package.json": json.dumps({"scripts": scripts})}).commit("2026-08-01T10:00:00Z")
    plan = repo.plan()
    assert plan.edits == [] and "needs a manual fix" in plan.manual[0].reason


def test_deleted_path_is_never_invented(repo):
    repo.write({"src/gone.py": "", "AGENTS.md": "## X\n\n`src/gone.py` and `npm run nope`\n",
                "package.json": json.dumps({"scripts": {}})}).commit("2026-06-01T10:00:00Z")
    repo.git("rm", "-q", "src/gone.py")
    repo.commit("2026-08-01T10:00:00Z")
    plan = repo.plan()
    assert plan.edits == []
    assert [m.reason for m in plan.manual] == ['"src/gone.py" does not exist: needs a manual fix',
                                               '"npm run nope": no script "nope" in package.json: needs a manual fix']


def test_okf_source_that_moved(repo):
    front = meta(sources=[{"resource": "../src/config.py"}])
    repo.write({"src/config.py": "DEBUG = 1\nPORT = 80\n", "kb/index.md": "# KB\n", "kb/guide.md": doc(front)})
    repo.commit("2026-06-01T10:00:00Z")
    repo.git("mv", "src/config.py", "src/settings.py")
    repo.commit("2026-08-01T10:00:00Z")
    assert repo.units()["kb/guide.md"].level == "recheck"
    [edit] = repo.plan().edits
    assert (edit.old, edit.new, edit.kind) == ("../src/config.py", "../src/settings.py", "knowledge")
    apply(repo.plan(), repo.root, NOW)
    document = load_document(repo.root / "kb/guide.md", repo.root / "kb")
    assert document.meta["sources"] == [{"resource": "../src/settings.py"}]
    assert document.meta["generated"] == {"by": FIX_ACTOR, "at": "2026-10-22T12:00:00Z"}
    assert len(verifications(document)) == 1  # verified is left alone
    assert repo.units()["kb/guide.md"].level == "unverified"


def test_only_limits_the_fixes(repo):
    moved_repo(repo)
    assert repo.plan(only=["AGENTS.md#Auth"]).edits == []


# --- Layer 2: drafts with a mocked model ---


class FakeModel(Provider):
    actor = "test-model/1"

    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def complete(self, system, prompt, unit):
        self.prompts.append((system, prompt, unit))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


SECTION = "## Auth\n\nLogin: `src/auth.py`.\n"


def drifted_repo(repo):
    repo.write({"src/auth.py": "TTL = 30\n", "src/config.py": "",
                "AGENTS.md": "# AGENTS\n\n" + SECTION + "\n## Other\n\nText.\n"}).commit("2026-06-01T10:00:00Z")
    verify("AGENTS.md#Auth", "human:ivan", datetime(2026, 9, 1, tzinfo=timezone.utc), repo.root, repo.root)
    repo.write({"src/auth.py": "TTL = 7  # shorter refresh tokens\n"}).commit("2026-10-20T10:00:00Z")
    assert repo.units()["AGENTS.md#Auth"].level == "recheck"
    return repo


def test_draft_gets_the_section_sources_and_their_diff(repo):
    model = FakeModel({"section": "## Auth\n\nLogin: `src/auth.py` (7-day refresh tokens).\n",
                       "summary": "refresh tokens now live 7 days", "changed": True})
    plan = drifted_repo(repo).plan(provider=model)
    [draft] = plan.drafts
    assert draft.rejected is None and draft.summary == "refresh tokens now live 7 days"
    system, prompt, unit = model.prompts[0]
    assert unit == "AGENTS.md#Auth" and "Do not invent file paths" in system
    assert "Login: `src/auth.py`." in prompt and "+TTL = 7" in prompt and "since 2026-09-01" in prompt
    _, drafted = render(plan)
    assert "-Login: `src/auth.py`.\n+Login: `src/auth.py` (7-day refresh tokens).\n \n ## Other" in drafted


def test_applied_draft_is_generated_not_verified(repo):
    model = FakeModel({"section": "## Auth\n\nLogin: `src/auth.py`, 7-day tokens.\n", "summary": "x", "changed": True})
    plan = drifted_repo(repo).plan(provider=model)
    apply(plan, repo.root, NOW)
    record = Sidecar(repo.root / ".okf/trust.yml").record("AGENTS.md#Auth")
    assert record["generated"] == {"by": "test-model/1", "at": "2026-10-22T12:00:00Z"}
    assert [v["by"] for v in record["verified"]] == ["human:ivan"]  # the old confirmation stays, but is not enough
    unit = repo.units()["AGENTS.md#Auth"]
    assert unit.level == "unverified" and unit.message.startswith("edited by test-model/1 on 2026-10-22; not verified")


@pytest.mark.parametrize("answer,reason", [
    ({"section": "## Auth\n\nLogin: `src/session.py`.\n", "summary": "", "changed": True},
     'the draft mentions "src/session.py", which does not exist'),
    ({"section": "## Authentication\n\nLogin: `src/auth.py`.\n", "summary": "", "changed": True},
     'the draft changed the heading to "## Authentication"'),
    ({"section": SECTION, "summary": "still fine", "changed": False},
     "the model says the section is still correct: confirm it with okf verify"),
    ({"summary": "no section"}, "the model returned no section"),
    (FixError("the model declined to draft this section"), "the model declined to draft this section"),
])
def test_bad_drafts_are_rejected(repo, answer, reason):
    plan = drifted_repo(repo).plan(provider=FakeModel(answer))
    assert plan.drafts[0].rejected == reason
    assert render(plan)[1] == ""


def test_a_command_the_draft_invents_is_rejected(repo):
    repo.write({"package.json": json.dumps({"scripts": {"test": "pytest"}})})
    answer = {"section": "## Auth\n\nLogin: `src/auth.py`; test with `npm run test:auth`.\n", "summary": "",
              "changed": True}
    plan = drifted_repo(repo).plan(provider=FakeModel(answer))
    assert plan.drafts[0].rejected == 'the draft mentions "npm run test:auth", which does not exist'


def test_a_diff_over_the_limit_is_not_sent(repo):
    model = FakeModel({"section": SECTION, "summary": "", "changed": True})
    plan = drifted_repo(repo).plan(provider=model, max_diff=10)
    assert plan.drafts[0].rejected.startswith("the diff is ") and model.prompts == []


def test_provider_from_env():
    assert provider_from_env({}) is None
    claude = provider_from_env({"ANTHROPIC_API_KEY": "k"})
    assert isinstance(claude, AnthropicProvider) and claude.actor == "anthropic/claude-opus-5-5"
    other = provider_from_env({"ANTHROPIC_API_KEY": "k", "OKF_LLM_BASE_URL": "http://x/v1", "OKF_LLM_API_KEY": "o",
                               "OKF_LLM_MODEL": "meta-llama/Llama-3.3:70b", "OKF_LLM_MAX_TOKENS": "500"})
    assert isinstance(other, OpenAICompatibleProvider) and other.max_tokens == 500
    assert other.actor == "openai-compatible/meta-llama-Llama-3.3-70b" == _actor("openai-compatible",
                                                                                 "meta-llama/Llama-3.3:70b")


def test_without_a_key_only_the_mechanical_layer_runs(repo, capsys, monkeypatch):
    moved_repo(repo)
    for name in ("ANTHROPIC_API_KEY", "OKF_LLM_BASE_URL", "OKF_LLM_API_KEY", "OKF_LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert main(["fix", str(repo.root), "--draft"]) == 0
    out, err = capsys.readouterr()
    assert "+./scripts/seed.sh" in out
    assert "no LLM key, so no drafts: set ANTHROPIC_API_KEY, or OKF_LLM_BASE_URL + OKF_LLM_API_KEY + OKF_LLM_MODEL" in err


def test_cli_replay_and_apply(repo, capsys, tmp_path):
    drifted_repo(repo)
    saved = tmp_path / "answer.json"
    saved.write_text(json.dumps({"provider": "anthropic", "model": "claude-opus-5-5", "units": {
        "AGENTS.md#Auth": {"section": "## Auth\n\nLogin: `src/auth.py` (7 days).\n", "summary": "7 days", "changed": True}
    }}), encoding="utf-8")
    assert main(["fix", str(repo.root), "--replay", str(saved), "--apply"]) == 0
    err = capsys.readouterr().err
    assert "AGENTS.md#Auth: 7 days (by anthropic/claude-opus-5-5; not verified)" in err
    assert "Login: `src/auth.py` (7 days)." in repo.read("AGENTS.md")


# --- the real providers, against a local fake server (no network, no key) ---


class _Server:
    def __init__(self, reply):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                data = json.dumps(reply(body)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


ANSWER = {"section": "## Auth\n\nok\n", "summary": "s", "changed": True}


def test_openai_compatible_provider():
    server = _Server(lambda body: {"choices": [{"finish_reason": "stop",
                                                "message": {"content": "```json\n" + json.dumps(ANSWER) + "\n```"}}]})
    try:
        answer = OpenAICompatibleProvider(server.url + "/v1", "secret", "local-model", 300).complete("sys", "hi", "u")
    finally:
        server.close()
    path, headers, body = server.requests[0]
    assert answer == ANSWER and path == "/v1/chat/completions" and headers["authorization"] == "Bearer secret"
    assert body["temperature"] == 0 and body["max_tokens"] == 300 and body["messages"][0]["role"] == "system"


def test_anthropic_provider(monkeypatch):
    pytest.importorskip("anthropic")
    server = _Server(lambda body: {
        "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
        "content": [{"type": "text", "text": json.dumps(ANSWER)}], "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })
    monkeypatch.setenv("ANTHROPIC_BASE_URL", server.url)
    try:
        answer = AnthropicProvider("test-key", max_tokens=1000).complete("sys", "hi", "u")
    finally:
        server.close()
    path, headers, body = server.requests[0]
    assert answer == ANSWER and path.startswith("/v1/messages")
    assert "test-key" in (headers.get("x-api-key", ""), headers.get("authorization", "").removeprefix("Bearer "))
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default" and "temperature" not in body
    assert body["output_config"]["format"]["schema"]["required"] == ["section", "summary", "changed"]
    assert "server-side-fallback-2026-07-01" in headers["anthropic-beta"]


def test_verify_all_current_leaves_ai_edits_to_a_person(repo, capsys, monkeypatch):
    model = FakeModel({"section": "## Auth\n\nLogin: `src/auth.py`, 7-day tokens.\n", "summary": "x", "changed": True})
    plan = drifted_repo(repo).plan(provider=model)
    apply(plan, repo.root, NOW)
    assert repo.units()["AGENTS.md#Auth"].reason == "unverified:generated"
    monkeypatch.chdir(repo.root)
    assert main(["verify", "--all-current", "--by", "human:ivan", "--at", "2026-10-22T13:00:00Z"]) == 0
    err = capsys.readouterr().err
    assert "AGENTS.md#Other verified by human:ivan" in err and "AGENTS.md#Auth verified" not in err
    assert "skipped 1 edited by a tool or a model (AGENTS.md#Auth): read each and confirm it with okf verify" in err
    assert repo.units(now=datetime(2026, 10, 23, tzinfo=timezone.utc))["AGENTS.md#Auth"].level == "unverified"
    assert main(["verify", "AGENTS.md#Auth", "--by", "human:ivan", "--at", "2026-10-22T14:00:00Z"]) == 0
    assert repo.units(now=datetime(2026, 10, 23, tzinfo=timezone.utc))["AGENTS.md#Auth"].level == "human-verified"
