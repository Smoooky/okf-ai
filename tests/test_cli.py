"""CLI behaviour: exit codes, output format, the example bundles."""

import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import OFFICIAL_BUNDLE, REPO_ROOT, doc, meta
from okf.cli import main
from okf.report import ERROR, Issue, format_github

LINE_FORMAT = re.compile(r"^\[(ERROR|WARNING|INFO)\] [^:]+: [\w.\[\]]+: .+$")


def run(capsys, *argv):
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out.splitlines(), err


def found(out):
    return {tuple(line.split(": ")[:2]) for line in out}


def test_validate_exit_0_when_clean(make_bundle, capsys):
    root = make_bundle({"index.md": "[a](a.md)", "a.md": doc(meta())})
    code, out, err = run(capsys, "validate", str(root))
    assert (code, out) == (0, [])
    assert "okf validate (okf):" in err and "0 errors, 0 warnings" in err


def test_validate_exit_0_with_only_warnings(make_bundle, capsys):
    root = make_bundle({"index.md": "[a](a.md) [x](missing.md)", "a.md": doc(meta()), "orphan.md": doc(meta())})
    code, out, err = run(capsys, "validate", str(root), "--strict")
    assert code == 0
    assert len(out) == 2 and all(line.startswith("[WARNING] ") for line in out)
    assert "okf validate (strict):" in err


def test_validate_exit_1_on_any_error(make_bundle, capsys):
    root = make_bundle({"index.md": "[a](a.md)", "a.md": doc(meta(status="published"))})
    code, out, _ = run(capsys, "validate", str(root))
    assert code == 1
    assert out[0].startswith("[ERROR] ")
    assert out[0].endswith('a.md: status: Value "published" must be one of draft, stable, deprecated')


def test_validate_paths_are_relative_to_working_directory(make_bundle, capsys, monkeypatch):
    root = make_bundle({"index.md": "[a](docs/a.md)", "docs/a.md": doc(meta(type=""))})
    monkeypatch.chdir(root.parent)
    _, out, _ = run(capsys, "validate", "bundle")
    assert out == ["[ERROR] bundle/docs/a.md: type: Field must not be empty"]


def test_missing_bundle_directory_exits_2(tmp_path, capsys):
    code, _, err = run(capsys, "validate", str(tmp_path / "nope"))
    assert code == 2 and "not found" in err


def test_github_format_escapes_workflow_commands():
    issue = Issue(ERROR, Path("kb/a,b.md"), "stale_after", "100% wrong\nreally", 7)
    line = format_github(issue)
    assert line.startswith("::error file=")
    assert "a%2Cb.md,line=7,title=okf stale_after::100%25 wrong%0Areally" in line


@pytest.mark.parametrize("strict", [[], ["--strict"]])
def test_demo_bundle_is_clean(capsys, monkeypatch, strict):
    monkeypatch.chdir(REPO_ROOT)
    code, out, _ = run(capsys, "validate", "examples/demo/knowledge", *strict)
    assert (code, out) == (0, [])


@pytest.mark.parametrize("strict", [[], ["--strict"]])
def test_official_bundle_has_no_errors(capsys, strict):
    code, out, _ = run(capsys, "validate", str(OFFICIAL_BUNDLE), *strict)
    if not strict:
        assert (code, out) == (0, [])
    else:  # the official example is not written to okf-ai team rules
        assert all(LINE_FORMAT.match(line) for line in out)


BROKEN_OKF = {
    ("[WARNING] examples/broken/bad_fields.md", "tags"),
    ("[ERROR] examples/broken/bad_fields.md", "sources[0]"),
    ("[ERROR] examples/broken/bad_fields.md", "sources[1].resource"),
    ("[ERROR] examples/broken/bad_fields.md", "generated.by"),
    ("[ERROR] examples/broken/bad_fields.md", "verified[0].by"),
    ("[ERROR] examples/broken/bad_fields.md", "verified[0].at"),
    ("[ERROR] examples/broken/bad_fields.md", "status"),
    ("[ERROR] examples/broken/bad_fields.md", "stale_after"),
    ("[WARNING] examples/broken/broken_link.md", "link"),
    ("[ERROR] examples/broken/index.md", "frontmatter"),
    ("[WARNING] examples/broken/log.md", "log"),
    ("[ERROR] examples/broken/missing_type.md", "type"),
    ("[ERROR] examples/broken/no_front_matter.md", "frontmatter"),
    ("[ERROR] examples/broken/yaml_list.md", "frontmatter"),
}

BROKEN_STRICT_ONLY = {
    ("[ERROR] examples/broken/agent_unreviewed_stable.md", "verified"),
    ("[ERROR] examples/broken/bad_fields.md", "tags"),
    ("[ERROR] examples/broken/legacy_team_format.md", "sources"),
    ("[ERROR] examples/broken/legacy_team_format.md", "verified"),
    ("[ERROR] examples/broken/legacy_team_format.md", "stale_after"),
    ("[ERROR] examples/broken/log.md", "frontmatter"),
    ("[ERROR] examples/broken/no_sources.md", "sources"),
    ("[WARNING] examples/broken/orphan.md", "link"),
    ("[ERROR] examples/broken/stale_before_review.md", "stale_after"),
    ("[WARNING] examples/broken/wrong_type.md", "type"),
}


def test_broken_bundle_okf_rules(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, _ = run(capsys, "validate", "examples/broken")
    assert code == 1
    assert all(LINE_FORMAT.match(line) for line in out), out
    assert found(out) == BROKEN_OKF


def test_broken_bundle_strict_rules(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, _ = run(capsys, "validate", "examples/broken", "--strict")
    assert code == 1
    assert all(LINE_FORMAT.match(line) for line in out), out
    expected = (BROKEN_OKF - {("[WARNING] examples/broken/bad_fields.md", "tags")}) | BROKEN_STRICT_ONLY
    assert found(out) == expected


def test_demo_agents_md_is_up_to_date(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, _ = run(capsys, "agents", "examples/demo/knowledge", "--check", "--now", "2026-10-22")
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
    assert code == 0 and out[0] == "---"
    assert "# AGENTS.md" in out
    assert not (root / "AGENTS.md").exists()


def test_generated_agents_md_validates_as_okf_concept(make_bundle, capsys):
    root = make_bundle({"index.md": "[a](a.md)", "a.md": doc(meta())})
    run(capsys, "agents", str(root))
    (root / "router.md").write_text((root / "AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8")
    code, out, _ = run(capsys, "validate", str(root))
    assert (code, out) == (0, [])


def test_stale_with_changed_files(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, err = run(
        capsys, "stale", "examples/demo/knowledge", "--changed", "examples/demo/src/auth.py",
        "--repo-root", ".", "--now", "2026-10-22",
    )
    assert code == 0
    assert out == [
        "[WARNING] examples/demo/knowledge/auth_flow.md: sources: Source ../src/auth.py changed (examples/demo/src/auth.py); "
        "document may be outdated, ask human:teamlead_ivan to review it"
    ]
    assert "1 documents may be outdated" in err


def test_stale_reads_changed_files_from_stdin(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(sys, "stdin", io.StringIO("examples/demo/src/billing.py\n"))
    _, out, _ = run(capsys, "stale", "examples/demo/knowledge", "--changed", "-", "--repo-root", ".", "--now", "2026-10-22")
    assert sorted(line.split(": ")[0] for line in out) == [
        "[WARNING] examples/demo/knowledge/billing_service.md",
        "[WARNING] examples/demo/knowledge/payment_failures_runbook.md",
    ]


def test_stale_marks_expired_documents(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    _, out, _ = run(capsys, "stale", "examples/demo/knowledge", "--repo-root", ".", "--now", "2026-11-10T00:00:00Z")
    assert out == [
        "[WARNING] examples/demo/knowledge/api_start_ride.md: stale_after: 2026-11-10T00:00:00Z has passed "
        "(now 2026-11-10T00:00:00Z); document is stale, ask human:maria_backend to review it"
    ]


def test_bad_now_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["stale", ".", "--now", "tomorrow"])
    assert exc.value.code == 2


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_stale_bad_base_ref_exits_2(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, _, err = run(capsys, "stale", "examples/demo/knowledge", "--base", "no-such-ref-okf")
    assert code == 2 and "git" in err


def test_module_entry_point():
    result = subprocess.run(
        [sys.executable, "-m", "okf", "--version"], capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )
    assert result.returncode == 0 and result.stdout.startswith("okf ")


# --- okf agents-check ---


DEMO_INSTRUCTIONS = [
    '[WARNING] examples/demo/AGENTS.md: command: "./scripts/seed_db.sh" does not exist (line 14)',
    '[WARNING] examples/demo/CLAUDE.md: command: "npm run test:unit": no script "test:unit" in package.json (line 6)',
    "[WARNING] examples/demo/CLAUDE.md: consistency: Instructions for different agents disagree: "
    'AGENTS.md runs "npm test", CLAUDE.md runs "npm run test:unit" (line 6)',
]


def test_agents_check_demo(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, err = run(capsys, "agents-check", "examples/demo")
    assert (code, out) == (0, DEMO_INSTRUCTIONS)
    assert "okf agents-check: 4 instruction files" in err and "0 errors, 3 warnings" in err


def test_agents_check_strict_fails(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    code, out, _ = run(capsys, "agents-check", "examples/demo", "--strict")
    assert code == 1
    assert [line.split(": ")[1] for line in out] == ["command", "command", "consistency"]
    assert out[0].startswith("[ERROR] ") and out[2].startswith("[WARNING] ")


def test_agents_check_with_changed_files(capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    _, out, _ = run(capsys, "agents-check", "examples/demo", "--changed", "examples/demo/src/config.py",
                    "--repo-root", ".")
    assert [line for line in out if line not in DEMO_INSTRUCTIONS] == [
        '[WARNING] examples/demo/AGENTS.md: path: "src/config.py" changed in this change; '
        "the instruction may be outdated (line 22)",
        '[WARNING] examples/demo/CLAUDE.md: path: "src/config.py" changed in this change; '
        "the instruction may be outdated (line 8)",
    ]


def test_agents_check_fixed_instructions_are_clean(make_bundle, capsys):
    demo = REPO_ROOT / "examples" / "demo"
    root = make_bundle({})
    shutil.copytree(demo, root, dirs_exist_ok=True)
    shutil.copy(REPO_ROOT / "examples/demo-pr/AGENTS.fixed.md", root / "AGENTS.md")
    shutil.copy(REPO_ROOT / "examples/demo-pr/CLAUDE.fixed.md", root / "CLAUDE.md")
    (root / "src/config.py").rename(root / "src/settings.py")
    code, out, _ = run(capsys, "agents-check", str(root), "--strict")
    assert (code, out) == (0, [])


def test_agents_check_missing_directory(tmp_path, capsys):
    code, _, err = run(capsys, "agents-check", str(tmp_path / "nope"))
    assert code == 2 and "not found" in err
