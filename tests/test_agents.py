from datetime import datetime, timezone

from conftest import OFFICIAL_BUNDLE, doc, meta
from okf.agents import freshness_status, render_agents, trust
from okf.bundle import Bundle

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def render(make_bundle, files):
    root = make_bundle(files)
    return render_agents(Bundle.load(root), NOW, root / "AGENTS.md")


def rows(text):
    return [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| Document")]


def one_doc(make_bundle, front):
    return Bundle.load(make_bundle({"a.md": doc(front)})).documents[0]


def test_router_lists_title_type_tags_freshness_trust_and_path(make_bundle):
    files = {
        "index.md": "# Index\n",
        "log.md": "# Log\n",
        "auth_flow.md": doc(meta(description="SMS login and JWT tokens."), "# Heading\n"),
    }
    text, skipped = render(make_bundle, files)
    assert skipped == []
    assert rows(text) == [
        "| Auth flow: SMS login and JWT tokens. | Architecture | auth, security | fresh until 2027-10-19 | "
        "human-reviewed, written by human:teamlead_ivan | [auth_flow.md](auth_flow.md) |"
    ]
    assert "[index.md](index.md)" in text and "[log.md](log.md)" in text
    assert "## Documents (1)" in text


def test_router_is_an_okf_concept_itself(make_bundle):
    text, _ = render(make_bundle, {"a.md": doc(meta())})
    root = make_bundle({"AGENTS.md": text})
    router = next(d for d in Bundle.load(root).documents if d.name == "AGENTS.md")
    assert router.meta["type"] == "Agent Router"
    assert router.meta["generated"]["by"].startswith("okf-ai/")


def test_router_skips_reserved_generated_and_invalid_files(make_bundle):
    files = {
        "index.md": "# Index\n",
        "sub/index.md": "# Sub\n",
        "AGENTS.md": "old\n",
        "good.md": doc(meta()),
        "bad.md": "# No header\n",
    }
    text, skipped = render(make_bundle, files)
    assert [row.split(" | ")[-1] for row in rows(text)] == ["[good.md](good.md) |"]
    assert [(issue.path.name, issue.level) for issue in skipped] == [("bad.md", "WARNING")]


def test_rows_are_sorted_by_type_then_path(make_bundle):
    files = {
        "z_concept.md": doc(meta(type="Concept")),
        "b_guide.md": doc(meta(type="guide")),
        "a_guide.md": doc(meta(type="Guide")),
        "table.md": doc(meta(type="BigQuery Table")),
    }
    text, _ = render(make_bundle, files)
    assert [row.split(" | ")[1] for row in rows(text)] == ["BigQuery Table", "Concept", "Guide", "guide"]


def test_title_falls_back_from_front_matter_to_heading_to_file_name(make_bundle):
    files = {
        "a.md": doc(meta(title="From YAML"), "# From heading\n"),
        "b.md": doc(meta(title=None), "```\n# not a heading\n```\n# From heading\n"),
        "ride_glossary.md": doc(meta(title=None), "No heading.\n"),
    }
    text, _ = render(make_bundle, files)
    assert [row.split(" | ")[0] for row in rows(text)] == ["| From YAML", "| From heading", "| ride glossary"]



def test_nested_paths_and_custom_output_location(make_bundle, tmp_path):
    root = make_bundle({"docs/api/start.md": doc(meta(type="API Endpoint"))})
    text, _ = render_agents(Bundle.load(root), NOW, tmp_path / "out" / "AGENTS.md")
    assert "[docs/api/start.md](../bundle/docs/api/start.md)" in text


def test_table_cells_are_escaped(make_bundle):
    text, _ = render(make_bundle, {"a.md": doc(meta(title="A | B"))})
    assert "A \\| B" in text


def test_freshness_status(make_bundle):
    def status(stale_after, lifecycle="stable"):
        return freshness_status(one_doc(make_bundle, meta(stale_after=stale_after, status=lifecycle)), NOW)

    assert status("2027-01-01T00:00:00Z") == "fresh until 2027-01-01"
    assert status("2026-11-21T00:00:00Z") == "review due 2026-11-21"
    assert status("2026-10-22T12:00:00Z") == "stale since 2026-10-22"
    assert status("2026-10-21T00:00:00Z") == "stale since 2026-10-21"
    assert status(None) == "no stale_after"
    assert status("2027-01-01T00:00:00Z", "deprecated") == "deprecated, fresh until 2027-01-01"
    assert status("2027-01-01T00:00:00Z", None) == "fresh until 2027-01-01"


def test_trust_tiers(make_bundle):
    def tier(**changes):
        return trust(one_doc(make_bundle, meta(**changes)))

    assert tier() == "human-reviewed, written by human:teamlead_ivan"
    assert tier(verified={"by": "process:ci", "at": "2026-10-01T00:00:00Z"}) == "machine-confirmed, written by human:teamlead_ivan"
    assert tier(verified=None, generated=None) == "unverified"
    assert tier(verified=[], **{"generated.by": "agent/1"}) == "unverified, written by agent/1"


def test_official_bundle_router():
    text, skipped = render_agents(Bundle.load(OFFICIAL_BUNDLE), NOW, OFFICIAL_BUNDLE / "AGENTS.md")
    assert skipped == []
    assert len(rows(text)) == 9
    assert any("deprecated, no stale_after" in row for row in rows(text))
