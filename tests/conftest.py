import copy
from pathlib import Path

import pytest
import yaml

from okf.bundle import Bundle
from okf.validate import validate_bundle

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID_META = {
    "type": "Architecture",
    "tags": ["auth", "security"],
    "provenance": {"sources": ["git://src/auth.py"]},
    "trust": {"generated": "human", "verified_by": "teamlead_ivan", "confidence": 1.0},
    "lifecycle": {"status": "stable"},
    "freshness": {"last_reviewed": "2026-10-19", "stale_after": "2027-10-19"},
    "timestamp": "2026-10-19T10:00:00Z",
}

DELETE = object()


def meta(**changes):
    """VALID_META with dotted-path overrides: meta(**{"trust.confidence": 0.5, "tags": DELETE})."""
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


@pytest.fixture
def validate(make_bundle):
    """Validate a one-document bundle; returns (level, file, field) tuples for that document."""

    def run(text, name="doc.md", extra=None):
        files = {"index.md": f"# Index\n\n[doc]({name})\n", name: text, **(extra or {})}
        bundle = Bundle.load(make_bundle(files))
        return [(i.level, i.path.relative_to(bundle.root).as_posix(), i.field) for i in validate_bundle(bundle)]

    return run
