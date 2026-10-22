"""`okf init`: the bundle, the sidecar, the workflow, the AGENTS.md hint; nothing overwritten."""

from datetime import datetime, timezone

import yaml

from conftest import REPO_ROOT
from okf.bundle import Bundle
from okf.cli import main
from okf.git import History
from okf.report import ERROR
from okf.schema import get_profile
from okf.scaffold import AGENTS_MARK, init
from okf.sources import registry
from okf.trust import build_map
from okf.validate import validate_bundle

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
AGENTS = "# AGENTS.md\n\nIntro.\n\n## Auth\n\nLogin: `src/auth.py`, see [the schema](db/schema.sql).\n\n" \
         "## Архитектура\n\nTwo services.\n"


def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "db").mkdir()
    (root / "src" / "auth.py").write_text("TTL = 30\n", encoding="utf-8")
    (root / "db" / "schema.sql").write_text("", encoding="utf-8")
    (root / "AGENTS.md").write_text(AGENTS, encoding="utf-8")
    return root


def test_init_creates_a_valid_bundle_and_the_frame(tmp_path):
    root = repo(tmp_path)
    result = init(root, NOW)
    created = sorted(p.relative_to(root).as_posix() for p in result.created)
    assert created == [".github/workflows/okf.yml", ".okf/trust.yml", "knowledge/AGENTS.md",
                       "knowledge/architecture.md", "knowledge/index.md", "knowledge/local_setup.md",
                       "knowledge/log.md", "knowledge/runbook.md"]
    assert [p.name for p in result.updated] == ["AGENTS.md"]
    issues = validate_bundle(Bundle.load(root / "knowledge"), get_profile(False))
    assert [i for i in issues if i.level == ERROR] == []
    text = (root / "knowledge" / "runbook.md").read_text(encoding="utf-8")
    assert "type: Runbook\n" in text and "status: draft\n" in text
    assert "generated: { by: process:okf-init, at: 2026-10-22T12:00:00Z }" in text
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith(AGENTS.rstrip("\n")) and AGENTS_MARK in agents and "knowledge/AGENTS.md" in agents
    workflow = yaml.safe_load((root / ".github/workflows/okf.yml").read_text(encoding="utf-8"))
    assert workflow["env"]["OKF_REPO"] == "." and workflow["env"]["OKF_BUNDLE"] == "knowledge"
    units = {u.name: u for u in build_map(root, History(None, NOW), now=NOW, sources=registry({})).units}
    assert units["knowledge/runbook.md"].message == "edited by process:okf-init on 2026-10-22; not verified"


def test_init_never_overwrites_without_force(tmp_path):
    root = repo(tmp_path)
    init(root, NOW)
    (root / "knowledge" / "runbook.md").write_text("mine\n", encoding="utf-8")
    again = init(root, NOW)
    assert again.created == [] and again.updated == []
    assert (root / "knowledge" / "runbook.md").read_text(encoding="utf-8") == "mine\n"
    assert (root / "AGENTS.md").read_text(encoding="utf-8").count(AGENTS_MARK) == 1
    forced = init(root, NOW, force=True)
    assert root / "knowledge" / "runbook.md" in forced.updated
    assert (root / "knowledge" / "runbook.md").read_text(encoding="utf-8") != "mine\n"


def test_init_from_agents_proposes_documents_with_sources(tmp_path):
    root = repo(tmp_path)
    result = init(root, NOW, from_agents=True)
    names = {p.name for p in result.created}
    assert {"auth.md", "arkhitektura.md"} <= names
    auth = (root / "knowledge" / "auth.md").read_text(encoding="utf-8")
    assert "sources:\n  - resource: ../src/auth.py\n" in auth and "type: Guide" in auth
    assert "[the schema](../db/schema.sql)" in auth  # links still work from knowledge/
    assert "type: Architecture" in (root / "knowledge" / "arkhitektura.md").read_text(encoding="utf-8")
    issues = validate_bundle(Bundle.load(root / "knowledge"), get_profile(False))
    assert [i for i in issues if i.level == ERROR] == [] and not [i for i in issues if i.field == "link"]
    assert "[Auth](auth.md)" in (root / "knowledge" / "index.md").read_text(encoding="utf-8")


def test_cli_init(tmp_path, capsys):
    root = repo(tmp_path)
    assert main(["init", str(root), "--now", "2026-10-22"]) == 0
    err = capsys.readouterr().err
    assert "okf init: created" in err and "knowledge/index.md" in err and "updated" in err
    assert main(["init", str(root)]) == 0
    assert "kept" in capsys.readouterr().err


def test_workflow_template_follows_the_repository_workflow():
    """The workflow okf init writes has the same check steps as the one okf-ai runs on itself."""
    ours = yaml.safe_load((REPO_ROOT / ".github/workflows/okf.yml").read_text(encoding="utf-8"))
    template = yaml.safe_load((REPO_ROOT / "src/okf/templates/okf.yml").read_text(encoding="utf-8"))
    names = [[s.get("name") or s.get("uses") for s in w["jobs"]["knowledge"]["steps"]] for w in (ours, template)]
    assert names[0] == names[1]
    assert "tests" not in template["jobs"]
