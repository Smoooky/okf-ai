"""`okf trust --html` and `okf view`: self-contained pages in one design, no external requests."""

import re
import shutil
import subprocess
from datetime import datetime, timezone

import pytest

from conftest import REPO_ROOT, doc, meta
from okf.bundle import Bundle
from okf.cli import main
from okf.git import History, web_base
from okf.sources import registry
from okf.trust import build_map
from okf.view import build_site, date_ru, find_bundles, freshness, markdown_html, plural, trust_html

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
DEMO = REPO_ROOT / "examples" / "demo"


def no_external(page: str) -> None:
    """Nothing the page loads comes from the network: no external scripts, styles, images or fonts."""
    assert not re.search(r'<(script|link|img|iframe)[^>]+(src|href)="https?://', page)
    assert "@import" not in page and "url(http" not in page and "fonts.googleapis" not in page


def test_markdown_html():
    text = ("# Title\n\nText with **bold**, *it*, `a<b>` and [a link](other.md#x).\n\n- one\n  - nested\n- two\n\n"
            "1. first\n2. second\n\n```bash\nmake <seed>\n```\n\n| A | B |\n|---|---|\n| 1 | x \\| y |\n\n"
            "> quoted\n\nNote.[^n]\n\n[^n]: The note.\n\n[bad](javascript:alert(1))\n")
    html = markdown_html(text, lambda target: target.replace(".md", ".html"), lambda note: '<a href="s">src</a>')
    assert '<h1 id="title">Title</h1>' in html
    assert "<strong>bold</strong>, <em>it</em>, <code>a&lt;b&gt;</code>" in html
    assert '<a href="other.html#x">a link</a>' in html
    assert "<ul><li>one<ul><li>nested</li></ul></li><li>two</li></ul>" in html
    assert "<ol><li>first</li><li>second</li></ol>" in html
    assert '<pre><code class="language-bash">make &lt;seed&gt;</code></pre>' in html
    assert "<td>x | y</td>" in html and "<blockquote><p>quoted</p></blockquote>" in html
    assert '<sup id="fnref-n"><a href="#fn-n">1</a></sup>' in html
    assert '<li id="fn-n">The note. — <a href="s">src</a> <a href="#fnref-n"' in html
    assert "javascript:" not in html and "bad" in html


def test_russian_words_and_dates():
    assert [plural(n, ("раздел", "раздела", "разделов")) for n in (1, 2, 5, 11, 21, 22, 112)] == \
        ["раздел", "раздела", "разделов", "разделов", "раздел", "раздела", "разделов"]
    assert date_ru(NOW) == "22 окт 2026"


def test_freshness_in_days(make_bundle):
    root = make_bundle({"a.md": doc(meta(stale_after="2026-11-01T00:00:00Z")),
                        "b.md": doc(meta(stale_after="2026-10-01T00:00:00Z"))})
    bundle = Bundle.load(root)
    by_name = {d.name: d for d in bundle.documents}
    assert freshness(by_name["a.md"], NOW) == ("через 9 дней", "fresh-soon")
    assert freshness(by_name["b.md"], NOW) == ("просрочен с 1 окт 2026", "fresh-late")


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_trust_html_is_one_offline_page(tmp_path):
    shutil.copytree(DEMO, tmp_path / "demo")
    trust_map = build_map(tmp_path / "demo", History(None, NOW), now=NOW, sources=registry({}))
    page = trust_html(trust_map, tmp_path / "demo", NOW)
    no_external(page)
    assert page.startswith("<!doctype html>") and "<style>" in page and "<script>" in page
    assert len(page.encode("utf-8")) < 150_000
    assert 'prefers-color-scheme: dark' in page and 'name="viewport"' in page and 'id="theme"' in page
    assert "localStorage" in page and "try{" in page  # the remembered theme, safe without storage
    assert 'class="brand-name">okf-ai' in page and "каким знаниям агентов можно верить сейчас" in page
    for level, word, icon in (("broken", "сломано", "✕"), ("recheck", "перепроверить", "!"),
                              ("verified", "подтверждено", "✓"), ("unverified", "не подтверждено", "○")):
        assert f'data-filter="{level}" data-solo aria-pressed="true"' in page  # tiles filter
        assert f'<span class="ico" aria-hidden="true">{icon}</span>{word}' in page  # icon and word, not color only
    assert re.search(r'<div class="bar" role="img" aria-label="сломано: \d+, перепроверить', page)
    assert "Можно доверять <b>" in page and "С чего начать" in page and 'id="empty" hidden' in page
    start = page.index("С чего начать")
    assert page.index('class="card k-broken"', start) < page.index("Остальные разделы")
    assert "Ссылается на то, чего нет: <code>&quot;./scripts/seed_db.sh&quot; does not exist</code>" in page
    assert 'data-copy="okf fix"' in page and 'aria-label="Скопировать команду okf fix"' in page
    assert '<details class="group" open data-group="AGENTS.md">' in page
    assert "Сгенерировано <code>okf trust</code>" in page and "OKF v0.2</a>" in page


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_timeline_shows_the_check_and_the_later_change(tmp_path):
    from test_trust import AGENTS, Repo, code_repo

    repo = Repo(tmp_path / "repo")
    code_repo(repo).write({"AGENTS.md": AGENTS}).commit("2026-09-01T10:00:00Z")
    repo.verify("AGENTS.md#Auth", by="human:ivan")
    repo.commit("2026-09-05T11:00:00Z")
    repo.write({"src/auth.py": "TTL = 7\n"}).commit("2026-10-20T10:00:00Z")
    page = trust_html(repo.map(), repo.root, NOW, git_root=repo.root)
    assert '<div class="pt "><b>проверено 5 сен 2026</b><span>human:ivan</span></div>' in page
    assert '<span class="gap">+45 дней</span>' in page and "<b>код изменился 20 окт 2026</b>" in page
    assert 'data-copy="okf verify &quot;AGENTS.md#Auth&quot;"' in page
    assert "ветка <code>main</code>" in page


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_cli_trust_html_line_links_and_since(tmp_path, capsys, monkeypatch):
    repo = tmp_path / "demo"
    shutil.copytree(DEMO, repo)

    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", *args], cwd=repo, check=True,
                       capture_output=True)

    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "x")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/wheelo")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    report = tmp_path / "report.html"
    assert main(["trust", str(repo), "--html", str(report)]) == 0
    assert "okf trust: wrote" in capsys.readouterr().err
    page = report.read_text(encoding="utf-8")
    assert 'href="https://github.com/acme/wheelo/blob/abc123/AGENTS.md#L7"' in page
    git("checkout", "-q", "-b", "pr")
    (repo / "src" / "billing.py").write_text("FEE = 1\n", encoding="utf-8")
    git("commit", "-q", "-am", "y")
    assert main(["trust", str(repo), "--since", "main", "--html", str(report)]) == 0
    page = report.read_text(encoding="utf-8")
    assert "Изменение относительно <code>main</code>:</b> задето 4 раздела" in page


def test_web_base_from_the_origin_remote(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "x"],
                   cwd=tmp_path, check=True)
    assert web_base(tmp_path, env={}) is None
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:Smoooky/okf-ai.git"], cwd=tmp_path, check=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    assert web_base(tmp_path, env={}) == f"https://github.com/Smoooky/okf-ai/blob/{sha}"


def site(tmp_path):
    bundle = Bundle.load(DEMO / "knowledge")
    trust_map = build_map(DEMO, History(None, NOW), bundles=[bundle.root], now=NOW, sources=registry({}))
    units = {u.path: u for u in trust_map.units if u.kind == "knowledge"}
    return build_site(bundle, tmp_path / "site", units, NOW)


def test_site_home(tmp_path):
    pages = site(tmp_path)
    index = pages[0].read_text(encoding="utf-8")
    no_external(index)
    assert "<h1>База знаний Wheelo</h1>" in index and 'id="nav"' in index and 'id="nav-q"' in index
    assert '<div class="nav-group"><h4>Архитектура и сервисы</h4>' in index  # the sidebar follows index.md
    assert 'aria-controls="nav" aria-expanded="false"' in index  # the drawer on phones
    assert '<div class="bar" role="img"' in index and 'data-filter="recheck" data-solo' in index
    assert re.search(r'<tr data-level="\w+" data-tags="api rides"', index)
    assert 'data-tag="billing" aria-pressed="false"' in index
    assert "через 18 дней" in index and 'href="graph.html"' in index


def test_site_document_page(tmp_path):
    site(tmp_path)
    page = (tmp_path / "site" / "ride_conversion_metric.html").read_text(encoding="utf-8")
    no_external(page)
    assert '<nav class="crumbs" aria-label="Путь"><a href="index.html">База знаний Wheelo</a>' in page
    assert '<span class="badge">Metric</span><span class="badge">draft</span>' in page
    assert 'aria-label="Паспорт знания"' in page and "<dt>Источники</dt>" in page and "<dt>Свежесть</dt>" in page
    assert '<a href="https://wheelo.atlassian.net/browse/WHL-42">Эпик: определение сессии</a>' in page
    assert '<a href="api_start_ride.html">POST /rides</a>' in page
    assert 'aria-current="page"' in page  # the open document is marked in the sidebar
    footnote = re.search(r'<li id="fn-definition">.*?</li>', page).group(0)
    assert 'href="https://wheelo.atlassian.net/browse/WHL-42"' in footnote  # [^definition] cites its source
    auth = (tmp_path / "site" / "auth_flow.html").read_text(encoding="utf-8")
    assert "Документ надо перепроверить" not in auth  # without git history nothing is newer than the check
    assert (tmp_path / "site" / "log.html").exists() and (tmp_path / "site" / "AGENTS.html").exists()


def test_site_graph(tmp_path):
    site(tmp_path)
    page = (tmp_path / "site" / "graph.html").read_text(encoding="utf-8")
    no_external(page)
    assert page.count('<a class="node n-') == 9 and 'id="graph-data"' in page and "Fruchterman" in page
    assert 'id="zoom-in"' in page and 'aria-label="Легенда"' in page
    assert re.search(r'<line class="edge" data-a="\d+" data-b="\d+"', page)


def test_find_bundles(tmp_path):
    (tmp_path / "kb").mkdir()
    (tmp_path / "kb" / "index.md").write_text('---\nokf_version: "0.2"\n---\n# KB\n', encoding="utf-8")
    (tmp_path / "kb" / "a.md").write_text(doc(meta()), encoding="utf-8")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "index.md").write_text("# not a bundle\n", encoding="utf-8")
    assert find_bundles(tmp_path) == [(tmp_path / "kb").resolve()]
    assert find_bundles(tmp_path / "kb") == [(tmp_path / "kb").resolve()]


def test_cli_view(tmp_path, capsys):
    assert main(["view", str(DEMO), "--out", str(tmp_path / "site"), "--now", "2026-10-22"]) == 0
    assert "knowledge: 9 documents" in capsys.readouterr().err
    assert (tmp_path / "site" / "index.html").exists() and (tmp_path / "site" / "graph.html").exists()
    assert main(["view", str(tmp_path / "site"), "--out", str(tmp_path / "x")]) == 2


def test_site_banner_for_a_document_to_recheck(tmp_path):
    bundle = Bundle.load(DEMO / "knowledge")
    trust_map = build_map(DEMO, History(None, NOW), bundles=[bundle.root], now=NOW, sources=registry({}))
    units = {u.path: u for u in trust_map.units if u.kind == "knowledge"}
    auth = next(u for u in units.values() if u.path.name == "auth_flow.md")
    auth.level, auth.reason = "recheck", "recheck:code-changed"
    auth.changed = [("src/auth.py", datetime(2026, 10, 20, tzinfo=timezone.utc))]
    build_site(bundle, tmp_path / "site", units, NOW)
    page = (tmp_path / "site" / "auth_flow.html").read_text(encoding="utf-8")
    assert '<div class="banner b-recheck" role="note"><span class="ico" aria-hidden="true">!</span>' in page
    assert "<b>Документ надо перепроверить.</b> Код изменился после подтверждения: <code>src/auth.py</code>, 20 окт 2026" in page
    index = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert '<span class="dot d-recheck" aria-hidden="true"></span>Поток аутентификации' in index
