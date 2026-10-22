import shutil
import subprocess
from datetime import datetime, timezone

import pytest

from conftest import OFFICIAL_BUNDLE, doc, meta
from okf.bundle import Bundle
from okf.git import changed_paths, changes_since
from okf.stale import find_stale, resource_paths, source_matches

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def stale(make_bundle, files, changed, now=NOW):
    """Bundle in <repo>/kb; returns (level, file name, field) for every issue."""
    repo = make_bundle(files)
    bundle = Bundle.load(repo / "kb")
    return [(i.level, i.path.name, i.field) for i in find_stale(bundle, changed, repo, now)]


def sourced(*resources, **changes):
    return doc(meta(sources=[{"resource": r} for r in resources], **changes))


@pytest.mark.parametrize(
    "resource,doc_path,expected",
    [
        ("/src/auth.py", "kb/a.md", ["kb/src/auth.py"]),
        ("/src/auth.py", "kb/docs/a.md", ["kb/src/auth.py"]),
        ("../src/auth.py", "kb/docs/a.md", ["kb/src/auth.py"]),
        ("../../src/auth.py", "kb/docs/a.md", ["src/auth.py"]),
        ("policies/x.md", "kb/metrics/a.md", ["kb/metrics/policies/x.md", "kb/policies/x.md"]),
        ("./b.md#part", "kb/a.md", ["kb/b.md"]),
        ("/src/", "kb/a.md", ["kb/src"]),
        ("https://github.com/Smoooky/okf-ai/blob/main/src/okf/cli.py", "kb/a.md", ["src/okf/cli.py"]),
        ("https://github.com/Smoooky/okf-ai/tree/main/src/okf#readme", "kb/a.md", ["src/okf"]),
        ("https://wiki.example/src/auth.py", "kb/a.md", []),
        ("jira://WHL-1", "kb/a.md", []),
        ("../../../outside.py", "kb/docs/a.md", []),
        ("", "kb/a.md", []),
    ],
)
def test_resource_paths(make_bundle, resource, doc_path, expected):
    repo = make_bundle({doc_path: doc(meta())})
    bundle = Bundle.load(repo / "kb")
    [document] = bundle.documents
    assert resource_paths(resource, document, bundle.root, repo.resolve()) == expected


@pytest.mark.parametrize(
    "pattern,changed,expected",
    [
        ("src/auth.py", "src/auth.py", True),
        ("src/auth.py", "src/auth.pyc", False),
        ("src", "src/auth.py", True),
        ("src/", "src/deep/auth.py", True),
        ("src", "srcs/auth.py", False),
        ("src/*.py", "src/auth.py", True),
        ("src/*.py", "src/auth.sql", False),
    ],
)
def test_source_matches(pattern, changed, expected):
    assert source_matches(pattern, changed) is expected


def test_changed_code_marks_document_as_possibly_outdated(make_bundle):
    files = {
        "kb/index.md": "# Index\n",
        "kb/auth_flow.md": sourced("/src/auth.py"),
        "kb/billing.md": sourced("/src/billing.py"),
    }
    assert stale(make_bundle, files, ["kb/src/auth.py"]) == [("WARNING", "auth_flow.md", "sources")]


def test_warning_names_source_and_reviewer(make_bundle):
    repo = make_bundle({"kb/auth_flow.md": sourced("/src/auth.py")})
    [issue] = find_stale(Bundle.load(repo / "kb"), ["kb/src/auth.py"], repo, NOW)
    assert issue.message == (
        "Source /src/auth.py changed (kb/src/auth.py); document may be outdated, ask human:teamlead_ivan to review it"
    )


def test_reviewer_is_latest_human_verifier_else_human_author(make_bundle):
    verified = [
        {"by": "human:old", "at": "2026-01-01T00:00:00Z"},
        {"by": "human:new", "at": "2026-09-01T00:00:00Z"},
        {"by": "process:ci", "at": "2026-10-01T00:00:00Z"},
    ]
    files = {
        "kb/a.md": doc(meta(verified=verified)),
        "kb/b.md": doc(meta(verified=[{"by": "process:ci", "at": "2026-10-01T00:00:00Z"}])),
        "kb/c.md": doc(meta(verified=[], **{"generated.by": "agent/1"})),
    }
    repo = make_bundle(files)
    issues = find_stale(Bundle.load(repo / "kb"), ["kb/src/auth.py"], repo, NOW)
    assert [i.message.rsplit("outdated", 1)[1] for i in issues] == [
        ", ask human:new to review it",
        ", ask human:teamlead_ivan to review it",
        "",
    ]


def test_github_url_and_relative_sources(make_bundle):
    files = {
        "kb/docs/url.md": sourced("https://github.com/acme/app/blob/main/src/auth.py"),
        "kb/docs/rel.md": sourced("../../src/auth.py"),
        "kb/docs/other.md": sourced("https://example.com/src/auth.py", "all queries in project X"),
    }
    assert sorted(stale(make_bundle, files, ["src/auth.py"])) == [
        ("WARNING", "rel.md", "sources"),
        ("WARNING", "url.md", "sources"),
    ]


def test_scope_descriptors_are_not_paths(make_bundle):
    # "/src/* every module" would match "kb/src/a b.py" as a glob; a resource with spaces is a scope
    # descriptor, skipped as in okf trust
    files = {"kb/scope.md": sourced("/src/* every module"), "kb/path.md": sourced("/src/*")}
    assert stale(make_bundle, files, ["kb/src/a every module"]) == [("WARNING", "path.md", "sources")]


def test_official_style_bundle_relative_path_without_slash(make_bundle):
    files = {"kb/metrics/margin.md": sourced("policies/margin-standard.md"), "kb/policies/margin-standard.md": doc(meta())}
    assert stale(make_bundle, files, ["kb/policies/margin-standard.md"]) == [("WARNING", "margin.md", "sources")]


def test_directory_and_glob_sources(make_bundle):
    files = {"kb/dir.md": sourced("/src/"), "kb/glob.md": sourced("/src/*.sql")}
    assert stale(make_bundle, files, ["kb/src/schema.sql"]) == [
        ("WARNING", "dir.md", "sources"),
        ("WARNING", "glob.md", "sources"),
    ]


def test_changed_paths_are_normalized(make_bundle):
    files = {"kb/a.md": sourced("/src/auth.py")}
    assert stale(make_bundle, files, [".\\kb\\src\\auth.py"]) == [("WARNING", "a.md", "sources")]


def test_document_updated_in_same_change_is_info(make_bundle):
    files = {"kb/auth_flow.md": sourced("/src/auth.py")}
    assert stale(make_bundle, files, ["kb/src/auth.py", "kb/auth_flow.md"]) == [("INFO", "auth_flow.md", "sources")]


def test_stale_when_now_reaches_stale_after(make_bundle):
    files = {
        "kb/old.md": doc(meta(stale_after="2026-10-22T11:59:59Z")),
        "kb/exact.md": doc(meta(stale_after="2026-10-22T15:00:00+03:00")),  # == NOW
        "kb/fresh.md": doc(meta(stale_after="2026-10-22T12:00:01Z")),
        "kb/none.md": doc(meta(stale_after=None)),
    }
    assert sorted(stale(make_bundle, files, [])) == [
        ("WARNING", "exact.md", "stale_after"),
        ("WARNING", "old.md", "stale_after"),
    ]


def test_now_can_be_moved(make_bundle):
    files = {"kb/a.md": doc(meta())}  # stale_after 2027-10-19
    later = datetime(2027, 10, 20, tzinfo=timezone.utc)
    assert stale(make_bundle, files, [], now=later) == [("WARNING", "a.md", "stale_after")]


def test_documents_with_broken_front_matter_are_skipped(make_bundle):
    files = {"kb/a.md": "# no header\n", "kb/b.md": "---\n- list\n---\n"}
    assert stale(make_bundle, files, ["kb/src/auth.py"]) == []


def test_official_bundle_sources(tmp_path):
    repo = OFFICIAL_BUNDLE.parent
    bundle = Bundle.load(OFFICIAL_BUNDLE)
    issues = find_stale(bundle, ["acme_retail/policies/margin-standard.md"], repo, NOW)
    assert sorted(i.path.relative_to(bundle.root).as_posix() for i in issues) == [
        "computations/gross-margin-period.md",
        "metrics/gross-margin.md",
    ]


requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


@requires_git
def test_git_changed_files_against_base(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/auth.py").write_text("TTL = 30\n")
    (repo / "src/billing.py").write_text("FEE = 50\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "src/auth.py").write_text("TTL = 7\n")
    _git(repo, "commit", "-q", "-am", "ttl")
    (repo / "src/billing.py").write_text("FEE = 60\n")  # uncommitted change counts too

    assert sorted(changed_paths(changes_since(repo, "main"))) == ["src/auth.py", "src/billing.py"]
