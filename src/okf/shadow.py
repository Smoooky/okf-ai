"""`okf shadow`: shadow-testing from the brief. Does an agent find and use the right knowledge?

`.okf/shadow.yml` holds control questions:

    questions:
      - id: auth-lockout
        question: После скольких неверных кодов блокируется номер и на сколько?
        expect_documents: [auth_flow.md]      # paths from the bundle root
        expect_facts: ["5 неверных", "15 минут"]  # must be in the answer (case does not matter)

For each question the model sees only the router (the bundle's AGENTS.md) and picks the documents to
open; then it gets their text and answers. Three checks: it opened the expected documents, it did
not rely on a document the trust map marks "to recheck" or "broken", and the answer has the facts.
With `--base REF` the same questions run on the base branch too, and the questions that got worse are
listed. Without an LLM key nothing runs; `--replay FILE` uses saved answers (demos, tests).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from okf.agents import render_agents
from okf.bundle import Bundle
from okf.fix import FixError, Provider

MAX_OPEN = 5
OPEN_SCHEMA = {
    "type": "object",
    "properties": {"open": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}},
    "required": ["open", "why"],
    "additionalProperties": False,
}
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "used": {"type": "array", "items": {"type": "string"}}},
    "required": ["answer", "used"],
    "additionalProperties": False,
}
SYSTEM_OPEN = f"""You are an AI coding agent working in a repository with a knowledge base.
You get the router of the knowledge base (AGENTS.md: a table of its documents) and a question.
Choose the documents you would open to answer it: at most {MAX_OPEN}, only paths from the router.
Answer with JSON: {{"open": [paths], "why": one line}}."""
SYSTEM_ANSWER = """You are an AI coding agent. Answer the question from the opened documents only;
if they do not say, answer that you do not know. Be short and exact: numbers, names, paths.
Answer with JSON: {"answer": the answer, "used": [paths of the documents you relied on]}."""
CHECKS = ("documents", "trust", "facts")
RISKY = ("recheck", "broken")


class ShadowError(RuntimeError):
    pass


@dataclass
class Question:
    id: str
    question: str
    expect_documents: list[str] = field(default_factory=list)
    expect_facts: list[str] = field(default_factory=list)


@dataclass
class Result:
    question: Question
    opened: list[str] = field(default_factory=list)
    used: list[str] = field(default_factory=list)
    answer: str = ""
    missing_documents: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    risky: list[tuple[str, str]] = field(default_factory=list)  # (document, level) it relied on
    invented: list[str] = field(default_factory=list)  # paths the model asked for that do not exist
    error: str | None = None

    @property
    def checks(self) -> dict[str, bool]:
        if self.error:
            return {name: False for name in CHECKS}
        return {"documents": not self.missing_documents, "trust": not self.risky, "facts": not self.missing_facts}

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def problems(self) -> list[str]:
        if self.error:
            return [self.error]
        found = []
        if self.missing_documents:
            found.append(f"did not open {', '.join(self.missing_documents)}")
        if self.risky:
            found.append("relied on " + ", ".join(f"{doc} ({'to recheck' if level == 'recheck' else level})"
                                                  for doc, level in self.risky))
        if self.missing_facts:
            found.append("the answer lacks " + ", ".join(f'"{fact}"' for fact in self.missing_facts))
        return found


def load_questions(path: Path) -> list[Question]:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ShadowError(f"cannot read {path}: {exc}") from None
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ShadowError(f"{path}: expected `questions:` with a list of questions")
    questions = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("question"), str):
            raise ShadowError(f"{path}: question {i + 1} needs `question:`")
        questions.append(Question(str(item.get("id") or f"q{i + 1}"), item["question"].strip(),
                                  [_norm(d) for d in item.get("expect_documents") or []],
                                  [str(f) for f in item.get("expect_facts") or []]))
    return questions


def run(bundle_root: Path, questions: list[Question], provider: Provider, levels: dict[str, str],
        now: datetime, prefix: str = "") -> list[Result]:
    """`levels`: trust level of each document, by its path from the bundle root."""
    bundle = Bundle.load(bundle_root)
    router_path = bundle.root / "AGENTS.md"
    router = router_path.read_text(encoding="utf-8") if router_path.is_file() else \
        render_agents(bundle, now, router_path)[0]
    documents = {doc.rel: doc for doc in bundle.concepts()}
    results = []
    for question in questions:
        result = Result(question)
        results.append(result)
        try:
            chosen = provider.complete(SYSTEM_OPEN, f"<router>\n{router}\n</router>\n\nQuestion: {question.question}",
                                       f"{prefix}shadow:{question.id}:open", OPEN_SCHEMA)
            for path in [_norm(p) for p in (chosen.get("open") or [])][:MAX_OPEN]:
                if path not in documents and "/" in path and path.split("/", 1)[1] in documents:
                    path = path.split("/", 1)[1]  # "knowledge/auth_flow.md": the bundle folder in front
                (result.opened if path in documents else result.invented).append(path)
            texts = "\n\n".join(f'<document path="{p}">\n{documents[p].text}\n</document>' for p in result.opened)
            answer = provider.complete(SYSTEM_ANSWER, f"{texts or '(no documents opened)'}\n\nQuestion: "
                                                      f"{question.question}", f"{prefix}shadow:{question.id}:answer",
                                       ANSWER_SCHEMA)
        except FixError as exc:
            result.error = str(exc)
            continue
        result.answer = str(answer.get("answer") or "").strip()
        result.used = [p for p in (_norm(u) for u in answer.get("used") or []) if p in result.opened] or result.opened
        result.missing_documents = [d for d in question.expect_documents if d not in result.opened]
        result.risky = [(d, levels[d]) for d in result.used if levels.get(d) in RISKY]
        found = _plain(result.answer)
        result.missing_facts = [f for f in question.expect_facts if _plain(f) not in found]
    return results


def worse(base: list[Result], head: list[Result]) -> list[tuple[Result, list[str]]]:
    """Questions whose checks passed on the base branch and fail now."""
    before = {r.question.id: r for r in base}
    found = []
    for result in head:
        old = before.get(result.question.id)
        if old is None:
            continue
        lost = [name for name in CHECKS if old.checks[name] and not result.checks[name]]
        if lost:
            found.append((result, lost))
    return found


def at_ref(git_root: Path, ref: str) -> tuple[Path, Path]:
    """A temporary worktree of `ref`: (its root, the directory to remove afterwards)."""
    temp = Path(tempfile.mkdtemp(prefix="okf-shadow-")).resolve()  # Windows: no 8.3 short names
    target = temp / "base"
    result = subprocess.run(["git", "worktree", "add", "-q", "--detach", str(target), ref], cwd=git_root,
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        shutil.rmtree(temp, ignore_errors=True)
        raise ShadowError(f"cannot check out {ref}: {result.stderr.strip()}")
    return target, temp


def drop_worktree(git_root: Path, target: Path, temp: Path) -> None:
    subprocess.run(["git", "worktree", "remove", "--force", str(target)], cwd=git_root, capture_output=True)
    shutil.rmtree(temp, ignore_errors=True)


def _norm(path: str) -> str:
    path = str(path).strip().strip("`").replace("\\", "/")
    path = re.sub(r"^(\./|/)+", "", path)
    return path.split("#", 1)[0]


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip().casefold()
