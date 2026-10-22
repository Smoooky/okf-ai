"""`okf notify`: grouping by the last verifier, Slack and Teams payloads, on a mocked webhook."""

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from okf import notify as notify_module
from okf.cli import main
from okf.notify import NOBODY, NotifyError, reminders, send, slack_message, teams_message
from test_trust import AGENTS, Repo, code_repo

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


class Webhook:
    """A local HTTP server for webhook POSTs: answers in order, the last one repeats."""

    def __init__(self, answers=((200, {}),)):
        self.posts, self.answers = [], list(answers)
        hook = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                hook.posts.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                status, headers = hook.answers.pop(0) if len(hook.answers) > 1 else hook.answers[0]
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hooks/secret-token-123"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def webhook():
    hooks = []

    def start(answers=((200, {}),)):
        hooks.append(Webhook(answers))
        return hooks[-1]

    yield start
    for hook in hooks:
        hook.close()


@pytest.fixture
def drifted(tmp_path):
    repo = Repo(tmp_path / "repo")
    code_repo(repo).write({"AGENTS.md": AGENTS + "\n## Seed\n\nRun `src/seed.py`.\n", "src/seed.py": ""})
    repo.commit("2026-09-01T10:00:00Z")
    repo.verify("AGENTS.md#Auth", by="human:ivan")
    repo.verify("AGENTS.md#Billing", by="human:maria")
    repo.commit("2026-09-05T11:00:00Z")
    repo.write({"src/auth.py": "TTL = 7\n", "src/billing.py": "FEE = 60\n", "src/seed.py": "x = 1\n"})
    repo.commit("2026-10-20T10:00:00Z")
    return repo


def test_reminders_group_by_the_last_verifier(drifted):
    found = reminders(drifted.map())
    assert [(r.who, [u.name for u in r.units]) for r in found] == [
        ("human:ivan", ["AGENTS.md#Auth"]), ("human:maria", ["AGENTS.md#Billing"]), (NOBODY, ["AGENTS.md#Seed"])]


def test_slack_and_teams_messages(drifted):
    [ivan, _, nobody] = reminders(drifted.map())
    web = "https://github.com/acme/app/blob/abc"
    text = slack_message(ivan, drifted.root, web, drifted.root, {"human:ivan": {"slack": "U0IVAN"}})["text"]
    assert text.startswith(":mag: okf-ai: <@U0IVAN>, 1 section you confirmed need a recheck")
    assert f"• <{web}/AGENTS.md#L5|AGENTS.md#Auth>: src/auth.py changed 2026-10-20" in text
    assert text.endswith('confirm in one command: `okf verify "AGENTS.md#Auth"`')
    assert "never confirmed section needs" in slack_message(nobody, drifted.root, None, None)["text"]
    card = teams_message(ivan, drifted.root, web, drifted.root)
    assert card["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
    blocks = [b["text"] for b in card["attachments"][0]["content"]["body"]]
    assert blocks[1].startswith(f"- [AGENTS.md#Auth]({web}/AGENTS.md#L5): ") and blocks[-1] == 'okf verify "AGENTS.md#Auth"'


def test_send_retries_429_and_never_shows_the_url(webhook):
    hook = webhook([(429, {"Retry-After": "1"}), (200, {})])
    pauses = []
    send(hook.url, {"text": "hi"}, sleep=pauses.append)
    assert pauses == [1.0] and len(hook.posts) == 2
    broken = webhook([(404, {})])
    with pytest.raises(NotifyError) as exc:
        send(broken.url, {"text": "hi"})
    assert str(exc.value) == "the webhook answered HTTP 404" and "secret-token" not in str(exc.value)


def test_cli_notify_sends_one_message_per_person(drifted, webhook, capsys, monkeypatch):
    slack, teams = webhook(), webhook()
    monkeypatch.setattr(notify_module.time, "sleep", lambda s: None)
    code = main(["notify", str(drifted.root), "--slack-webhook", slack.url, "--teams-webhook", teams.url,
                 "--now", "2026-10-22T12:00:00Z"])
    err = capsys.readouterr().err
    assert code == 0 and "3 units to recheck, 3 people or groups; sent 6 messages" in err
    assert len(slack.posts) == 3 and len(teams.posts) == 3 and "secret-token" not in err
    assert "*human:ivan*" in slack.posts[0][1]["text"] and teams.posts[0][1]["type"] == "message"


def test_cli_notify_dry_run_and_settings(drifted, capsys, monkeypatch):
    monkeypatch.delenv("OKF_SLACK_WEBHOOK", raising=False)
    monkeypatch.delenv("OKF_TEAMS_WEBHOOK", raising=False)
    assert main(["notify", str(drifted.root)]) == 2
    assert "--dry-run prints the messages" in capsys.readouterr().err
    assert main(["notify", str(drifted.root), "--dry-run", "--now", "2026-10-22"]) == 0
    out, err = capsys.readouterr()
    assert "--- slack, for human:maria ---" in out and "would send 3 messages" in err


def test_failed_webhook_exits_1(drifted, webhook, capsys):
    hook = webhook([(500, {})])
    assert main(["notify", str(drifted.root), "--slack-webhook", hook.url, "--now", "2026-10-22"]) == 1
    assert "the webhook answered HTTP 500" in capsys.readouterr().err


@pytest.mark.parametrize("workflow", [".github/workflows/okf.yml", "src/okf/templates/okf.yml"])
def test_notify_job_runs_on_schedule_only_with_a_webhook(workflow):
    import yaml

    from conftest import REPO_ROOT

    data = yaml.safe_load((REPO_ROOT / workflow).read_text(encoding="utf-8"))
    job = data["jobs"]["notify"]
    assert job["if"] == "github.event_name == 'schedule'" and data[True]["schedule"]
    assert all(step["if"] == "env.OKF_SLACK_WEBHOOK != '' || env.OKF_TEAMS_WEBHOOK != ''" for step in job["steps"])
    assert job["env"]["OKF_SLACK_WEBHOOK"] == "${{ secrets.OKF_SLACK_WEBHOOK }}"
    assert data["jobs"]["knowledge"]["if"] == "github.event_name != 'schedule'"


def test_a_negative_retry_after_is_clamped(webhook):
    hook = webhook([(429, {"Retry-After": "-5"}), (503, {"Retry-After": "soon"}), (200, {})])
    pauses = []
    send(hook.url, {"text": "hi"}, sleep=pauses.append)  # was ValueError: sleep length must be non-negative
    assert pauses == [0.0, 2.0] and len(hook.posts) == 3
