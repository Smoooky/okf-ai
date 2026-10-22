"""`okf init`: the frame from the brief in one command.

- knowledge/: an OKF bundle (index.md, log.md, a few `status: draft` templates, the AGENTS.md router);
- .okf/trust.yml: where `okf verify` records confirmations;
- .github/workflows/okf.yml: the check on every pull request;
- a short section in an existing AGENTS.md that sends agents to knowledge/.

Nothing is overwritten without `force`. `from_agents` also proposes a knowledge document for every
section of the existing AGENTS.md / CLAUDE.md, with `sources` from the paths in its text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from okf.agents import render_agents
from okf.bundle import SCHEME_RE, Bundle
from okf.git import History
from okf.importer import slug
from okf.trust import _flow, _relative, instruction_units

INIT_ACTOR = "process:okf-init"
AGENTS_MARK = "<!-- okf init: knowledge router -->"
AGENTS_SECTION = f"""
## Knowledge base

{AGENTS_MARK}
Project knowledge for agents lives in `knowledge/` ([OKF](https://github.com/GoogleCloudPlatform/open-knowledge-format)).
Start with the router [knowledge/AGENTS.md](knowledge/AGENTS.md): pick the documents your task needs and read only
those. A document `okf trust` marks as "to recheck" or "broken" is a hint, not a fact: check it against the code.
"""

TEMPLATES = {
    "architecture.md": ("Architecture", "System overview", "The main parts of the system and how they talk.",
                        ["architecture"],
                        "## Parts\n\n- **<service>** — what it does, where its code lives (`src/...`).\n\n"
                        "## How a request flows\n\n1. ...\n\n## Decisions\n\n- Why we chose ... over ..."),
    "local_setup.md": ("Guide", "Local setup", "How to run the project on a laptop.", ["onboarding", "dev"],
                       "## Requirements\n\n- ...\n\n## Run\n\n```bash\n# the commands, as in AGENTS.md\n```\n\n"
                       "## Test data\n\n- ..."),
    "runbook.md": ("Runbook", "Runbook: <incident>", "What the on-call engineer does when <symptom>.",
                   ["oncall", "incident"],
                   "## Symptoms\n\n- ...\n\n## Check\n\n1. ...\n\n## Fix\n\n1. ...\n\n## Escalate\n\n- ..."),
}


@dataclass
class Result:
    created: list[Path] = field(default_factory=list)
    kept: list[Path] = field(default_factory=list)  # already there: not overwritten without --force
    updated: list[Path] = field(default_factory=list)


def init(root: Path, now: datetime, force: bool = False, from_agents: bool = False) -> Result:
    root = Path(root).resolve()
    result = Result()
    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    kb = root / "knowledge"
    docs: dict[str, str] = {}
    for name, (kind, title, description, tags, body) in TEMPLATES.items():
        docs[name] = _document(kind, title, description, tags, [], stamp,
                               f"> Template from `okf init`: replace the text, list the code it describes in `sources`\n"
                               f"> (`- resource: ../src/app.py`), then confirm it: `okf verify knowledge/{name}`.\n\n"
                               + body)
    if from_agents:
        docs.update(proposals(root, kb, stamp))
    for name, text in docs.items():
        _write(kb / name, text, force, result)
    links = "\n".join(f"- [{_title_of(text)}]({name})" for name, text in docs.items())
    _write(kb / "index.md", f'---\nokf_version: "0.2"\n---\n\n# Knowledge base\n\nWhat agents and people need to '
                            f"know about this project. Agents start with [AGENTS.md](AGENTS.md).\n\n{links}\n",
           force, result)
    _write(kb / "log.md", f"# Log\n\n## {stamp[:10]}\n* **Creation**: `okf init` created the bundle "
                          f"({len(docs)} draft documents).\n", force, result)
    _write(root / ".okf" / "trust.yml", "# okf-ai trust records: who confirmed which agent instruction sections, and "
                                        "when.\n# Written by `okf verify`.\nunits: []\n", force, result)
    workflow = resources.files("okf").joinpath("templates/okf.yml").read_text(encoding="utf-8")
    _write(root / ".github" / "workflows" / "okf.yml", workflow, force, result)
    router = kb / "AGENTS.md"
    if force or not router.exists():
        text, _ = render_agents(Bundle.load(kb), now, router)
        _write(router, text, True, result)
    else:
        result.kept.append(router)
    agents = root / "AGENTS.md"
    if agents.is_file():
        current = agents.read_text(encoding="utf-8")
        if AGENTS_MARK not in current:
            agents.write_text(current.rstrip("\n") + "\n" + AGENTS_SECTION, encoding="utf-8", newline="\n")
            result.updated.append(agents)
    return result


def proposals(root: Path, kb: Path, stamp: str) -> dict[str, str]:
    """A draft knowledge document for every titled section of the agent instructions."""
    units, _ = instruction_units(root, History(None))
    docs: dict[str, str] = {}
    for unit in units:
        if not unit.section or unit.path.name not in ("AGENTS.md", "CLAUDE.md") or unit.path.parent != root:
            continue
        lines = unit.path.read_text(encoding="utf-8").split("\n")[unit.line : unit.end]
        body = _rebase_links("\n".join(lines).strip(), unit.path.parent, kb)
        name = f"{slug(unit.section) or 'section'}.md"
        if not body or name in docs or name in TEMPLATES:
            continue
        sources = [_relative(s, kb) for s in unit.sources]
        kind = _kind(unit.section)
        docs[name] = _document(kind, unit.section, f"From the {unit.name} section of the agent instructions.", [],
                               sources, stamp, f"> Proposed by `okf init --from-agents` from {unit.name}: check it, "
                                               f"then `okf verify knowledge/{name}`.\n\n" + body)
    return docs


def _rebase_links(text: str, origin: Path, kb: Path) -> str:
    """Relative markdown links written for the instruction file, made to work from knowledge/."""
    def rebase(match: re.Match) -> str:
        target = match.group(1)
        if SCHEME_RE.match(target) or target.startswith(("#", "/")):
            return match.group(0)
        return f"]({_relative(origin / target, kb)})"

    return re.sub(r"\]\(([^)\s]+)\)", rebase, text)


def _kind(title: str) -> str:
    lowered = title.lower()
    for words, kind in ((("архитект", "architecture", "design"), "Architecture"),
                        (("runbook", "incident", "инцидент", "дежур", "on-call", "oncall"), "Runbook"),
                        (("api", "endpoint", "эндпоинт"), "API Endpoint"),
                        (("правил", "policy", "rules", "политик"), "Policy")):
        if any(word in lowered for word in words):
            return kind
    return "Guide"


def _document(kind: str, title: str, description: str, tags: list[str], sources: list[str], stamp: str,
              body: str) -> str:
    lines = ["---", f"type: {kind}", f"title: {_scalar(title)}", f"description: {_scalar(description)}"]
    if tags:
        lines.append(f"tags: [{', '.join(tags)}]")
    lines += ["status: draft", f"generated: {_flow({'by': INIT_ACTOR, 'at': stamp})}"]
    if sources:
        lines += ["sources:", *(f"  - resource: {_scalar(s)}" for s in sources)]
    else:
        lines.append("sources: []  # the code this document describes, e.g. - resource: ../src/app.py")
    return "\n".join(lines) + f"\n---\n\n# {title}\n\n{body.rstrip()}\n"


def _scalar(text: str) -> str:
    plain = text and text[0] not in "-?:,[]{}#&*!|>'\"%@`<" and ": " not in text and " #" not in text
    return text if plain else "'" + text.replace("'", "''") + "'"


def _title_of(text: str) -> str:
    for line in text.split("\n"):
        if line.startswith("title: "):
            value = line[len("title: "):]
            return value[1:-1].replace("''", "'") if value.startswith("'") else value
    return "Document"


def _write(path: Path, text: str, force: bool, result: Result) -> None:
    if path.exists() and not force:
        result.kept.append(path)
        return
    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    (result.updated if existed else result.created).append(path)
