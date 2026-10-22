import shutil
import subprocess
from datetime import date

import pytest

from conftest import doc, meta
from okf.bundle import Bundle
from okf.stale import find_stale, git_changed_files, source_matches, source_path

TODAY = date(2026, 10, 22)


def stale(make_bundle, files, changed, today=TODAY):
    root = make_bundle(files)
    bundle = Bundle.load(root / "kb")
    return [(i.level, i.path.name, i.field) for i in find_stale(bundle, changed, root, today)]


def sources(*items, **changes):
    return doc(meta(**{"provenance.sources": list(items)}, **changes))


@pytest.mark.parametrize(
    "source,expected",
    [
        ("git://src/auth.py", "src/auth.py"),
        ("git:///src/auth.py", "src/auth.py"),
        ("git://./src/auth.py#L10-L20", "src/auth.py"),
        ("git://src/", "src/"),
        ("https://example.com/src/auth.py", None),
        ("jira://WHL-1", None),
        ("git://", None),
        (42, None),
    ],
)
def test_source_path(source, expected):
    assert source_path(source) == expected


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
        "kb/auth_flow.md": sources("git://src/auth.py"),
        "kb/billing.md": sources("git://src/billing.py"),
        "src/auth.py": "TTL = 30\n",
    }
    assert stale(make_bundle, files, ["src/auth.py"]) == [("WARNING", "auth_flow.md", "provenance.sources")]


def test_warning_names_source_and_reviewer(make_bundle):
    root = make_bundle({"kb/auth_flow.md": sources("git://src/auth.py")})
    [issue] = find_stale(Bundle.load(root / "kb"), ["src/auth.py"], root, TODAY)
    assert "git://src/auth.py changed" in issue.message
    assert "may be outdated" in issue.message
    assert "teamlead_ivan" in issue.message


def test_unrelated_changes_and_non_git_sources_are_ignored(make_bundle):
    files = {"kb/a.md": sources("https://wiki.example/src/auth.py", "jira://src/auth.py", "git://src/other.py")}
    assert stale(make_bundle, files, ["src/auth.py", "README.md"]) == []


def test_directory_and_glob_sources(make_bundle):
    files = {"kb/dir.md": sources("git://src/"), "kb/glob.md": sources("git://src/*.sql")}
    assert stale(make_bundle, files, ["src/schema.sql"]) == [
        ("WARNING", "dir.md", "provenance.sources"),
        ("WARNING", "glob.md", "provenance.sources"),
    ]


def test_changed_paths_are_normalized(make_bundle):
    files = {"kb/a.md": sources("git://src/auth.py")}
    assert stale(make_bundle, files, [".\\src\\auth.py"]) == [("WARNING", "a.md", "provenance.sources")]


def test_document_updated_in_same_change_is_info(make_bundle):
    files = {"kb/auth_flow.md": sources("git://src/auth.py")}
    assert stale(make_bundle, files, ["src/auth.py", "kb/auth_flow.md"]) == [
        ("INFO", "auth_flow.md", "provenance.sources")
    ]


def test_expired_stale_after_is_warning(make_bundle):
    files = {
        "kb/old.md": doc(meta(**{"freshness.last_reviewed": "2026-01-01", "freshness.stale_after": "2026-10-21"})),
        "kb/today.md": doc(meta(**{"freshness.last_reviewed": "2026-01-01", "freshness.stale_after": "2026-10-22"})),
        "kb/fresh.md": doc(meta()),
    }
    assert stale(make_bundle, files, []) == [("WARNING", "old.md", "freshness.stale_after")]


def test_today_can_be_moved(make_bundle):
    files = {"kb/a.md": doc(meta())}  # stale_after 2027-10-19
    assert stale(make_bundle, files, [], today=date(2027, 10, 20)) == [("WARNING", "a.md", "freshness.stale_after")]


def test_documents_with_broken_front_matter_are_skipped(make_bundle):
    files = {"kb/a.md": "# no header\n", "kb/b.md": "---\n- list\n---\n"}
    assert stale(make_bundle, files, ["src/auth.py"]) == []


requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@requires_git
def test_git_changed_files_against_base(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/auth.py").write_text("TTL = 30\n")
    (repo / "src/billing.py").write_text("FEE = 50\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "src/auth.py").write_text("TTL = 7\n")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-am", "ttl")
    (repo / "src/billing.py").write_text("FEE = 60\n")  # uncommitted change counts too

    assert sorted(git_changed_files(repo, "main")) == ["src/auth.py", "src/billing.py"]
