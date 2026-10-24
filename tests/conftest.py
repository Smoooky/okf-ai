import copy
import json
import os
import subprocess
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from okf.bundle import Bundle
from okf.schema import get_profile
from okf.validate import validate_bundle

REPO_ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_BUNDLE = REPO_ROOT / "tests" / "fixtures" / "okf-official" / "acme_retail"

# Valid in both profiles.
VALID_META = {
    "type": "Architecture",
    "title": "Auth flow",
    "tags": ["auth", "security"],
    "status": "stable",
    "generated": {"by": "human:teamlead_ivan", "at": "2026-10-19T10:00:00Z"},
    "verified": [{"by": "human:teamlead_ivan", "at": "2026-10-19T10:00:00Z"}],
    "stale_after": "2027-10-19T00:00:00Z",
    "sources": [{"id": "auth", "resource": "/src/auth.py"}],
}

DELETE = object()


def meta(**changes):
    """VALID_META with dotted-path overrides: meta(**{"generated.by": "agent/1", "tags": DELETE})."""
    result = copy.deepcopy(VALID_META)
    for dotted, value in changes.items():
        *parents, leaf = dotted.split(".")
        node = result
        for part in parents:
            node = node.setdefault(part, {})
        if value is DELETE:
            node.pop(leaf, None)
        else:
            node[leaf] = value
    return result


def doc(front_matter, body="# Title\n\nText.\n"):
    """Markdown text with front matter from a dict, or a raw YAML string."""
    if isinstance(front_matter, dict):
        front_matter = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False)
    return f"---\n{front_matter.rstrip()}\n---\n{body}"


class BundleFactory:
    def __init__(self, root: Path):
        self.root = root

    def __call__(self, files: dict) -> Path:
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return self.root


@pytest.fixture
def make_bundle(tmp_path):
    return BundleFactory(tmp_path / "bundle")


def issues_of(root, strict=False):
    """(level, path from the bundle root, field) for every issue."""
    bundle = Bundle.load(root)
    return [
        (i.level, i.path.relative_to(bundle.root).as_posix(), i.field)
        for i in validate_bundle(bundle, get_profile(strict))
    ]


@pytest.fixture
def validate(make_bundle):
    """Validate a one-concept bundle (plus an index linking it)."""

    def run(text, name="doc.md", extra=None, strict=False):
        files = {"index.md": f"# Index\n\n* [doc](/{name})\n", name: text, **(extra or {})}
        return issues_of(make_bundle(files), strict)

    return run


# --- No network in tests; a local mock HTTP server for connectors ---


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any request that is not to the local mock server fails the test."""
    real = urllib.request.urlopen

    def guarded(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else request
        assert url.startswith("http://127.0.0.1:"), f"unexpected network call to {url}"
        return real(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", guarded)


class Mock:
    """A local HTTP server: path -> list of (status, body, headers) answers, the last one repeats."""

    def __init__(self, routes):
        self.routes, self.seen = routes, []
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                mock.seen.append((self.path, dict(self.headers)))
                answers = mock.routes.get(self.path.split("?")[0], [(404, {}, {})])
                status, body, headers = answers.pop(0) if len(answers) > 1 else answers[0]
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                for key, value in {"Content-Type": "application/json", **headers}.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def mock():
    servers = []

    def start(routes):
        servers.append(Mock(routes))
        return servers[-1]

    yield start
    for server in servers:
        server.close()


# --- A throwaway git repository with commits at chosen dates, and the moment tests evaluate at ---

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class Repo:
    """A git repository in a temporary folder: write files, commit them at a date, map them."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args, when=None):
        env = {**os.environ, **({"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when} if when else {})}
        result = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                                cwd=self.root, check=True, capture_output=True, text=True, env=env)
        return result.stdout

    def write(self, files):
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return self

    def commit(self, when, message="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, when=when)
        return self

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def map(self, changes=None, now=NOW, **kwargs):
        from okf.git import History
        from okf.trust import build_map

        return build_map(self.root, History(self.root, now), changes, now=now, **kwargs)

    def units(self, now=NOW, **kwargs):
        return {u.name: u for u in self.map(now=now, **kwargs).units}

    def levels(self, **kwargs):
        return {unit.name: unit.level for unit in self.map(**kwargs).units}

    def unit(self, name, **kwargs):
        return next(u for u in self.map(**kwargs).units if u.name == name)

    def verify(self, target, by="human:ivan", when="2026-09-05T10:00:00Z"):
        from okf.trust import verify

        return verify(target, by, at(when), self.root, self.root)

    def plan(self, changes=None, only=None, provider=None, now=NOW, **draft_options):
        """okf fix: the mechanical fixes, and drafts when a provider is given."""
        from okf.fix import plan_drafts, plan_fixes
        from okf.git import History
        from okf.trust import build_map

        history = History(self.root, now)
        trust_map = build_map(self.root, history, changes, now=now)
        plan = plan_fixes(self.root, history, trust_map, changes, only)
        if provider:
            plan_drafts(plan, trust_map, history, provider, only, **draft_options)
        return plan

    def check(self):
        """okf agents-check: (level, file, field, message) per issue."""
        from okf.instructions import check_repository

        report = check_repository(self.root, False, None, self.root)
        return [(i.level, i.path.relative_to(self.root.resolve()).as_posix(), i.field, i.message)
                for i in report.issues]


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo")
