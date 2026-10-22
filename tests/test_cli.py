"""CLI behaviour: exit codes, output format, the example bundles."""

import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, doc, meta
from okf.cli import main
from okf.report import ERROR, Issue, format_github

LINE_FORMAT = re.compile(r"^\[(ERROR|WARNING|INFO)\] [^:]+: [\w.\[\]]+: .+$")


def run(capsys, *argv):
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out.splitlines(), err


def test_validate_exit_0_when_clean(make_bundle, capsys):
    root = make_bundle({"index.md": "[a](a.md)", "a.md": doc(meta())})
    code, out, err = run(capsys, "validate", str(root))
    assert (code, out) == (0, [])
    assert "0 errors, 0 warnings" in err


def test_validate_exit_0_with_only_warnings(make_bundle, capsys):
    root = make_bundle({"index.md": "[a](a.md) [x](missing.md)", "a.md": doc(meta()), "orphan.md": doc(meta())})
    code, out, _ = run(capsys, "validate", str(root))
    assert code == 0
    assert len(out) == 2 and all(line.startswith("[WARNING] ") for line in out)


def test_validate_exit_1_on_any_error(make_bundle, capsys):
    root = make_bundle({"index.md": "[a](a.md)", "a.md": doc(meta(type="Endpoint"))})
    code, out, _ = run(capsys, "validate", str(root))
    assert code == 1
    assert out[0].startswith("[ERROR] ")
    assert out[0].endswith('a.md: type: Value "Endpoint" is not in the allowed type dictionary (did you mean "API Endpoint"?)')


def test_validate_paths_are_relative_to_working_directory(make_bundle, capsys, monkeypatch):
    root = make_bundle({"index.md": "[a](docs/a.md)", "docs/a.md": doc(meta(type="Endpoint"))})
    monkeypatch.chdir(root.parent)
    _, out, _ = run(capsys, "validate", "bundle")
    assert out == ['[ERROR] bundle/docs/a.md: type: Value "Endpoint" is not in the allowed type dictionary '
                   '(did you mean "API Endpoint"?)']


def test_missing_bundle_directory_exits_2(tmp_path, capsys):
    code, _, err = run(capsys, "validate", str(tmp_path / "nope"))
    assert code == 2 and "not found" in err


def test_github_format_escapes_workflow_commands():
    issue = Issue(ERROR, Path("kb/a,b.md"), "trust.confidence", "100% wrong\nreally", 7)
    line = format_github(issue)
    assert line.startswith("::error file=")
    assert "a%2Cb.md,line=7,title=okf trust.confidence::100%25 wrong%0Areally" in line


def test_demo_bundle_is_clean(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, _ = run(capsys, "validate", "examples/demo")
    assert (code, out) == (0, [])


def test_broken_bundle_shows_every_rule(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, _ = run(capsys, "validate", "examples/broken")
    assert code == 1
    assert all(LINE_FORMAT.match(line) for line in out), out
    found = {tuple(line.split(": ")[:2]) for line in out}
    prefix = "examples/broken/"
    assert found == {
        (f"[ERROR] {prefix}agent_overconfident.md", "trust.confidence"),
        (f"[ERROR] {prefix}bad_fields.md", "tags"),
        (f"[ERROR] {prefix}bad_fields.md", "trust.confidence"),
        (f"[ERROR] {prefix}bad_fields.md", "trust.verified_by"),
        (f"[ERROR] {prefix}bad_fields.md", "freshness.last_reviewed"),
        (f"[ERROR] {prefix}bad_fields.md", "freshness.stale_after"),
        (f"[WARNING] {prefix}broken_link.md", "link"),
        (f"[ERROR] {prefix}index.md", "frontmatter"),
        (f"[ERROR] {prefix}no_front_matter.md", "frontmatter"),
        (f"[ERROR] {prefix}no_sources.md", "provenance.sources"),
        (f"[WARNING] {prefix}orphan.md", "link"),
        (f"[ERROR] {prefix}stale_before_review.md", "freshness.stale_after"),
        (f"[ERROR] {prefix}wrong_type.md", "type"),
        (f"[ERROR] {prefix}yaml_list.md", "frontmatter"),
    }


def test_demo_agents_md_is_up_to_date(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, err = run(capsys, "agents", "examples/demo", "--check", "--today", "2026-10-22")
    assert code == 0, out


def test_agents_writes_file_and_check_detects_drift(make_bundle, capsys):
    root = make_bundle({"index.md": "[a](a.md)", "a.md": doc(meta())})
    assert run(capsys, "agents", str(root))[0] == 0
    assert "| [a.md](a.md) |" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert run(capsys, "agents", str(root), "--check")[0] == 0
    (root / "b.md").write_text(doc(meta()), encoding="utf-8")
    code, out, _ = run(capsys, "agents", str(root), "--check")
    assert code == 1 and out[0].startswith("[ERROR] ")


def test_agents_to_stdout(make_bundle, capsys):
    root = make_bundle({"a.md": doc(meta())})
    code, out, _ = run(capsys, "agents", str(root), "-o", "-")
    assert code == 0 and out[0] == "# AGENTS.md"
    assert not (root / "AGENTS.md").exists()


def test_stale_with_changed_files(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, err = run(
        capsys, "stale", "examples/demo", "--changed", "examples/demo/src/auth.py",
        "--repo-root", ".", "--today", "2026-10-22",
    )
    assert code == 0
    assert out == [
        "[WARNING] examples/demo/auth_flow.md: provenance.sources: Source git://examples/demo/src/auth.py changed; "
        "document may be outdated, ask teamlead_ivan to review it"
    ]
    assert "1 documents may be outdated" in err


def test_stale_reads_changed_files_from_stdin(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(sys, "stdin", io.StringIO("examples/demo/src/billing.py\n"))
    _, out, _ = run(capsys, "stale", "examples/demo", "--changed", "-", "--repo-root", ".", "--today", "2026-10-22")
    assert sorted(line.split(": ")[0] for line in out) == [
        "[WARNING] examples/demo/billing_service.md",
        "[WARNING] examples/demo/payment_failures_runbook.md",
    ]


def test_stale_marks_expired_documents(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    _, out, _ = run(capsys, "stale", "examples/demo", "--repo-root", ".", "--today", "2026-11-11")
    assert out == [
        "[WARNING] examples/demo/api_start_ride.md: freshness.stale_after: Review date 2026-11-10 has passed "
        "(today is 2026-11-11); document is stale, ask maria_backend to review it"
    ]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_stale_bad_base_ref_exits_2(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, _, err = run(capsys, "stale", "examples/demo", "--base", "no-such-ref-okf")
    assert code == 2 and "git" in err


def test_module_entry_point():
    result = subprocess.run(
        [sys.executable, "-m", "okf", "--version"], capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )
    assert result.returncode == 0 and result.stdout.startswith("okf ")
