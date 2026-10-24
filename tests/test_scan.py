"""`okf scan`: the probe over many repositories (R7) and the labelling sample (R8), on local repositories."""

import csv
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import NOW
from okf import scan as scan_module
from okf.cli import main
from okf.scan import RepoSpec, ScanError, _clone_failure, parse_repos, scan, score

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def make_repo(root: Path, files: dict, when="2026-09-01T10:00:00Z") -> Path:
    root.mkdir(parents=True)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                       capture_output=True, env=env)
    return root


@pytest.fixture
def origins(tmp_path):
    """Three local "GitHub" repositories: findings, clean, no instructions."""
    base = tmp_path / "origins"
    make_repo(base / "acme" / "web", {
        "AGENTS.md": "## Commands\n\n`npm run dev`, `npm run nope`, `./scripts/gone.sh`\n\n## Code\n\n`src/app.ts`\n",
        "CLAUDE.md": "## Claude\n\nUse `npm run dev`.\n",
        "package.json": json.dumps({"scripts": {"dev": "vite"}}), "src/app.ts": "",
    })
    make_repo(base / "acme" / "api", {"AGENTS.md": "## Test\n\nRun `pytest tests/test_api.py`.\n",
                                      "tests/test_api.py": ""})
    make_repo(base / "acme" / "plain", {"README.md": "# Plain\n"})
    return base


def local_clone(origins):
    def clone(spec, directory, timeout):
        source = origins / spec.name
        if not source.exists():
            return "not found, private or renamed"
        subprocess.run(["git", "clone", "-q", str(source), str(directory)], check=True, capture_output=True)
        return None

    return clone


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# --- the list of repositories ---


def test_parse_repos():
    text = """
    # probe list
    acme/web
    https://github.com/acme/api.git
    git@github.com:acme/cli.git
    acme/docs@0a1b2c3   # pinned
    ACME/web            # duplicate
    """
    assert parse_repos(text) == [RepoSpec("acme/web"), RepoSpec("acme/api"), RepoSpec("acme/cli"),
                                 RepoSpec("acme/docs", "0a1b2c3")]
    with pytest.raises(ScanError, match="not a GitHub repository"):
        parse_repos("just words here")


@pytest.mark.parametrize("stderr,reason", [
    ("remote: Repository not found.\nfatal: repository 'x' not found", "not found, private or renamed"),
    ("fatal: could not read Username for 'https://github.com'", "not found, private or renamed"),
    ("error: RPC failed; HTTP 429", "rate limited by GitHub, retry later"),
    ("fatal: unable to access: Could not resolve host", "clone failed: fatal: unable to access: Could not resolve host"),
])
def test_clone_failures_have_reasons(stderr, reason):
    assert _clone_failure(stderr) == reason


# --- the probe ---


def test_scan_writes_the_report(origins, tmp_path):
    out, work = tmp_path / "report", tmp_path / "work"
    work.mkdir()
    specs = parse_repos("acme/web\nacme/api\nacme/plain\nacme/missing\n")
    rows = scan(specs, out, jobs=2, sample=100, seed=7, now=NOW, work=work, clone=local_clone(origins))
    assert [(r["repo"], r["status"], r["reason"]) for r in rows] == [
        ("acme/web", "ok", ""), ("acme/api", "ok", ""), ("acme/plain", "ok", ""),
        ("acme/missing", "skipped", "not found, private or renamed"),
    ]
    assert list(work.iterdir()) == []  # every clone is removed

    by_repo = {r["repo"]: r for r in read_csv(out / "repos.csv")}
    web = by_repo["acme/web"]
    assert (web["agents_md"], web["claude_md"], web["instruction_units"], web["broken"]) == ("1", "1", "3", "1")
    assert web["top_reason"] == "broken:npm-script" and len(web["commit"]) == 40
    assert (by_repo["acme/api"]["broken"], by_repo["acme/plain"]["instruction_files"]) == ("0", "0")

    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "| processed | 3 |" in summary and "| skipped | 1 |" in summary
    assert "| with ≥1 broken reference | 1 of 3 (33%) |" in summary
    assert "| without agent instructions | 1 of 3 (33%) |" in summary
    assert "| with both AGENTS.md and CLAUDE.md | 1 of 3 (33%) |" in summary
    assert "broken: no such script in package.json" in summary
    assert "| acme/missing | not found, private or renamed |" in summary

    raw = json.loads((out / "raw" / "acme__web.json").read_text(encoding="utf-8"))
    assert raw["repo"] == "acme/web" and {u["unit"] for u in raw["units"]} == {
        "AGENTS.md#Commands", "AGENTS.md#Code", "CLAUDE.md#Claude"}
    pinned = (out / "repos.pinned.txt").read_text(encoding="utf-8").split()
    assert pinned[0].startswith("acme/web@") and pinned[-1] == "acme/missing"


def test_label_sample_is_reproducible(origins, tmp_path):
    specs = parse_repos("acme/web\nacme/api\n")
    clone = local_clone(origins)
    scan(specs, tmp_path / "a", sample=3, seed=1, now=NOW, clone=clone)
    scan(specs, tmp_path / "b", sample=3, seed=1, now=NOW, clone=clone)
    first, second = read_csv(tmp_path / "a" / "label.csv"), read_csv(tmp_path / "b" / "label.csv")
    assert first == second and len(first) == 3
    assert list(first[0]) == ["repo", "file", "line", "section", "source", "type", "extracted_from", "status",
                              "correct", "comment", "url"]
    assert all(row["correct"] == "" and row["url"].startswith("https://github.com/acme/") for row in first)
    everything = read_csv(scan(specs, tmp_path / "c", sample=100, seed=1, now=NOW, clone=clone) and
                          tmp_path / "c" / "label.csv")
    assert {row["type"] for row in everything} == {"npm-script", "script", "path"}
    assert {(row["source"], row["status"]) for row in everything} >= {
        ("./scripts/gone.sh", "broken"), ("src/app.ts", "ok"), ("tests/test_api.py", "ok")}


def test_one_failing_repository_does_not_stop_the_run(origins, tmp_path):
    def clone(spec, directory, timeout):
        if spec.name == "acme/web":
            raise RuntimeError("disk full")
        return local_clone(origins)(spec, directory, timeout)

    rows = scan(parse_repos("acme/web\nacme/api\n"), tmp_path / "r", now=NOW, clone=clone)
    assert [(r["status"], r["reason"]) for r in rows] == [("skipped", "error: RuntimeError: disk full"), ("ok", "")]


# --- scoring the labels ---


def test_score(tmp_path):
    path = tmp_path / "label.csv"
    rows = [("path", "да"), ("path", "yes"), ("path", "нет"), ("npm-script", "да"), ("npm-script", "неясно"),
            ("make", ""), ("script", "maybe")]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["repo", "file", "line", "section", "source", "type", "extracted_from", "status", "correct",
                         "comment", "url"])
        for kind, verdict in rows:
            writer.writerow(["acme/web", "AGENTS.md", "1", "", "x", kind, "", "ok", verdict, "", ""])
    report = score(path)
    assert "| all | 5 of 7 | 3 | 1 | 1 | 60.0% | 75.0% |" in report
    assert "| path | 3 of 3 | 2 | 1 | 0 | 66.7% | 66.7% |" in report
    assert "| npm-script | 2 of 2 | 1 | 0 | 1 | 50.0% | 100.0% |" in report
    assert "1 rows have a value in `correct` that is not yes/no/unclear" in report


def test_cli_scan(tmp_path, capsys, monkeypatch):
    assert main(["scan", "--repos", str(tmp_path / "missing.txt")]) == 2
    monkeypatch.setattr(scan_module.shutil, "which", lambda _: None)
    assert main(["scan", "--find", "5"]) == 2
    assert "gh auth login" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["0", "-3", "many"])
def test_scan_find_needs_a_positive_number(value, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["scan", "--find", value])
    assert exc.value.code == 2 and "--find" in capsys.readouterr().err
