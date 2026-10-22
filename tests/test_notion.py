"""The Notion connector and `okf import notion`, on fixtures and a mock server only."""

import json
from datetime import datetime, timezone

import pytest

from conftest import doc, meta
from okf.bundle import Bundle
from okf.cli import main
from okf.git import History
from okf.importer import import_notion
from okf.report import ERROR
from okf.schema import get_profile
from okf.sources import registry
from okf.sources.http import Http
from okf.sources.notion import MIN_INTERVAL, SNAPSHOTS, NotionSource, page_id
from okf.trust import build_map
from okf.validate import validate_bundle

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
ROOT_ID = "1a2b3c4d5e6f40718293a4b5c6d7e8f9"
CHILD_ID = "0f0e0d0c0b0a49384756a5b4c3d2e1f0"


def dashed(raw):
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def text(content, **annotations):
    return {"plain_text": content, "annotations": annotations, "href": None}


def block(kind, content="", children=False, **extra):
    return {"id": f"b-{kind}-{content[:4]}", "type": kind, "has_children": children,
            kind: {"rich_text": [text(content)] if content else [], **extra}}


def page(raw, title, edited):
    return {"object": "page", "id": dashed(raw), "url": f"https://www.notion.so/Page-{raw}",
            "last_edited_time": edited, "properties": {"Name": {"type": "title", "title": [text(title)]}}}


@pytest.fixture
def fixtures(tmp_path):
    root = tmp_path / "notion"

    def put(rel, data):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    put(f"v1/pages/{dashed(ROOT_ID)}.json", page(ROOT_ID, "Онбординг", "2026-10-10T09:30:00.000Z"))
    put(f"v1/pages/{dashed(CHILD_ID)}.json", page(CHILD_ID, "Доступы", "2026-09-01T10:00:00.000Z"))
    put(f"v1/blocks/{dashed(ROOT_ID)}/children.json", {"results": [
        block("heading_2", "Первый день"),
        block("paragraph", "Ставим окружение по гайду."),
        block("bulleted_list_item", "Репозиторий", children=True),
        block("code", "make seed", language="bash"),
    ], "has_more": True, "next_cursor": "c2"})
    put(f"v1/blocks/{dashed(ROOT_ID)}/children@start_cursor=c2.json", {"results": [
        {"id": dashed(CHILD_ID), "type": "child_page", "has_children": True, "child_page": {"title": "Доступы"}},
        block("to_do", "Получить VPN", checked=True),
    ], "has_more": False, "next_cursor": None})
    put("v1/blocks/b-bulleted_list_item-Репо/children.json", {"results": [
        block("bulleted_list_item", "клонировать okf-ai")], "has_more": False})
    put(f"v1/blocks/{dashed(CHILD_ID)}/children.json", {"results": [
        block("paragraph", "VPN и GitHub — у тимлида.")], "has_more": False})
    return root


def env(fixtures):
    return {"OKF_SOURCES_FIXTURES": str(fixtures), "OKF_NOTION_TOKEN": "secret_test"}


@pytest.mark.parametrize("resource, expected", [
    (f"https://www.notion.so/Onboarding-{ROOT_ID}", dashed(ROOT_ID)),
    (f"https://www.notion.so/acme/Onboarding-{ROOT_ID}?pvs=4", dashed(ROOT_ID)),
    (f"https://acme.notion.site/{ROOT_ID}", dashed(ROOT_ID)),
    (f"notion://{ROOT_ID}", dashed(ROOT_ID)),
    (f"notion://{dashed(ROOT_ID)}", dashed(ROOT_ID)),
    ("https://www.notion.so/Onboarding", None),
    (f"https://example.com/Onboarding-{ROOT_ID}", None),
])
def test_notion_resources(resource, expected):
    assert page_id(resource) == expected


def notion(fixtures, tmp_path=None, **kwargs):
    return NotionSource(env(fixtures), Http(env(fixtures)), sleep=lambda s: None, **kwargs)


def test_page_date_title_and_blocks(fixtures):
    source = notion(fixtures)
    resource = f"notion://{ROOT_ID}"
    assert source.last_modified(resource) == datetime(2026, 10, 10, 9, 30, tzinfo=timezone.utc)
    assert source.describe(resource) == 'Notion page "Онбординг"'
    page = source.page(resource)
    assert page.text == ("## Первый день\n\nСтавим окружение по гайду.\n\n- Репозиторий\n  - клонировать okf-ai\n\n"
                         "```bash\nmake seed\n```\n\n- Page: Доступы\n- [x] Получить VPN\n")
    assert page.children == [(dashed(CHILD_ID), "Доступы")]


def test_requests_are_spaced_to_three_a_second(fixtures):
    pauses, clock = [], iter([0.0, 0.0, 0.1, 0.1, 1.0, 1.0, 1.05, 1.05, 5.0, 5.0])
    source = NotionSource(env(fixtures), Http(env(fixtures)), sleep=pauses.append, clock=lambda: next(clock))
    source.page(f"notion://{ROOT_ID}")
    assert pauses and all(0 < p <= MIN_INTERVAL for p in pauses)


def test_changes_since_without_and_with_a_snapshot(fixtures, tmp_path):
    source = notion(fixtures)
    source.root = tmp_path
    resource = f"notion://{ROOT_ID}"
    since = datetime(2026, 9, 5, tzinfo=timezone.utc)
    assert "there is no saved snapshot" in source.changes_since(resource, since)
    snapshot = tmp_path / SNAPSHOTS / f"{dashed(ROOT_ID)}.md"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("## Первый день\n\nСтавим окружение вручную.\n", encoding="utf-8")
    diff = notion(fixtures)
    diff.root = tmp_path
    text = diff.changes_since(resource, since)
    assert "-Ставим окружение вручную." in text and "+Ставим окружение по гайду." in text
    assert diff.changes_since(resource, datetime(2026, 10, 11, tzinfo=timezone.utc)) is None


def test_edited_page_asks_for_a_recheck_and_without_a_token_is_unknown(fixtures, make_bundle):
    root = make_bundle({"index.md": "[m](m.md)\n", "m.md": doc(meta(**{
        "verified": [{"by": "human:anna", "at": "2026-09-05T00:00:00Z"}],
        "generated": {"by": "human:anna", "at": "2026-09-05T00:00:00Z"},
        "sources": [{"resource": f"https://www.notion.so/Onboarding-{ROOT_ID}"}]}))})
    [unit] = build_map(root, History(None, NOW), now=NOW, sources=registry(env(fixtures))).units
    assert (unit.level, unit.reason) == ("recheck", "recheck:source-changed")
    assert unit.message == 'Notion page "Онбординг" changed 2026-10-10, last verified 2026-09-05 by human:anna'
    http = Http({})
    check = registry({}, http=http).check(f"notion://{ROOT_ID}")
    assert (check.status, check.message) == ("unknown", "connector not configured: set OKF_NOTION_TOKEN")
    assert http.requests == 0


def test_import_notion_recursive(fixtures, tmp_path):
    out = tmp_path / "kb"
    done = import_notion(notion(fixtures), out, [ROOT_ID], True, None, 50, NOW, tmp_path)
    assert [(d.path.name, d.action) for d in done] == [("onbording.md", "new"), ("dostupy.md", "new")]
    assert not [i for i in validate_bundle(Bundle.load(out), get_profile(False)) if i.level == ERROR]
    text = (out / "onbording.md").read_text(encoding="utf-8")
    assert f"    resource: https://www.notion.so/Page-{ROOT_ID}\n" in text and "generated: { by: process:okf-import" in text
    assert "    last_modified: 2026-10-10T09:30:00Z\n" in text and "## Первый день" in text
    assert (tmp_path / SNAPSHOTS / f"{dashed(ROOT_ID)}.md").read_text(encoding="utf-8").startswith("## Первый день")
    again = import_notion(notion(fixtures), out, [ROOT_ID], False, None, 50, NOW, tmp_path)
    assert [(d.path.name, d.action) for d in again] == [("onbording.md", "unchanged")]


def test_cli_import_notion(fixtures, tmp_path, capsys, monkeypatch):
    for key, value in env(fixtures).items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(tmp_path)
    assert main(["import", "notion", "--page", f"https://www.notion.so/x-{ROOT_ID}", "--out", "kb"]) == 0
    assert "1 pages from Notion, 1 written" in capsys.readouterr().err
    assert main(["import", "notion", "--space", "X", "--out", "kb"]) == 2


def test_headers_and_429_against_a_mock_server(mock):
    server = mock({f"/v1/pages/{dashed(ROOT_ID)}": [(429, {}, {"Retry-After": "1"}),
                                                    (200, page(ROOT_ID, "T", "2026-10-10T09:30:00.000Z"), {})]})
    pauses = []
    env_ = {"OKF_NOTION_TOKEN": "secret_abc", "OKF_NOTION_URL": server.url}
    source = NotionSource(env_, Http(env_, sleep=pauses.append), sleep=pauses.append)
    assert source.last_modified(f"notion://{ROOT_ID}") == datetime(2026, 10, 10, 9, 30, tzinfo=timezone.utc)
    assert pauses == [1.0]
    _, headers = server.seen[-1]
    assert headers["Authorization"] == "Bearer secret_abc" and headers["Notion-Version"] == "2022-06-28"
