"""`okf shadow`: control questions against the knowledge, on a mocked model only."""

import shutil
import subprocess

import pytest

from conftest import NOW, REPO_ROOT
from okf.cli import main
from okf.fix import FixError, Provider
from okf.shadow import ANSWER_SCHEMA, OPEN_SCHEMA, Question, ShadowError, load_questions, run, worse

KB = REPO_ROOT / "examples" / "demo" / "knowledge"


class Model(Provider):
    """Answers by unit name; records what it was shown."""

    actor = "test-model/1"

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def complete(self, system, prompt, unit, schema=None):
        self.calls.append((unit, prompt, schema))
        answer = self.answers.get(unit) or self.answers.get(unit.removeprefix("base:"))
        if isinstance(answer, Exception):
            raise answer
        return answer


Q = Question("price", "Сколько стоит минута поездки?", ["billing_service.md"], ["8 ₽"])


def test_a_good_answer_passes_and_the_model_sees_the_router_then_the_documents():
    model = Model({"shadow:price:open": {"open": ["billing_service.md"], "why": "x"},
                   "shadow:price:answer": {"answer": "Минута — 8 ₽.", "used": ["billing_service.md"]}})
    [result] = run(KB, [Q], model, {"billing_service.md": "human-verified"}, NOW)
    assert result.passed and result.checks == {"documents": True, "trust": True, "facts": True}
    (unit1, prompt1, schema1), (unit2, prompt2, schema2) = model.calls
    assert unit1 == "shadow:price:open" and schema1 == OPEN_SCHEMA and "[billing_service.md](billing_service.md)" in prompt1
    assert schema2 == ANSWER_SCHEMA and '<document path="billing_service.md">' in prompt2 and "8 ₽" in prompt2


def test_wrong_documents_outdated_sources_and_missing_facts():
    model = Model({"shadow:price:open": {"open": ["knowledge/api_start_ride.md", "nope.md"], "why": "x"},
                   "shadow:price:answer": {"answer": "Не знаю.", "used": []}})
    [result] = run(KB, [Q], model, {"api_start_ride.md": "recheck"}, NOW)
    assert result.opened == ["api_start_ride.md"] and result.invented == ["nope.md"]
    assert result.checks == {"documents": False, "trust": False, "facts": False}
    assert result.problems() == ["did not open billing_service.md", "relied on api_start_ride.md (to recheck)",
                                 'the answer lacks "8 ₽"']


def test_a_model_error_fails_the_question_without_stopping_the_run():
    model = Model({"shadow:price:open": FixError("rate limited"),
                   "shadow:other:open": {"open": [], "why": "x"}, "shadow:other:answer": {"answer": "ok", "used": []}})
    results = run(KB, [Q, Question("other", "?")], model, {}, NOW)
    assert results[0].error == "rate limited" and not results[0].passed and results[1].passed


def test_worse_lists_the_checks_lost_since_the_base():
    good = Model({"shadow:price:open": {"open": ["billing_service.md"], "why": ""},
                  "shadow:price:answer": {"answer": "8 ₽", "used": ["billing_service.md"]}})
    base = run(KB, [Q], good, {"billing_service.md": "human-verified"}, NOW)
    head = run(KB, [Q], good, {"billing_service.md": "recheck"}, NOW)
    assert [(r.question.id, lost) for r, lost in worse(base, head)] == [("price", ["trust"])]
    assert worse(head, base) == []


def test_load_questions(tmp_path):
    path = tmp_path / "shadow.yml"
    path.write_text("questions:\n  - question: Q?\n    expect_documents: [./a.md]\n    expect_facts: [1]\n",
                    encoding="utf-8")
    [q] = load_questions(path)
    assert (q.id, q.question, q.expect_documents, q.expect_facts) == ("q1", "Q?", ["a.md"], ["1"])
    path.write_text("nothing: here\n", encoding="utf-8")
    with pytest.raises(ShadowError, match="expected `questions:`"):
        load_questions(path)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_cli_shadow_on_the_demo_with_the_base_branch(tmp_path, capsys, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "examples"))
    from make_demo_history import build

    build(tmp_path / "wheelo")
    root = tmp_path / "wheelo"
    for key in ("ANTHROPIC_API_KEY", "OKF_LLM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert main(["shadow", str(root)]) == 2
    assert "no LLM key, nothing was run" in capsys.readouterr().err
    replay = str(root / ".okf" / "shadow_answers.example.json")
    subprocess.run(["git", "switch", "-q", "pr/billing-tariff"], cwd=root, check=True)
    code = main(["shadow", str(root), "--replay", replay, "--base", "main", "--strict", "--now", "2026-10-22T12:00:00Z"])
    out, err = capsys.readouterr()
    assert code == 1
    assert "[WARNING] shadow: minute-price: relied on billing_service.md (to recheck)" in out
    assert "[WARNING] shadow: minute-price: worse than main: trust" in out
    assert "3 questions, 1 passed (documents 3/3, trust 1/3, facts 3/3)" in err and "1 worse than main" in err
    worktrees = subprocess.run(["git", "worktree", "list"], cwd=root, capture_output=True, text=True).stdout
    assert len(worktrees.strip().splitlines()) == 1  # the base checkout is removed
