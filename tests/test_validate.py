"""`okf validate`: OKF v0.2 conformance (default) and the okf-ai strict profile."""

import pytest

from conftest import DELETE, doc, issues_of, meta
from okf.bundle import Bundle
from okf.schema import TEAM_TYPES, get_profile
from okf.validate import validate_bundle

ERR = "ERROR"
WARN = "WARNING"
STRICT = {"strict": True}


@pytest.mark.parametrize("strict", [False, True])
def test_valid_document_has_no_issues(validate, strict):
    assert validate(doc(meta()), strict=strict) == []


def test_type_alone_is_conformant(validate):
    assert validate(doc({"type": "BigQuery Table"})) == []


# --- front matter structure (§4, §11) ---


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


def test_unknown_keys_are_tolerated(validate):
    front = meta(confidence=1.0, provenance={"sources": ["git://x"]}, **{"not": [{"term": "x"}]})
    assert validate(doc(front)) == []


# --- type ---


def test_type_missing_is_error(validate):
    assert validate(doc(meta(type=DELETE))) == [(ERR, "doc.md", "type")]


@pytest.mark.parametrize("value", ["", "   ", None])
def test_type_empty_is_error(validate, value):
    assert validate(doc(meta(type=value))) == [(ERR, "doc.md", "type")]


@pytest.mark.parametrize("value", [["Concept"], 5])
def test_type_must_be_string(validate, value):
    assert validate(doc(meta(type=value))) == [(ERR, "doc.md", "type")]


@pytest.mark.parametrize("value", ["Endpoint", "BigQuery Table", "Skill", "architecture"])
def test_unknown_type_is_fine_by_default_and_a_warning_in_strict(validate, value):
    assert validate(doc(meta(type=value))) == []
    assert validate(doc(meta(type=value)), **STRICT) == [(WARN, "doc.md", "type")]


@pytest.mark.parametrize("value", TEAM_TYPES)
def test_team_dictionary_types_pass_strict(validate, value):
    front = meta(type=value, runtime="bigquery") if value == "Attested Computation" else meta(type=value)
    assert validate(doc(front), **STRICT) == []


def test_strict_type_warning_suggests_closest(make_bundle):
    root = make_bundle({"index.md": "[d](/api.md)", "api.md": doc(meta(type="Endpoint"))})

    [issue] = validate_bundle(Bundle.load(root), get_profile(strict=True))
    assert issue.message == 'Value "Endpoint" is not in the okf-ai type dictionary (did you mean "API Endpoint"?)'


# --- tags ---


@pytest.mark.parametrize("value", ["auth, security", {"a": 1}, [1, 2], ["ok", None]])
def test_tags_not_list_of_strings_warns_by_default_errors_in_strict(validate, value):
    assert validate(doc(meta(tags=value))) == [(WARN, "doc.md", "tags")]
    assert validate(doc(meta(tags=value)), **STRICT) == [(ERR, "doc.md", "tags")]


@pytest.mark.parametrize("value", [DELETE, None, [], ["auth"]])
def test_tags_absent_or_list_of_strings_is_ok(validate, value):
    assert validate(doc(meta(tags=value)), **STRICT) == []


# --- sources (§5.1) ---


@pytest.mark.parametrize("value", [DELETE, []])
def test_sources_are_optional_by_default_required_in_strict(validate, value):
    assert validate(doc(meta(sources=value))) == []
    assert validate(doc(meta(sources=value)), **STRICT) == [(ERR, "doc.md", "sources")]


def test_sources_must_be_a_list(validate):
    assert validate(doc(meta(sources={"resource": "/a.md"}))) == [(ERR, "doc.md", "sources")]


def test_sources_entry_must_be_mapping(validate):
    assert validate(doc(meta(sources=["git://src/a.py"]))) == [(ERR, "doc.md", "sources[0]")]


@pytest.mark.parametrize("entry", [{"id": "x"}, {"resource": ""}, {"resource": None}])
def test_sources_entry_requires_resource(validate, entry):
    assert validate(doc(meta(sources=[{"resource": "/a.py"}, entry]))) == [(ERR, "doc.md", "sources[1].resource")]


def test_sources_resource_must_be_string(validate):
    assert validate(doc(meta(sources=[{"resource": 42}]))) == [(ERR, "doc.md", "sources[0].resource")]


def test_sources_accept_urls_paths_scopes_and_signals(validate):
    sources = [
        {"id": "a", "resource": "https://wiki.example/page", "title": "Wiki", "author": "team:docs", "usage_count": 5,
         "last_modified": "2026-05-30T00:00:00Z"},
        {"resource": "/references/schema.md"},
        {"resource": "../src/auth.py"},
        {"resource": "all queries in BigQuery project X"},
    ]
    front = meta(sources=sources, usage_window={"from": "2026-06-01T00:00:00Z", "to": "2026-06-30T00:00:00Z"})
    assert validate(doc(front)) == []


def test_sources_timestamps_must_have_offsets(validate):
    sources = [{"resource": "/a", "last_modified": "2026-05-30", "usage_window": {"from": "2026-06-01T00:00:00Z"}}]
    front = meta(sources=sources, usage_window="June")
    assert validate(doc(front)) == [
        (ERR, "doc.md", "sources[0].last_modified"),
        (ERR, "doc.md", "sources[0].usage_window.to"),
        (ERR, "doc.md", "usage_window"),
    ]


# --- generated and verified (§5.2, §7) ---


def test_generated_must_be_mapping(validate):
    assert validate(doc(meta(generated="human:ivan"))) == [(ERR, "doc.md", "generated")]


def test_generated_requires_by(validate):
    assert validate(doc(meta(**{"generated.by": DELETE}))) == [(ERR, "doc.md", "generated.by")]


def test_generated_at_is_optional_but_must_be_an_instant(validate):
    assert validate(doc(meta(**{"generated.at": DELETE}))) == []
    assert validate(doc(meta(**{"generated.at": "yesterday"}))) == [(ERR, "doc.md", "generated.at")]


def test_verified_bare_mapping_is_a_one_element_list(validate):
    front = meta(verified={"by": "human:ivan", "at": "2026-10-19T10:00:00Z"})
    assert validate(doc(front), **STRICT) == []


def test_verified_must_be_mapping_or_list(validate):
    assert validate(doc(meta(verified="human:ivan"))) == [(ERR, "doc.md", "verified")]


@pytest.mark.parametrize("key", ["by", "at"])
def test_verified_entry_requires_by_and_at(validate, key):
    entry = {"by": "human:ivan", "at": "2026-10-19T10:00:00Z"}
    del entry[key]
    assert validate(doc(meta(verified=[entry]))) == [(ERR, "doc.md", f"verified[0].{key}")]


def test_verified_entry_must_be_mapping(validate):
    assert validate(doc(meta(verified=["human:ivan"]))) == [(ERR, "doc.md", "verified[0]")]


@pytest.mark.parametrize(
    "actor", ["human:ivan", "human:jsmith@acme", "process:finance-nightly", "reference_agent/gemini-2.5-pro", "okf-ai/0.1.0"]
)
def test_valid_actors(validate, actor):
    front = meta(**{"generated.by": actor}, verified={"by": actor, "at": "2026-10-19T10:00:00Z"}, status="draft")
    assert validate(doc(front)) == []


@pytest.mark.parametrize("actor", ["teamlead_ivan", "human", "human:", "team:docs", "agent/", "/1.0", "a/b/c", "x y/1"])
def test_invalid_actors(validate, actor):
    front = meta(**{"generated.by": actor}, verified={"by": actor, "at": "2026-10-19T10:00:00Z"})
    issues = validate(doc(front))
    assert (ERR, "doc.md", "generated.by") in issues
    assert (ERR, "doc.md", "verified.by") in issues


# --- status and stale_after (§5.4, §5.5) ---


@pytest.mark.parametrize("value", ["draft", "stable", "deprecated", DELETE])
def test_status_values(validate, value):
    assert validate(doc(meta(status=value))) == []


@pytest.mark.parametrize("value", ["published", "Stable", None, 1])
def test_status_outside_vocabulary_is_error(validate, value):
    assert validate(doc(meta(status=value))) == [(ERR, "doc.md", "status")]


@pytest.mark.parametrize("value", ["2027-10-19T00:00:00Z", "2027-10-19T03:00:00+03:00", "2027-10-19T00:00:00.5z"])
def test_stale_after_valid_instants(validate, value):
    assert validate(doc(meta(stale_after=value))) == []


@pytest.mark.parametrize("value", ["2027-10-19", "2027-10-19T00:00:00", "2027-13-01T00:00:00Z", "soon", 20271019])
def test_stale_after_must_have_utc_offset(validate, value):
    assert validate(doc(meta(stale_after=value))) == [(ERR, "doc.md", "stale_after")]


def test_unquoted_yaml_instants_are_ok(validate):
    text = doc(meta()).replace("'2027-10-19T00:00:00Z'", "2027-10-19T00:00:00Z")
    assert "stale_after: 2027-10-19T00:00:00Z" in text
    assert validate(text, **STRICT) == []


def test_stale_after_in_the_past_is_not_a_validation_error(validate):
    assert validate(doc(meta(stale_after="2026-11-01T00:00:00Z")), **STRICT) == []


# --- Attested Computation (§10.2) ---


def test_attested_computation_requires_runtime(validate):
    assert validate(doc(meta(type="Attested Computation"))) == [(ERR, "doc.md", "runtime")]
    assert validate(doc(meta(type="Attested Computation", runtime="bigquery"))) == []


# --- strict profile: team rules on OKF fields ---


def test_strict_requires_verified(validate):
    for value in (DELETE, []):
        assert validate(doc(meta(verified=value))) == []
        assert validate(doc(meta(verified=value)), **STRICT) == [(ERR, "doc.md", "verified")]


def test_strict_requires_stale_after(validate):
    assert validate(doc(meta(stale_after=DELETE))) == []
    assert validate(doc(meta(stale_after=DELETE)), **STRICT) == [(ERR, "doc.md", "stale_after")]


def test_strict_stale_after_not_before_latest_verification(validate):
    verified = [
        {"by": "human:ivan", "at": "2026-01-01T00:00:00Z"},
        {"by": "process:nightly", "at": "2026-10-20T00:00:00Z"},
    ]
    assert validate(doc(meta(verified=verified, stale_after="2026-10-19T00:00:00Z"))) == []
    assert validate(doc(meta(verified=verified, stale_after="2026-10-19T00:00:00Z")), **STRICT) == [
        (ERR, "doc.md", "stale_after")
    ]
    assert validate(doc(meta(verified=verified, stale_after="2026-10-20T03:00:00+03:00")), **STRICT) == []


@pytest.mark.parametrize("author", ["wheelo-docs-agent/1.4", "process:docgen"])
@pytest.mark.parametrize("status", ["stable", DELETE])
def test_strict_machine_written_stable_needs_human_review(validate, author, status):
    front = meta(**{"generated.by": author}, status=status, verified=[{"by": "process:ci", "at": "2026-10-20T00:00:00Z"}])
    assert validate(doc(front)) == []
    assert validate(doc(front), **STRICT) == [(ERR, "doc.md", "verified")]


def test_strict_ai_rule_message(make_bundle):
    front = meta(**{"generated.by": "agent/1"}, verified={"by": "process:ci", "at": "2026-10-20T00:00:00Z"})
    root = make_bundle({"index.md": "[d](/doc.md)", "doc.md": doc(front)})

    [issue] = validate_bundle(Bundle.load(root), get_profile(strict=True))
    assert "human:<id>" in issue.message and "status: draft" in issue.message


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "draft"},
        {"status": "deprecated"},
        {"verified": [{"by": "process:ci", "at": "2026-10-20T00:00:00Z"}, {"by": "human:ivan", "at": "2026-10-21T00:00:00Z"}]},
    ],
)
def test_strict_agent_document_ok_when_draft_or_human_reviewed(validate, changes):
    base = {"generated.by": "agent/1", "verified": [{"by": "process:ci", "at": "2026-10-20T00:00:00Z"}]}
    assert validate(doc(meta(**{**base, **changes})), **STRICT) == []


def test_strict_human_written_machine_checked_is_ok(validate):
    front = meta(verified=[{"by": "process:ci", "at": "2026-10-20T00:00:00Z"}])
    assert validate(doc(front), **STRICT) == []


def test_strict_hints_at_legacy_team_fields(make_bundle):
    legacy = {
        "type": "Service",
        "provenance": {"sources": ["git://src/billing.py"]},
        "trust": {"generated": "human", "verified_by": "maria", "confidence": 0.9},
        "freshness": {"last_reviewed": "2026-10-05", "stale_after": "2027-04-05"},
    }
    root = make_bundle({"index.md": "[d](/doc.md)", "doc.md": doc(legacy)})

    assert validate_bundle(Bundle.load(root)) == []
    issues = validate_bundle(Bundle.load(root), get_profile(strict=True))
    assert [i.field for i in issues] == ["sources", "verified", "stale_after"]
    assert all("OKF v0.2 uses" in i.message for i in issues)


# --- reserved files: index.md and log.md (§3.1, §8, §9) ---


def test_root_index_may_declare_okf_version(make_bundle):
    root = make_bundle({"index.md": '---\nokf_version: "0.2"\n---\n[d](/doc.md)\n', "doc.md": doc(meta())})
    assert issues_of(root, strict=True) == []


def test_root_index_other_keys_are_error(make_bundle):
    root = make_bundle({"index.md": doc({"okf_version": "0.2", "title": "x"}, "[d](/doc.md)\n"), "doc.md": doc(meta())})
    assert issues_of(root) == [(ERR, "index.md", "frontmatter")]


def test_root_index_other_version_is_warning(make_bundle):
    root = make_bundle({"index.md": "---\nokf_version: 0.1\n---\n[d](/doc.md)\n", "doc.md": doc(meta())})
    assert issues_of(root) == [(WARN, "index.md", "okf_version")]


@pytest.mark.parametrize("strict", [False, True])
def test_nested_index_with_front_matter_is_error(make_bundle, strict):
    files = {"index.md": "[s](/sub/index.md)", "sub/index.md": '---\nokf_version: "0.2"\n---\n[d](/sub/doc.md)\n',
             "sub/doc.md": doc(meta())}
    assert issues_of(make_bundle(files), strict) == [(ERR, "sub/index.md", "frontmatter")]


def test_nested_index_and_log_are_reserved_not_concepts(make_bundle):
    files = {"index.md": "[s](/sub/index.md)", "sub/index.md": "[d](doc.md)\n", "sub/log.md": "# Log\n",
             "sub/doc.md": doc(meta())}
    assert issues_of(make_bundle(files), strict=True) == []


def test_log_front_matter_allowed_by_okf_error_in_strict(make_bundle):
    files = {"index.md": "[d](/doc.md)", "doc.md": doc(meta()), "log.md": doc({"type": "Log"}, "# Log\n")}
    assert issues_of(make_bundle(files)) == []
    assert issues_of(make_bundle(files), strict=True) == [(ERR, "log.md", "frontmatter")]


def test_log_date_headings_must_be_iso(make_bundle):
    log = "# Log\n\n## 2026-10-22\n* x\n\n## 23.10.2026\n* y\n\n## 2026-02-30\n* z\n"
    files = {"index.md": "[d](/doc.md)", "doc.md": doc(meta()), "log.md": log}
    assert issues_of(make_bundle(files)) == [(WARN, "log.md", "log"), (WARN, "log.md", "log")]


def test_agents_md_is_not_validated(make_bundle):
    files = {"index.md": "[d](/doc.md)", "doc.md": doc(meta()), "AGENTS.md": "# AGENTS\n[x](missing.md)\n"}
    assert issues_of(make_bundle(files), strict=True) == []


# --- links: broken (warning, §6.1) and orphans (strict) ---


def test_broken_relative_link_is_warning(validate):
    assert validate(doc(meta(), "See [x](missing.md).\n")) == [(WARN, "doc.md", "link")]


def test_broken_root_relative_link_is_warning(make_bundle):
    files = {"index.md": "[d](docs/doc.md)", "docs/doc.md": doc(meta(), "[x](/concepts/missing_file.md)\n")}
    root = make_bundle(files)

    [issue] = validate_bundle(Bundle.load(root))
    assert (issue.level, issue.field, issue.message) == (WARN, "link", "Broken link to /concepts/missing_file.md")
    lines = (root / "docs/doc.md").read_text(encoding="utf-8").split("\n")
    assert lines[issue.line - 1] == "[x](/concepts/missing_file.md)"


def test_existing_links_are_ok(make_bundle):
    body = "[a](other.md) [b](./other.md#part) [c](/docs/../other.md) [d](sub/x%20y.md) [e](<sub/x y.md>) [f](sub/)\n"
    files = {"index.md": "[d](doc.md)", "doc.md": doc(meta(), body), "other.md": doc(meta()), "sub/x y.md": doc(meta())}
    assert issues_of(make_bundle(files), strict=True) == []


def test_external_links_anchors_footnotes_and_code_are_ignored(validate):
    body = (
        "[web](https://example.com/x.md) [mail](mailto:a@b.c) [top](#title) A claim.[^auth]\n"
        "`[inline](missing1.md)`\n"
        "```\n[fenced](missing2.md)\n```\n"
        "~~~md\n[tilde](missing3.md)\n~~~\n"
        "\n[^auth]: Auth module source\n"
    )
    assert validate(doc(meta(), body)) == []


def test_reference_style_and_image_links_are_checked(validate):
    body = "![img](missing.png)\n\n[ref]: missing.md\n"
    assert validate(doc(meta(), body)) == [(WARN, "doc.md", "link"), (WARN, "doc.md", "link")]


def test_orphans_are_reported_only_in_strict(make_bundle):
    files = {"index.md": "[a](a.md)", "a.md": doc(meta()), "b.md": doc(meta())}
    assert issues_of(make_bundle(files)) == []
    assert issues_of(make_bundle(files), strict=True) == [(WARN, "b.md", "link")]


def test_link_from_any_document_counts(make_bundle):
    files = {"index.md": "[a](a.md)", "a.md": doc(meta(), "[b](/b.md)\n"), "b.md": doc(meta())}
    assert issues_of(make_bundle(files), strict=True) == []


def test_self_link_and_agents_md_links_do_not_count(make_bundle):
    files = {"index.md": "# Index\n", "a.md": doc(meta(), "[me](a.md)\n"), "AGENTS.md": "[a](a.md)\n"}
    assert issues_of(make_bundle(files), strict=True) == [(WARN, "a.md", "link")]


def test_hidden_directories_are_skipped(make_bundle):
    files = {"index.md": "[a](a.md)", "a.md": doc(meta()), ".github/notes.md": "no header"}
    assert issues_of(make_bundle(files), strict=True) == []


def test_field_errors_point_to_the_line(make_bundle):
    root = make_bundle({"index.md": "[d](doc.md)", "doc.md": doc(meta(status="published"))})

    [issue] = validate_bundle(Bundle.load(root))
    lines = (root / "doc.md").read_text(encoding="utf-8").split("\n")
    assert lines[issue.line - 1].strip() == "status: published"
