from datetime import date

from conftest import doc, meta
from okf.agents import freshness_status, render_agents
from okf.bundle import Bundle

TODAY = date(2026, 10, 22)


def render(make_bundle, files):
    root = make_bundle(files)
    bundle = Bundle.load(root)
    return render_agents(bundle, TODAY, root / "AGENTS.md")


def rows(text):
    return [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| Document")]


def test_router_lists_title_type_tags_freshness_trust_and_path(make_bundle):
    files = {
        "index.md": "# Index\n",
        "log.md": "# Log\n",
        "auth_flow.md": doc(meta(), "# Auth flow\n\nText.\n"),
    }
    text, skipped = render(make_bundle, files)
    assert skipped == []
    assert rows(text) == [
        "| Auth flow | Architecture | auth, security | fresh until 2027-10-19 | 1.0 human | [auth_flow.md](auth_flow.md) |"
    ]
    assert "[index.md](index.md)" in text and "[log.md](log.md)" in text
    assert "## Documents (1)" in text


def test_router_skips_service_generated_and_invalid_files(make_bundle):
    files = {
        "index.md": "# Index\n",
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
        "b_guide.md": doc(meta(type="Guide")),
        "a_guide.md": doc(meta(type="Guide")),
    }
    text, _ = render(make_bundle, files)
    assert [row.split(" | ")[1] for row in rows(text)] == ["Concept", "Guide", "Guide"]
    assert "a_guide.md" in rows(text)[1]


def test_title_falls_back_from_front_matter_to_heading_to_file_name(make_bundle):
    files = {
        "a.md": doc(meta(title="From YAML"), "# From heading\n"),
        "b.md": doc(meta(), "```\n# not a heading\n```\n# From heading\n"),
        "ride_glossary.md": doc(meta(), "No heading.\n"),
    }
    text, _ = render(make_bundle, files)
    assert [row.split(" | ")[0] for row in rows(text)] == ["| From YAML", "| From heading", "| ride glossary"]


def test_nested_paths_and_custom_output_location(make_bundle, tmp_path):
    root = make_bundle({"docs/api/start.md": doc(meta(type="API Endpoint"))})
    text, _ = render_agents(Bundle.load(root), TODAY, tmp_path / "out" / "AGENTS.md")
    assert "[docs/api/start.md](../bundle/docs/api/start.md)" in text


def test_table_cells_are_escaped(make_bundle):
    text, _ = render(make_bundle, {"a.md": doc(meta(title="A | B"))})
    assert "A \\| B" in text


def test_freshness_status(make_bundle):
    def status(stale_after, lifecycle="stable"):
        front = meta(**{"freshness.last_reviewed": "2026-01-01", "freshness.stale_after": stale_after,
                        "lifecycle.status": lifecycle})
        root = make_bundle({"a.md": doc(front)})
        return freshness_status(Bundle.load(root).documents[0], TODAY)

    assert status("2027-01-01") == "fresh until 2027-01-01"
    assert status("2026-11-21") == "review due 2026-11-21"
    assert status("2026-10-22") == "review due 2026-10-22"
    assert status("2026-10-21") == "stale since 2026-10-21"
    assert status("not a date") == "unknown"
    assert status("2027-01-01", "deprecated") == "deprecated, fresh until 2027-01-01"
