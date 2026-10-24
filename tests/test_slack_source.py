"""Pinned Slack messages as sources, on fixtures and a mock server only."""

import json
from datetime import datetime, timezone

import pytest

from conftest import doc, meta, NOW
from okf.git import History
from okf.sources import registry
from okf.sources.http import Http
from okf.sources.slack import SlackSource, message_ref
from okf.trust import build_map

TS = "1726000000.000100"  # 2024-09-10
EDITED = "1729000000.000000"  # 2024-10-15T13:46:40Z


@pytest.mark.parametrize("resource, expected", [
    (f"slack://C0WHL01/{TS}", ("C0WHL01", TS)),
    ("https://wheelo.slack.com/archives/C0WHL01/p1726000000000100", ("C0WHL01", TS)),
    ("https://wheelo.slack.com/archives/C0WHL01/p1726000000000100?thread_ts=1.2&cid=C0WHL01", ("C0WHL01", TS)),
    ("https://wheelo.slack.com/archives/C0WHL01", None),
    ("https://example.com/archives/C0WHL01/p1726000000000100", None),
    ("slack://C0WHL01/123", None),
])
def test_slack_resources(resource, expected):
    assert message_ref(resource) == expected


def fixtures(tmp_path, *, edited=None, pinned=True, exists=True):
    root = tmp_path / "slack"
    (root / "api").mkdir(parents=True, exist_ok=True)
    message = {"type": "message", "ts": TS, "text": "Решение: сессия заканчивается после 30 минут паузы."}
    if edited:
        message["edited"] = {"user": "U1", "ts": edited}
    history = {"ok": True, "messages": [message] if exists else [{"ts": "1725000000.000100", "text": "older"}]}
    pins = {"ok": True, "items": [{"type": "message", "created": 1726000100, "message": message}] if pinned else []}
    (root / "api" / f"conversations.history@latest={TS}.json").write_text(json.dumps(history, ensure_ascii=False),
                                                                          encoding="utf-8")
    (root / "api" / "pins.list@channel=C0WHL01.json").write_text(json.dumps(pins, ensure_ascii=False), encoding="utf-8")
    return {"OKF_SOURCES_FIXTURES": str(root), "OKF_SLACK_TOKEN": "xoxb-test"}


def unit_for(make_bundle, env, verified="2024-10-01T00:00:00Z"):
    root = make_bundle({"index.md": "[m](m.md)\n", "m.md": doc(meta(**{
        "verified": [{"by": "human:anna", "at": verified}], "generated": {"by": "human:anna", "at": verified},
        "sources": [{"resource": f"https://wheelo.slack.com/archives/C0WHL01/p{TS.replace('.', '')}"}]}))})
    sources = registry(env)
    next(c for c in sources.connectors if isinstance(c, SlackSource)).now = NOW
    [unit] = build_map(root, History(None, NOW), now=NOW, sources=sources).units
    return unit


def test_pinned_and_unchanged_is_current(make_bundle, tmp_path):
    unit = unit_for(make_bundle, fixtures(tmp_path))
    assert unit.level == "human-verified" and unit.remote[0].status == "ok"


def test_edited_after_the_check_asks_for_a_recheck(make_bundle, tmp_path):
    unit = unit_for(make_bundle, fixtures(tmp_path, edited=EDITED))
    assert (unit.level, unit.reason) == ("recheck", "recheck:source-changed")
    assert unit.message == f"Slack message {TS} in C0WHL01 was edited 2024-10-15, last verified 2024-10-01 by human:anna"
    assert unit_for(make_bundle, fixtures(tmp_path, edited=EDITED), verified="2024-10-20T00:00:00Z").level == \
        "human-verified"


def test_unpinned_or_deleted_asks_for_a_recheck(make_bundle, tmp_path):
    unpinned = unit_for(make_bundle, fixtures(tmp_path, pinned=False), verified="2026-10-01T00:00:00Z")
    assert unpinned.reason == "recheck:unpinned"
    assert unpinned.message.startswith(f"Slack message {TS} in C0WHL01 is no longer pinned, seen 2026-10-22")
    gone = unit_for(make_bundle, fixtures(tmp_path, exists=False, pinned=False))
    assert gone.reason == "recheck:source-gone"


def test_changes_since_shows_the_text_now(tmp_path):
    env = fixtures(tmp_path, edited=EDITED)
    slack = SlackSource(env, Http(env))
    text = slack.changes_since(f"slack://C0WHL01/{TS}", datetime(2024, 10, 1, tzinfo=timezone.utc))
    assert "was edited 2024-10-15 (Slack keeps no earlier text)" in text and "30 минут" in text
    assert slack.changes_since(f"slack://C0WHL01/{TS}", datetime(2024, 10, 20, tzinfo=timezone.utc)) is None


def test_without_a_token_nothing_is_requested():
    http = Http({})
    check = registry({}, http=http).check(f"slack://C0WHL01/{TS}")
    assert (check.status, check.message) == ("unknown", "connector not configured: set OKF_SLACK_TOKEN")
    assert http.requests == 0


def test_api_errors_are_unknown_with_a_hint(mock):
    server = mock({"/api/conversations.history": [(200, {"ok": False, "error": "not_in_channel"}, {})]})
    env = {"OKF_SLACK_TOKEN": "xoxb-secret", "OKF_SLACK_API_URL": server.url + "/api"}
    check = registry(env).check(f"slack://C0WHL01/{TS}")
    assert check.status == "unknown"
    assert check.message == f"Slack message {TS} in C0WHL01: Slack: not_in_channel: invite the bot to the channel"
    assert server.seen[0][1]["Authorization"] == "Bearer xoxb-secret" and "xoxb-secret" not in check.message
