import copy
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
