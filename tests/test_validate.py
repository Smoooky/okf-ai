"""One test group per rule of etc/spec/cli-validator.md (stage 1)."""

import pytest

from conftest import DELETE, doc, meta
from okf.bundle import Bundle
from okf.validate import ALLOWED_TYPES, validate_bundle

ERR = "ERROR"
WARN = "WARNING"


def test_valid_document_has_no_issues(validate):
    assert validate(doc(meta())) == []


# --- YAML structure and parsing ---


def test_missing_front_matter_is_error(validate):
    assert validate("# Title\n\nNo header.\n") == [(ERR, "doc.md", "frontmatter")]


def test_front_matter_must_be_first_line(validate):
    assert validate("\n" + doc(meta())) == [(ERR, "doc.md", "frontmatter")]


def test_unclosed_front_matter_is_error(validate):
    assert validate("---\ntype: Concept\n# Title\n") == [(ERR, "doc.md", "frontmatter")]


def test_yaml_syntax_error_is_error(validate):
    assert validate(doc("type: [Concept\ntags: x")) == [(ERR, "doc.md", "frontmatter")]


@pytest.mark.parametrize("front_matter", ["- type: Concept\n- tags: [a]", "just some text", "42"])
def test_front_matter_must_be_mapping(validate, front_matter):
    assert validate(doc(front_matter)) == [(ERR, "doc.md", "frontmatter")]


def test_empty_front_matter_is_error(validate):
    assert validate("---\n---\n# Title\n") == [(ERR, "doc.md", "frontmatter")]


def test_utf8_bom_is_ignored(validate):
    assert validate("﻿" + doc(meta())) == []


# --- Service files ---


@pytest.mark.parametrize("name", ["index.md", "log.md"])
def test_service_file_with_front_matter_is_error(make_bundle, name):
    files = {"index.md": "# Index\n\n[doc](doc.md)\n", "log.md": "# Log\n", "doc.md": doc(meta())}
    files[name] = doc({"title": "service"}, files[name])
    issues = validate_bundle(Bundle.load(make_bundle(files)))
    assert [(i.level, i.path.name, i.field) for i in issues] == [(ERR, name, "frontmatter")]


def test_service_files_without_front_matter_are_ok(make_bundle):
    files = {"index.md": "# Index\n\n[doc](doc.md)\n", "log.md": "# Log\n\n- created\n", "doc.md": doc(meta())}
    assert validate_bundle(Bundle.load(make_bundle(files))) == []


def test_nested_index_is_a_knowledge_file(make_bundle):
    files = {"index.md": "# Index\n\n[sub](sub/index.md)\n", "sub/index.md": "# No header\n"}
    issues = validate_bundle(Bundle.load(make_bundle(files)))
    assert [(i.path.parent.name, i.field) for i in issues] == [("sub", "frontmatter")]


def test_agents_md_is_not_validated(make_bundle):
    files = {"index.md": "# Index\n\n[doc](doc.md)\n", "doc.md": doc(meta()), "AGENTS.md": "# AGENTS\n[x](missing.md)\n"}
    assert validate_bundle(Bundle.load(make_bundle(files))) == []


# --- type ---


def test_type_missing_is_error(validate):
    assert validate(doc(meta(type=DELETE))) == [(ERR, "doc.md", "type")]


@pytest.mark.parametrize("value", ["", "   ", None])
def test_type_empty_is_error(validate, value):
    assert validate(doc(meta(type=value))) == [(ERR, "doc.md", "type")]


@pytest.mark.parametrize("value", ["Endpoint", "architecture", "APIEndpoint", "API_Endpoint", ["Concept"], 5])
def test_type_outside_dictionary_is_error(validate, value):
    assert validate(doc(meta(type=value))) == [(ERR, "doc.md", "type")]


@pytest.mark.parametrize("value", ALLOWED_TYPES)
def test_every_dictionary_type_is_accepted(validate, value):
    assert validate(doc(meta(type=value))) == []


def test_type_error_message_matches_spec_and_suggests(make_bundle):
    files = {"index.md": "[d](api.md)", "api.md": doc(meta(type="Endpoint"))}
    [issue] = validate_bundle(Bundle.load(make_bundle(files)))
    assert issue.message.startswith('Value "Endpoint" is not in the allowed type dictionary')
    assert '"API Endpoint"' in issue.message


# --- tags ---


@pytest.mark.parametrize("value", ["auth", {"a": 1}, None, [1, 2], ["ok", None]])
def test_tags_not_list_of_strings_is_error(validate, value):
    assert validate(doc(meta(tags=value))) == [(ERR, "doc.md", "tags")]


@pytest.mark.parametrize("value", [DELETE, [], ["auth"]])
def test_tags_absent_or_list_of_strings_is_ok(validate, value):
    assert validate(doc(meta(tags=value))) == []


# --- provenance ---


def test_provenance_missing_is_error(validate):
    assert validate(doc(meta(provenance=DELETE))) == [(ERR, "doc.md", "provenance.sources")]


def test_provenance_sources_missing_is_error(validate):
    assert validate(doc(meta(**{"provenance.sources": DELETE}))) == [(ERR, "doc.md", "provenance.sources")]


def test_provenance_sources_empty_is_error(validate):
    assert validate(doc(meta(**{"provenance.sources": []}))) == [(ERR, "doc.md", "provenance.sources")]


def test_provenance_sources_not_list_is_error(validate):
    assert validate(doc(meta(**{"provenance.sources": "git://src/a.py"}))) == [(ERR, "doc.md", "provenance.sources")]


def test_provenance_not_mapping_is_error(validate):
    assert validate(doc(meta(provenance=["git://src/a.py"]))) == [(ERR, "doc.md", "provenance")]


def test_provenance_source_must_be_non_empty_string(validate):
    issues = validate(doc(meta(**{"provenance.sources": ["git://src/a.py", ""]})))
    assert issues == [(ERR, "doc.md", "provenance.sources[1]")]


def test_non_git_sources_are_allowed(validate):
    sources = ["https://wiki.example/page", "jira://WHL-1", "git://src/a.py"]
    assert validate(doc(meta(**{"provenance.sources": sources}))) == []


# --- trust.confidence ---


def test_confidence_missing_is_error(validate):
    assert validate(doc(meta(**{"trust.confidence": DELETE}))) == [(ERR, "doc.md", "trust.confidence")]


@pytest.mark.parametrize("value", [1.01, -0.1, 2])
def test_confidence_out_of_range_is_error(validate, value):
    assert validate(doc(meta(**{"trust.confidence": value}))) == [(ERR, "doc.md", "trust.confidence")]


def test_confidence_nan_is_error(validate):
    text = doc(meta()).replace("confidence: 1.0", "confidence: .nan")
    assert validate(text) == [(ERR, "doc.md", "trust.confidence")]


@pytest.mark.parametrize("value", ["0.8", "high", True, None])
def test_confidence_not_a_number_is_error(validate, value):
    assert validate(doc(meta(**{"trust.confidence": value}))) == [(ERR, "doc.md", "trust.confidence")]


@pytest.mark.parametrize("value", [0, 0.0, 0.5, 1, 1.0])
def test_confidence_boundaries_are_ok(validate, value):
    assert validate(doc(meta(**{"trust.confidence": value}))) == []


def test_confidence_range_message_matches_spec(make_bundle):
    files = {"index.md": "[d](auth.md)", "auth.md": doc(meta(**{"trust.confidence": 1.5}))}
    [issue] = validate_bundle(Bundle.load(make_bundle(files)))
    assert issue.message.startswith("Value must be between 0.0 and 1.0")


# --- AI pretending to be human ---


@pytest.mark.parametrize("generated", ["agent", "script", "Agent", " SCRIPT "])
@pytest.mark.parametrize("confidence", [1.0, 1])
def test_machine_generated_with_full_confidence_is_error(validate, generated, confidence):
    front = meta(**{"trust.generated": generated, "trust.confidence": confidence})
    assert validate(doc(front)) == [(ERR, "doc.md", "trust.confidence")]


@pytest.mark.parametrize("generated,confidence", [("agent", 0.99), ("script", 0.5), ("human", 1.0)])
def test_machine_generated_below_one_or_human_is_ok(validate, generated, confidence):
    front = meta(**{"trust.generated": generated, "trust.confidence": confidence})
    assert validate(doc(front)) == []


# --- trust.verified_by ---


@pytest.mark.parametrize("value", [DELETE, None, "", "  "])
def test_verified_by_missing_is_error(validate, value):
    assert validate(doc(meta(**{"trust.verified_by": value}))) == [(ERR, "doc.md", "trust.verified_by")]


def test_verified_by_required_for_agent_documents(validate):
    front = meta(**{"trust.generated": "agent", "trust.confidence": 0.6, "trust.verified_by": DELETE})
    assert validate(doc(front)) == [(ERR, "doc.md", "trust.verified_by")]


def test_trust_missing_reports_both_fields(validate):
    assert validate(doc(meta(trust=DELETE))) == [
        (ERR, "doc.md", "trust.confidence"),
        (ERR, "doc.md", "trust.verified_by"),
    ]


def test_trust_not_mapping_is_error(validate):
    assert validate(doc(meta(trust="human"))) == [(ERR, "doc.md", "trust")]


# --- freshness ---


@pytest.mark.parametrize("key", ["last_reviewed", "stale_after"])
def test_freshness_date_missing_is_error(validate, key):
    assert validate(doc(meta(**{f"freshness.{key}": DELETE}))) == [(ERR, "doc.md", f"freshness.{key}")]


@pytest.mark.parametrize("key", ["last_reviewed", "stale_after"])
@pytest.mark.parametrize("value", ["19.10.2026", "2026-13-01", "2026-02-30", "soon", 20261019, None])
def test_freshness_date_invalid_is_error(validate, key, value):
    assert validate(doc(meta(**{f"freshness.{key}": value}))) == [(ERR, "doc.md", f"freshness.{key}")]


def test_unquoted_yaml_dates_are_ok(validate):
    text = doc(meta()).replace("'2026-10-19'", "2026-10-19").replace("'2027-10-19'", "2027-10-19")
    assert "last_reviewed: 2026-10-19" in text
    assert validate(text) == []


def test_unquoted_invalid_date_is_field_error_not_yaml_error(validate):
    text = doc(meta()).replace("'2027-10-19'", "2027-13-45")
    assert validate(text) == [(ERR, "doc.md", "freshness.stale_after")]


def test_freshness_missing_reports_both_dates(validate):
    assert validate(doc(meta(freshness=DELETE))) == [
        (ERR, "doc.md", "freshness.last_reviewed"),
        (ERR, "doc.md", "freshness.stale_after"),
    ]


def test_freshness_under_lifecycle_gets_a_hint(make_bundle):
    front = meta(freshness=DELETE, **{"lifecycle.freshness": {"last_reviewed": "2026-10-19", "stale_after": "2027-10-19"}})
    files = {"index.md": "[d](doc.md)", "doc.md": doc(front)}
    issues = validate_bundle(Bundle.load(make_bundle(files)))
    assert [i.field for i in issues] == ["freshness.last_reviewed", "freshness.stale_after"]
    assert all("move freshness to the top level" in i.message for i in issues)


def test_stale_after_before_last_reviewed_is_error(validate):
    front = meta(**{"freshness.last_reviewed": "2026-10-19", "freshness.stale_after": "2026-10-18"})
    assert validate(doc(front)) == [(ERR, "doc.md", "freshness.stale_after")]


def test_stale_after_equal_to_last_reviewed_is_ok(validate):
    front = meta(**{"freshness.last_reviewed": "2026-10-19", "freshness.stale_after": "2026-10-19"})
    assert validate(doc(front)) == []


def test_stale_after_in_the_past_is_not_a_validation_error(validate):
    front = meta(**{"freshness.last_reviewed": "2020-01-01", "freshness.stale_after": "2020-06-01"})
    assert validate(doc(front)) == []


# --- graph hygiene: broken links and orphans (warnings) ---


def test_broken_relative_link_is_warning(validate):
    assert validate(doc(meta(), "See [x](missing.md).\n")) == [(WARN, "doc.md", "link")]


def test_broken_root_relative_link_is_warning(make_bundle):
    files = {"index.md": "[d](docs/doc.md)", "docs/doc.md": doc(meta(), "[x](/concepts/missing_file.md)\n")}
    [issue] = validate_bundle(Bundle.load(make_bundle(files)))
    assert (issue.level, issue.field, issue.message) == (WARN, "link", "Broken link to /concepts/missing_file.md")
    lines = (make_bundle.root / "docs/doc.md").read_text(encoding="utf-8").split("\n")
    assert lines[issue.line - 1] == "[x](/concepts/missing_file.md)"


def test_existing_links_are_ok(make_bundle):
    body = "[a](other.md) [b](./other.md#part) [c](/docs/../other.md) [d](sub/x%20y.md) [e](<sub/x y.md>)\n"
    files = {
        "index.md": "[d](doc.md)",
        "doc.md": doc(meta(), body),
        "other.md": doc(meta()),
        "sub/x y.md": doc(meta()),
    }
    assert validate_bundle(Bundle.load(make_bundle(files))) == []


def test_external_links_anchors_and_code_are_ignored(validate):
    body = (
        "[web](https://example.com/x.md) [mail](mailto:a@b.c) [top](#title) [git](git://src/a.py)\n"
        "`[inline](missing1.md)`\n"
        "```\n[fenced](missing2.md)\n```\n"
        "~~~md\n[tilde](missing3.md)\n~~~\n"
    )
    assert validate(doc(meta(), body)) == []


def test_reference_style_and_image_links_are_checked(validate):
    body = "![img](missing.png)\n\n[ref]: missing.md\n"
    assert validate(doc(meta(), body)) == [(WARN, "doc.md", "link"), (WARN, "doc.md", "link")]


def test_orphan_file_is_warning(make_bundle):
    files = {"index.md": "[a](a.md)", "a.md": doc(meta()), "b.md": doc(meta())}
    issues = validate_bundle(Bundle.load(make_bundle(files)))
    assert [(i.level, i.path.name, i.field) for i in issues] == [(WARN, "b.md", "link")]
    assert "Orphan" in issues[0].message


def test_link_from_any_document_counts(make_bundle):
    files = {"index.md": "[a](a.md)", "a.md": doc(meta(), "[b](b.md)\n"), "b.md": doc(meta())}
    assert validate_bundle(Bundle.load(make_bundle(files))) == []


def test_self_link_and_agents_md_links_do_not_count(make_bundle):
    files = {
        "index.md": "# Index\n",
        "a.md": doc(meta(), "[me](a.md)\n"),
        "AGENTS.md": "[a](a.md)\n",
    }
    issues = validate_bundle(Bundle.load(make_bundle(files)))
    assert [(i.level, i.path.name, i.field) for i in issues] == [(WARN, "a.md", "link")]


def test_service_files_are_never_orphans(make_bundle):
    files = {"index.md": "[a](a.md)", "log.md": "# Log\n", "a.md": doc(meta())}
    assert validate_bundle(Bundle.load(make_bundle(files))) == []


def test_hidden_directories_are_skipped(make_bundle):
    files = {"index.md": "[a](a.md)", "a.md": doc(meta()), ".github/notes.md": "no header"}
    assert validate_bundle(Bundle.load(make_bundle(files))) == []


def test_field_errors_point_to_the_line(make_bundle):
    files = {"index.md": "[d](doc.md)", "doc.md": doc(meta(**{"trust.confidence": 3}))}
    [issue] = validate_bundle(Bundle.load(make_bundle(files)))
    lines = (make_bundle.root / "doc.md").read_text(encoding="utf-8").split("\n")
    assert lines[issue.line - 1].strip() == "confidence: 3"
