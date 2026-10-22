"""Connectors (okf/sources): Confluence and Jira on mocked HTTP only, never the real Atlassian."""

import json
import threading
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from conftest import REPO_ROOT, doc, meta
from okf.bundle import Bundle
from okf.cli import main
from okf.git import History
from okf.importer import import_confluence
from okf.report import ERROR, INFO, WARNING
from okf.schema import get_profile
from okf.sources import ConfluenceSource, GitSource, JiraSource, registry
from okf.sources.confluence import markdown, page_ref
from okf.sources.http import Http
from okf.sources.jira import issue_ref
from okf.stale import find_stale
from okf.trust import build_map
from okf.validate import validate_bundle

FIXTURES = REPO_ROOT / "examples" / "atlassian-fixtures"
CLOUD = {"OKF_SOURCES_FIXTURES": str(FIXTURES), "OKF_CONFLUENCE_URL": "https://wheelo.atlassian.net/wiki",
         "OKF_JIRA_URL": "https://wheelo.atlassian.net"}
PAGE = "https://wheelo.atlassian.net/wiki/spaces/WHL/pages/131073/Metriki+produkta"
EPIC = "https://wheelo.atlassian.net/browse/WHL-42"
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any request that is not to the local mock server fails the test."""
    real = urllib.request.urlopen

    def guarded(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else request
        assert url.startswith("http://127.0.0.1:"), f"unexpected network call to {url}"
        return real(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", guarded)


# --- Recognizing resources ---


@pytest.mark.parametrize("resource, expected", [
    ("https://wheelo.atlassian.net/wiki/spaces/WHL/pages/131073/Metriki+produkta", ("wheelo.atlassian.net", "131073")),
    ("https://wheelo.atlassian.net/wiki/spaces/WHL/pages/131073", ("wheelo.atlassian.net", "131073")),
    ("https://wheelo.atlassian.net/wiki/spaces/WHL/pages/edit-v2/131073", ("wheelo.atlassian.net", "131073")),
    ("https://confluence.wheelo.ru/pages/viewpage.action?pageId=4456", ("confluence.wheelo.ru", "4456")),
    ("https://wiki.corp/confluence/pages/viewpage.action?spaceKey=X&pageId=77", ("wiki.corp", "77")),
    ("confluence://131073", (None, "131073")),
    ("confluence:131073", (None, "131073")),
    ("https://wheelo.atlassian.net/wiki/spaces/WHL/overview", None),
    ("https://confluence.wheelo.ru/pages/viewpage.action?pageId=abc", None),
    ("https://wiki.wheelo.example/legal/personal-data", None),
    ("../src/auth.py", None),
])
def test_confluence_resources(resource, expected):
    assert page_ref(resource) == expected


@pytest.mark.parametrize("resource, expected", [
    ("https://wheelo.atlassian.net/browse/WHL-42", ("wheelo.atlassian.net", "WHL-42")),
    ("https://jira.wheelo.ru/browse/PAY_2-7/", ("jira.wheelo.ru", "PAY_2-7")),
    ("jira://WHL-42", (None, "WHL-42")),
    ("jira:WHL-42", (None, "WHL-42")),
    ("https://wheelo.atlassian.net/browse/whl-42", None),
    ("https://wheelo.atlassian.net/jira/software/projects/WHL/boards/1", None),
    ("https://github.com/acme/app/blob/main/src/auth.py", None),
])
def test_jira_resources(resource, expected):
    assert issue_ref(resource) == expected


def test_registry_picks_the_connector():
    sources = registry({})
    assert isinstance(sources.find(PAGE), ConfluenceSource)
    assert isinstance(sources.find("jira://WHL-1"), JiraSource)
    assert isinstance(sources.find("../src/auth.py"), GitSource)
    assert isinstance(sources.find("https://github.com/acme/app/blob/main/src/auth.py"), GitSource)
    assert sources.find("https://metabase.wheelo.example/dashboard/12") is None


# --- Without settings: unknown, and no network at all ---


def test_without_settings_the_status_is_unknown_and_nothing_is_requested():
    http = Http({})
    sources = registry({}, http=http)
    for resource, setting in ((PAGE, "OKF_CONFLUENCE_URL"), (EPIC, "OKF_JIRA_URL")):
        check = sources.check(resource)
        assert (check.status, check.message) == ("unknown", f"connector not configured: set {setting}")
        assert check.actionable and check.signal is None
    other = sources.check("https://metabase.wheelo.example/dashboard/12")
    assert (other.connector, other.status, other.actionable) == (None, "unknown", False)
    assert http.requests == 0


def test_a_page_on_another_site_is_not_sent_the_credentials():
    http = Http({})
    env = {"OKF_CONFLUENCE_URL": "https://acme.atlassian.net/wiki", "OKF_ATLASSIAN_PAT": "secret-pat"}
    check = registry(env, http=http).check(PAGE)
    assert check.message == "OKF_CONFLUENCE_URL is acme.atlassian.net, not wheelo.atlassian.net"
    assert http.requests == 0


# --- Confluence and Jira from fixtures (the shape of Cloud REST v2 / v3 answers) ---


def test_confluence_page_date_and_description():
    sources = registry(CLOUD)
    check = sources.check(PAGE)
    assert check.status == "ok" and check.message == 'Confluence page "Метрики продукта" (v7)'
    assert check.last_modified == at("2026-08-28T12:00:00Z")
    assert check.signal.reason == "recheck:source-changed"


def test_confluence_changes_since_is_a_diff_of_versions():
    confluence = registry(CLOUD).find("confluence://131074")
    text = confluence.changes_since("confluence://131074", at("2026-09-01T00:00:00Z"))
    assert "--- Тарифы и биллинг v2 (2026-08-20)" in text and "+++ Тарифы и биллинг v3 (2026-10-03)" in text
    assert "-Поминутный тариф — **8 ₽** в минуту" in text and "+- Ночью (00:00–06:00) — 7 ₽ в минуту." in text
    assert confluence.changes_since("confluence://131074", at("2026-10-05T00:00:00Z")) is None


def test_storage_format_to_markdown():
    storage = (
        "<h1>Title</h1><p>Text with <strong>bold</strong>, <em>it</em> and <code>make seed</code>.<br/>Next line.</p>"
        "<ul><li>one<ul><li>nested</li></ul></li><li>two</li></ul><ol><li>first</li><li>second</li></ol>"
        '<p><a href="https://example.com/x">a link</a> and <ac:link><ri:page ri:content-title="Other page"/></ac:link>'
        '</p><ac:structured-macro ac:name="code"><ac:parameter ac:name="language">bash</ac:parameter>'
        "<ac:plain-text-body><![CDATA[make seed && echo <ok>]]></ac:plain-text-body></ac:structured-macro>"
        "<table><tbody><tr><th>A</th><th>B</th></tr><tr><td><p>1</p></td><td>x | y</td></tr></tbody></table>"
        '<ac:structured-macro ac:name="info"><ac:rich-text-body><p>Note &amp; more&nbsp;text</p>'
        "</ac:rich-text-body></ac:structured-macro>"
    )
    assert markdown(storage) == (
        "# Title\n\nText with **bold**, *it* and `make seed`.\nNext line.\n\n- one\n  - nested\n- two\n\n"
        "1. first\n2. second\n\n[a link](https://example.com/x) and Other page\n\n"
        "```bash\nmake seed && echo <ok>\n```\n\n| A | B |\n|---|---|\n| 1 | x \\| y |\n\nNote & more text\n"
    )


def test_jira_closed_epic_and_open_task():
    sources = registry(CLOUD)
    epic = sources.check(EPIC)
    assert epic.message == 'Jira epic WHL-42 "Определение сессии для метрики конверсии" (Done)'
    assert epic.last_modified == at("2026-10-16T05:12:00Z")  # fields.updated
    assert (epic.signal.subject, epic.signal.verb, epic.signal.at) == ("epic WHL-42", "closed",
                                                                        at("2026-10-14T14:30:00Z"))
    task = sources.check("jira://WHL-57")
    assert task.status == "ok" and task.signal is None  # open: no trigger, however often it is updated
    jira = sources.find(EPIC)
    text = jira.changes_since(EPIC, at("2026-10-01T00:00:00Z"))
    assert "- 2026-10-14 Анна (PM): status: In Progress -> Done" in text and "To Do" not in text


# --- The trust map, okf stale and okf fix --draft through the registry ---


def metric_bundle(make_bundle, verified="2026-09-01T15:00:00Z", generated=None, **extra):
    changes = {"type": "Metric", "verified": [{"by": "human:pm_anna", "at": verified}],
               "sources": [{"id": "page", "resource": PAGE}, {"id": "epic", "resource": EPIC},
                           {"id": "dash", "resource": "https://metabase.wheelo.example/dashboard/12"}],
               "generated": generated or {"by": "human:pm_anna", "at": verified}, **extra}
    return make_bundle({"index.md": "[m](metric.md)\n", "metric.md": doc(meta(**changes))})


def test_closed_epic_asks_for_a_recheck(make_bundle):
    root = metric_bundle(make_bundle)
    [unit] = build_map(root, History(None, NOW), now=NOW, sources=registry(CLOUD)).units
    assert (unit.level, unit.reason) == ("recheck", "recheck:closed")
    assert unit.message == "epic WHL-42 closed 2026-10-14, last verified 2026-09-01 by human:pm_anna"


def test_changed_page_asks_for_a_recheck(make_bundle):
    root = make_bundle({"index.md": "[m](metric.md)\n", "metric.md": doc(meta(**{
        "verified": [{"by": "human:maria", "at": "2026-09-01T00:00:00Z"}],
        "generated": {"by": "human:maria", "at": "2026-09-01T00:00:00Z"},
        "sources": [{"resource": "confluence://131074"}]}))})
    [unit] = build_map(root, History(None, NOW), now=NOW, sources=registry(CLOUD)).units
    assert (unit.level, unit.reason) == ("recheck", "recheck:source-changed")
    assert unit.message.startswith('Confluence page "Тарифы и биллинг" (v3) changed 2026-10-03, last verified')


def test_verified_after_the_epic_closed_is_current(make_bundle):
    root = metric_bundle(make_bundle, verified="2026-10-15T00:00:00Z")
    [unit] = build_map(root, History(None, NOW), now=NOW, sources=registry(CLOUD)).units
    assert unit.level == "human-verified" and unit.message.endswith("sources unchanged since")


def test_without_settings_the_level_does_not_change(make_bundle):
    root = metric_bundle(make_bundle)
    [unit] = build_map(root, History(None, NOW), now=NOW, sources=registry({})).units
    assert unit.level == "human-verified"
    assert unit.message.endswith(f"; {PAGE}: unknown, connector not configured: set OKF_CONFLUENCE_URL (and 1 more)")


def test_stale_reports_remote_changes(make_bundle):
    root = metric_bundle(make_bundle)
    issues = find_stale(Bundle.load(root), [], root, NOW, registry(CLOUD))
    assert [(i.level, i.message) for i in issues] == [
        (WARNING, f"Source {EPIC}: epic WHL-42 closed 2026-10-14, after it was last verified; document may be outdated, "
                  "ask human:pm_anna to review it")]
    issues = find_stale(Bundle.load(root), [], root, NOW, registry({}))
    assert {i.level for i in issues} == {INFO} and len(issues) == 2


def test_fix_draft_gets_the_jira_changelog(make_bundle):
    from test_fix import FakeModel

    from okf.fix import plan_drafts, plan_fixes

    root = metric_bundle(make_bundle)
    sources = registry(CLOUD)
    history = History(None, NOW)
    trust_map = build_map(root, history, now=NOW, sources=sources)
    plan = plan_fixes(root, history, trust_map)
    model = FakeModel({"section": "# Title\n\nSessions end after 30 minutes.\n", "summary": "epic closed",
                       "changed": True})
    plan_drafts(plan, trust_map, history, model, sources=sources)
    [draft] = plan.drafts
    _, prompt, unit = model.prompts[0]
    assert unit == "metric.md" and draft.rejected is None
    assert "status: In Progress -> Done" in prompt and 'Jira epic WHL-42 "Определение сессии' in prompt


# --- okf import confluence ---


def test_import_writes_valid_okf_documents(tmp_path):
    out = tmp_path / "knowledge"
    source = registry(CLOUD).find(PAGE)
    done = import_confluence(source, out, "WHL", [], None, 200, NOW)
    assert [(d.path.name, d.action) for d in done] == [("metriki_produkta.md", "new"), ("tarify_i_billing.md", "new")]
    bundle = Bundle.load(out)
    assert not [i for i in validate_bundle(bundle, get_profile(False)) if i.level == ERROR]
    text = (out / "metriki_produkta.md").read_text(encoding="utf-8")
    assert "type: Guide\ntitle: Метрики продукта\n" in text and "status: draft\n" in text
    assert "generated: { by: process:okf-import, at: 2026-10-22T12:00:00Z }" in text
    assert f"    resource: {PAGE}\n" in text and "    last_modified: 2026-08-28T12:00:00Z\n" in text
    assert "verified" not in text
    assert "## Конверсия в поездку" in text and "```sql" in text
    [unit, _] = build_map(out, History(None, NOW), now=NOW, sources=registry(CLOUD)).units
    assert unit.level == "unverified" and unit.message == "edited by process:okf-import on 2026-10-22; not verified"


def test_reimport_keeps_unchanged_pages_and_never_overwrites_a_human_document(tmp_path):
    out = tmp_path / "knowledge"
    out.mkdir()
    human = doc(meta(sources=[{"resource": PAGE}]))
    (out / "metriki_produkta.md").write_text(human, encoding="utf-8")
    source = registry(CLOUD).find(PAGE)
    [first] = import_confluence(source, out, None, ["131073"], "Metric", 200, NOW)
    assert first.path.name == "metriki_produkta_131073.md" and first.action == "new"
    assert (out / "metriki_produkta.md").read_text(encoding="utf-8") == human
    assert "type: Metric" in first.path.read_text(encoding="utf-8")
    [again] = import_confluence(registry(CLOUD).find(PAGE), out, None, ["131073"], None, 200, NOW)
    assert (again.path, again.action) == (first.path, "unchanged")


def test_cli_import_without_settings(capsys, tmp_path, monkeypatch):
    for name in CLOUD:
        monkeypatch.delenv(name, raising=False)
    assert main(["import", "confluence", "--space", "WHL", "--out", str(tmp_path / "k")]) == 2
    assert "connector not configured: set OKF_CONFLUENCE_URL" in capsys.readouterr().err


def test_cli_sources_and_import_from_fixtures(capsys, tmp_path, monkeypatch):
    for name, value in CLOUD.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(REPO_ROOT)
    assert main(["sources", "examples/demo"]) == 0
    out, err = capsys.readouterr()
    assert "okf sources: jira: configured (https://wheelo.atlassian.net)" in err
    assert f"[OK] examples/demo/knowledge/ride_conversion_metric.md: jira: {EPIC}: ok, Jira epic WHL-42" in out
    assert "; epic WHL-42 closed 2026-10-14" in out
    assert main(["import", "confluence", "--space", "WHL", "--out", str(tmp_path / "k"), "--now", "2026-10-22"]) == 0
    assert "2 pages from space WHL, 2 written" in capsys.readouterr().err


# --- HTTP: Server/DC, credentials, errors, retries (a local mock server) ---


class Mock:
    """A local HTTP server: path -> list of (status, body, headers) answers, the last one repeats."""

    def __init__(self, routes):
        self.routes, self.seen = routes, []
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                mock.seen.append((self.path, dict(self.headers)))
                answers = mock.routes.get(self.path.split("?")[0], [(404, {}, {})])
                status, body, headers = answers.pop(0) if len(answers) > 1 else answers[0]
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                for key, value in {"Content-Type": "application/json", **headers}.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def mock():
    servers = []

    def start(routes):
        servers.append(Mock(routes))
        return servers[-1]

    yield start
    for server in servers:
        server.close()


SERVER_PAGE = {"id": "4456", "title": "Runbook", "version": {"number": 5, "when": "2026-10-01T10:00:00.000+03:00"},
               "body": {"storage": {"value": "<p>Restart the worker.</p>"}}}


def test_server_dc_page_with_a_personal_access_token(mock):
    server = mock({"/rest/api/content/4456": [(200, SERVER_PAGE, {})]})
    env = {"OKF_CONFLUENCE_URL": server.url, "OKF_ATLASSIAN_PAT": "pat-123"}
    check = registry(env).check(f"{server.url}/pages/viewpage.action?pageId=4456")
    assert check.status == "ok" and check.last_modified == at("2026-10-01T07:00:00Z")
    path, headers = server.seen[0]
    assert path == "/rest/api/content/4456?expand=version,body.storage"
    assert headers["Authorization"] == "Bearer pat-123"


def test_jira_server_uses_rest_api_2_and_basic_auth(mock):
    issue = {"key": "PAY-7", "fields": {"summary": "Refunds", "issuetype": {"name": "Story"},
                                        "status": {"name": "Closed", "statusCategory": {"key": "done"}},
                                        "updated": "2026-10-10T10:00:00.000+0000",
                                        "resolutiondate": "2026-10-09T10:00:00.000+0000"},
             "changelog": {"histories": []}}
    server = mock({"/rest/api/2/issue/PAY-7": [(200, issue, {})]})
    env = {"OKF_JIRA_URL": server.url, "OKF_ATLASSIAN_EMAIL": "bot@wheelo.ru", "OKF_ATLASSIAN_TOKEN": "tok"}
    check = registry(env).check("jira://PAY-7")
    assert check.signal.subject == "story PAY-7" and check.signal.at == at("2026-10-09T10:00:00Z")
    assert server.seen[0][1]["Authorization"].startswith("Basic ")


@pytest.mark.parametrize("status, message", [
    (401, "authentication failed (HTTP 401): check OKF_ATLASSIAN_EMAIL and OKF_ATLASSIAN_TOKEN (Cloud) or "
          "OKF_ATLASSIAN_PAT (Server/DC)"),
    (403, "no access (HTTP 403)"),
    (404, "not found or no access (HTTP 404)"),
])
def test_errors_make_the_resource_unknown_and_never_show_the_token(mock, status, message):
    server = mock({"/rest/api/content/4456": [(status, {"message": "nope"}, {})]})
    env = {"OKF_CONFLUENCE_URL": server.url, "OKF_ATLASSIAN_PAT": "very-secret-token"}
    check = registry(env).check("confluence://4456")
    assert (check.status, check.message) == ("unknown", f"Confluence page 4456: {message}")
    assert "very-secret-token" not in check.message


def test_429_is_retried_with_backoff(mock):
    server = mock({"/rest/api/content/4456": [(429, {}, {"Retry-After": "2"}), (429, {}, {}), (200, SERVER_PAGE, {})]})
    pauses = []
    env = {"OKF_CONFLUENCE_URL": server.url}
    check = registry(env, http=Http(env, sleep=pauses.append)).check("confluence://4456")
    assert check.status == "ok" and pauses == [2.0, 2.0] and len(server.seen) == 3


def test_429_that_does_not_end_gives_up(mock):
    server = mock({"/rest/api/content/4456": [(429, {}, {})]})
    pauses = []
    env = {"OKF_CONFLUENCE_URL": server.url}
    check = registry(env, http=Http(env, sleep=pauses.append)).check("confluence://4456")
    assert check.message == "Confluence page 4456: rate limited (HTTP 429), gave up after 4 tries"
    assert pauses == [1.0, 2.0, 4.0]


def test_an_unreachable_host_is_unknown_and_asked_only_once(mock):
    server = mock({})
    url = server.url
    server.close()
    env = {"OKF_CONFLUENCE_URL": url, "OKF_SOURCES_TIMEOUT": "2"}
    http = Http(env)
    sources = registry(env, http=http)
    first, second = sources.check("confluence://1"), sources.check("confluence://2")
    why = first.message.split(": ", 1)[1]  # Windows may time out on a closed port instead of refusing
    assert first.status == second.status == "unknown" and why in ("127.0.0.1 cannot connect", "127.0.0.1 timed out")
    assert http.requests == 2 and second.message == f"Confluence page 2: {why}"


def test_fixture_status_and_missing_fixture(tmp_path):
    (tmp_path / "wiki/api/v2/pages").mkdir(parents=True)
    (tmp_path / "wiki/api/v2/pages/1.json").write_text('{"_status": 403}', encoding="utf-8")
    env = {"OKF_SOURCES_FIXTURES": str(tmp_path), "OKF_CONFLUENCE_URL": "https://x.atlassian.net"}
    sources = registry(env)
    assert sources.check("confluence://1").message == "Confluence page 1: no access (HTTP 403)"
    assert "no fixture for GET /wiki/api/v2/pages/2" in sources.check("confluence://2").message


def test_a_new_connector_is_one_class_and_one_line(make_bundle, monkeypatch, tmp_path):
    """The example from the README section "Как добавить коннектор"."""
    import okf.sources
    from okf.sources.base import Source, not_configured, parse_time

    class MyWikiSource(Source):
        name = "mywiki"
        settings = "OKF_MYWIKI_URL"

        def matches(self, resource):
            return resource.startswith("wiki://")

        def unconfigured(self):
            return None if self.env.get("OKF_MYWIKI_URL") else not_configured(self.settings)

        def last_modified(self, resource):
            page = self.http.get_json(f"{self.env['OKF_MYWIKI_URL']}/api/pages/{resource[7:]}")
            return parse_time(page.get("updated_at"))

        def changes_since(self, resource, since):
            return None

        def describe(self, resource):
            return f"wiki page {resource[7:]}"

    monkeypatch.setattr(okf.sources, "CONNECTORS", [*okf.sources.CONNECTORS, MyWikiSource])
    (tmp_path / "api/pages").mkdir(parents=True)
    (tmp_path / "api/pages/7.json").write_text('{"updated_at": "2026-10-10T10:00:00Z"}', encoding="utf-8")
    root = make_bundle({"index.md": "[m](m.md)\n", "m.md": doc(meta(**{
        "verified": [{"by": "human:a", "at": "2026-09-01T00:00:00Z"}],
        "generated": {"by": "human:a", "at": "2026-09-01T00:00:00Z"}, "sources": [{"resource": "wiki://7"}]}))})
    assert registry({}).check("wiki://7").message == "connector not configured: set OKF_MYWIKI_URL"
    env = {"OKF_MYWIKI_URL": "https://wiki.example", "OKF_SOURCES_FIXTURES": str(tmp_path)}
    [unit] = build_map(root, History(None, NOW), now=NOW, sources=registry(env)).units
    assert unit.message == "wiki page 7 changed 2026-10-10, last verified 2026-09-01 by human:a"
