"""`okf trust --html` and `okf view`: self-contained pages, no external requests."""

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
from okf.view import build_site, find_bundles, markdown_html, trust_html

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
DEMO = REPO_ROOT / "examples" / "demo"


def no_external(page: str) -> None:
    """Nothing the page loads comes from the network: no external scripts, styles, images or fonts."""
    assert not re.search(r'<(script|link|img|iframe)[^>]+(src|href)="https?://', page)
    assert "@import" not in page and "url(http" not in page


def test_markdown_html():
    text = ("# Title\n\nText with **bold**, *it*, `a<b>` and [a link](other.md#x).\n\n- one\n  - nested\n- two\n\n"
            "1. first\n2. second\n\n```bash\nmake <seed>\n```\n\n| A | B |\n|---|---|\n| 1 | x \\| y |\n\n"
            "> quoted\n\nNote.[^n]\n\n[^n]: The note.\n\n[bad](javascript:alert(1))\n")
    html = markdown_html(text, lambda target: target.replace(".md", ".html"))
    assert '<h1 id="title">Title</h1>' in html
    assert "<strong>bold</strong>, <em>it</em>, <code>a&lt;b&gt;</code>" in html
    assert '<a href="other.html#x">a link</a>' in html
    assert "<ul><li>one<ul><li>nested</li></ul></li><li>two</li></ul>" in html
    assert "<ol><li>first</li><li>second</li></ol>" in html
    assert '<pre><code class="language-bash">make &lt;seed&gt;</code></pre>' in html
    assert "<td>x | y</td>" in html and "<blockquote><p>quoted</p></blockquote>" in html
    assert '<sup><a href="#fn-n">n</a></sup>' in html and '<li id="fn-n">The note.</li>' in html
    assert "javascript:" not in html and "bad" in html


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_trust_html_is_one_offline_page(tmp_path):
    shutil.copytree(DEMO, tmp_path / "demo")
    trust_map = build_map(tmp_path / "demo", History(None, NOW), now=NOW, sources=registry({}))
    page = trust_html(trust_map, tmp_path / "demo", NOW)
    no_external(page)
    assert page.startswith("<!doctype html>") and "<style>" in page and "<script>" in page
    assert "prefers-color-scheme:dark" in page and 'name="viewport"' in page
    for level in ("broken", "recheck", "verified", "unverified"):
        assert f'data-filter="{level}"' in page
    assert 'id="q" type="search"' in page
    assert re.search(r'class="unit broken" data-level="broken"><h3>AGENTS.md#Команды', page)
    assert "./scripts/seed_db.sh" in page and "<dt>where</dt><dd><code>AGENTS.md:7</code>" in page
    assert "human:maria_backend, 2026-10-05" in page  # who verified, and when


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_cli_trust_html_and_line_links(tmp_path, capsys, monkeypatch):
    shutil.copytree(DEMO, tmp_path / "demo")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/wheelo")
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path / "demo", check=True)
    report = tmp_path / "report.html"
    assert main(["trust", str(tmp_path / "demo"), "--html", str(report)]) == 0
    assert "okf trust: wrote" in capsys.readouterr().err
    page = report.read_text(encoding="utf-8")
    assert 'href="https://github.com/acme/wheelo/blob/abc123/AGENTS.md#L7"' in page


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


def test_site_of_the_demo_knowledge(tmp_path):
    bundle = Bundle.load(DEMO / "knowledge")
    trust_map = build_map(DEMO, History(None, NOW), bundles=[bundle.root], now=NOW, sources=registry({}))
    units = {u.path: u for u in trust_map.units if u.kind == "knowledge"}
    pages = build_site(bundle, tmp_path / "site", units, NOW)
    index = pages[0].read_text(encoding="utf-8")
    no_external(index)
    assert "<h1>База знаний Wheelo</h1>" in index and "<h2>By tag</h2>" in index
    assert '<a href="auth_flow.html">Поток аутентификации</a>' in index  # index.md links now point to pages
    assert re.search(r'<svg viewBox=[^>]+aria-label="Links between 9 documents, \d+ links">', index)
    assert index.count('<circle class="node') == 9
    page = (tmp_path / "site" / "ride_conversion_metric.html").read_text(encoding="utf-8")
    no_external(page)
    assert "<dt>type</dt><dd>Metric</dd>" in page and "<dt>status</dt><dd>draft</dd>" in page
    assert "stale_after" in page and "https://wheelo.atlassian.net/browse/WHL-42" in page
    assert '<a href="api_start_ride.html">POST /rides</a>' in page and "badge verified" in page
    assert (tmp_path / "site" / "log.html").exists()


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
    assert (tmp_path / "site" / "index.html").exists() and (tmp_path / "site" / "auth_flow.html").exists()
    assert main(["view", str(tmp_path / "site"), "--out", str(tmp_path / "x")]) == 2
