"""`okf fix`: proposed fixes for what `okf trust` and `okf agents-check` found.

Two layers:

- mechanical, no AI (always): a file git saw renamed gets its new path, a package.json script that
  was renamed (the same command under another name) gets its new name, an OKF source that moved
  gets its new path. Anything else broken is listed as needing a manual fix: nothing is invented.
- drafts (`--draft`, an LLM with the user's own key): a section whose code changed since it was
  confirmed gets a proposed new text, from the section, its sources and their diff. Every path and
  command in a draft must exist (checked with the same extraction as `okf agents-check`), or the
  draft is rejected.

Both print a unified diff; `--apply` writes it. Each rewritten section is recorded as `generated`
(in .okf/trust.yml, or in the OKF front matter), never as `verified`: the trust map shows it as not
verified until a person runs `okf verify`.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from okf import schema
from okf.bundle import front_matter_end, load_document
from okf.git import Change, History, commits_changing_count, file_at
from okf.instructions import InstructionFile, Repository, discover, references
from okf.sources import Registry, registry
from okf.sources.git import resource_paths
from okf.trust import (
    ROUTER_MARK, SIDECAR, Sidecar, TrustMap, _concepts, _relative, _unit_name, find_sidecar, section_hash, sections,
    set_generated,
)

FIX_ACTOR = "process:okf-fix"
DEFAULT_MODEL = "claude-opus-5-5"
# Models that take server-side refusal fallbacks (`fallbacks: "default"`).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
DRAFT_REASONS = {"recheck:code-changed", "recheck:in-change", "recheck:source-changed", "recheck:closed"}
KEY_HELP = ("set ANTHROPIC_API_KEY, or OKF_LLM_BASE_URL + OKF_LLM_API_KEY + OKF_LLM_MODEL for an "
            "OpenAI-compatible endpoint")
DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "section": {"type": "string", "description": "the whole new section, its heading line first"},
        "summary": {"type": "string", "description": "one line: what changed and why"},
        "changed": {"type": "boolean", "description": "false if the section is still correct as it is"},
    },
    "required": ["section", "summary", "changed"],
    "additionalProperties": False,
}
SYSTEM_PROMPT = """You keep instructions for AI coding agents true to the code they describe.
You get one section of an instruction file (or one knowledge document), the source files it
mentions, and what changed in those files since the section was last confirmed.

Rewrite only this section so that every statement in it matches the code after the change.
- Keep the heading line exactly as it is, the language, the tone and the formatting.
- Keep everything that is still true; change as little as possible.
- Do not invent file paths, commands, script names or options: use only those in the section or
  in the diff. A path or command that does not exist will make your draft rejected.
- If the section is still correct, return it unchanged with "changed": false.
Answer with JSON: {"section": the whole new section, "summary": one line saying what changed and
why, "changed": true or false}."""


class FixError(RuntimeError):
    pass


@dataclass
class Edit:
    """Replace `old` by `new` in one line: the mechanical fixes."""

    path: Path
    line: int  # 1-based
    old: str
    new: str
    unit: str
    kind: str  # "instruction" or "knowledge"
    reason: str


@dataclass
class Manual:
    path: Path
    line: int
    unit: str
    reason: str


@dataclass
class Draft:
    path: Path
    unit: str
    kind: str
    start: int  # 1-based, inclusive: the lines the draft replaces
    end: int
    new_lines: list[str] = field(default_factory=list)
    summary: str = ""
    by: str = ""
    rejected: str | None = None


@dataclass
class FixPlan:
    root: Path
    originals: dict[Path, list[str]] = field(default_factory=dict)
    edits: list[Edit] = field(default_factory=list)
    manual: list[Manual] = field(default_factory=list)
    drafts: list[Draft] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def after_edits(self) -> dict[Path, list[str]]:
        texts = {path: list(lines) for path, lines in self.originals.items()}
        for edit in self.edits:
            lines = texts[edit.path]
            lines[edit.line - 1] = _replace_token(lines[edit.line - 1], edit.old, edit.new) or lines[edit.line - 1]
        return texts

    def after_drafts(self) -> dict[Path, list[str]]:
        texts = self.after_edits()
        for draft in sorted((d for d in self.drafts if not d.rejected), key=lambda d: -d.start):
            texts[draft.path][draft.start - 1 : draft.end] = draft.new_lines
        return texts


# --- Layer 1: mechanical fixes ------------------------------------------------------


def plan_fixes(root: Path, history: History, trust_map: TrustMap, changes: list[Change] | None = None,
               only: list[str] | None = None) -> FixPlan:
    root = Path(root).resolve()
    plan = FixPlan(root)
    repository = Repository(root, history)
    renamed = {c.old_path: c.path for c in changes or [] if c.status in "RC" and c.old_path}
    wanted = set(only or [])
    for instruction in discover(root):
        if instruction.alias_of or instruction.generated_from:
            continue  # fixed in its source
        text = _read(instruction.path)
        if text is None or ROUTER_MARK in text:
            continue
        lines = text.split("\n")
        titles = sections(text)
        for reference in references(instruction, repository, text).references:
            title = next((t for t, s, e in titles if s <= reference.line <= e), None)
            unit = _unit_name(instruction.path, root, title)
            if wanted and unit not in wanted:
                continue
            fix = _fix_reference(reference, instruction, root, history, renamed)
            if isinstance(fix, tuple):
                old, new, reason = fix
                if _replace_token(lines[reference.line - 1], old, new) is not None:
                    plan.originals.setdefault(instruction.path, list(lines))
                    plan.edits.append(Edit(instruction.path, reference.line, old, new, unit, "instruction", reason))
                    continue
                fix = f"{reason}, but the line could not be edited exactly"
            if fix:
                plan.manual.append(Manual(instruction.path, reference.line, unit, fix))
    for path, bundle_root in _concepts(root, None):
        unit = _relative(path, root)
        if wanted and unit not in wanted:
            continue
        _plan_knowledge(plan, path, bundle_root, unit, root, history)
    return plan


def _fix_reference(reference, instruction: InstructionFile, root: Path, history: History,
                   renamed: dict[str, str]) -> tuple[str, str, str] | str | None:
    """(old, new, why) for a mechanical fix, a reason when a person must fix it, None when nothing is wrong."""
    if reference.path is not None and reference.status in ("moved", "broken"):
        target = None
        if reference.status == "moved":
            target, source = reference.moved_to, reference.moved_from
        else:
            for candidate in reference.candidates:
                new = renamed.get(history.relative(candidate) or "")
                if new and history.root:
                    target, source = history.root / new, candidate
                    break
        if target is not None:
            new_text = _rewrite_path(reference.path, source, target, instruction, root)
            return reference.path, new_text, f"{reference.path} moved to {new_text}"
        return f"{reference.missing}: needs a manual fix"
    if reference.type == "npm-script" and reference.problem and "no script" in reference.problem:
        new_name = renamed_script(history, reference.manifest, reference.name)
        if new_name:
            return reference.name, new_name, f'script "{reference.name}" is now "{new_name}" in package.json'
        return f"{reference.problem}: needs a manual fix"
    if reference.missing:
        return f"{reference.missing}: needs a manual fix"
    return None


def _plan_knowledge(plan: FixPlan, path: Path, bundle_root: Path, unit: str, root: Path, history: History) -> None:
    doc = load_document(path, bundle_root)
    if doc.meta is None:
        return
    lines = doc.text.split("\n")
    end = front_matter_end(lines)
    for resource in schema.sources(doc):
        if any(ch.isspace() for ch in resource):
            continue
        candidates = [root / p for p in resource_paths(resource, doc, bundle_root, root)]
        if not candidates or any(c.exists() for c in candidates):
            continue
        line = next((i + 1 for i in range(1, end) if "resource" in lines[i] and resource in lines[i]), 1)
        moved = next(((c, m) for c in candidates if (m := history.moved(c))), None)
        if moved is None:
            plan.manual.append(Manual(path, line, unit, f'source "{resource}" does not exist: needs a manual fix'))
            continue
        candidate, (target, _) = moved
        new_text = _rewrite_path(resource, candidate, target, InstructionFile(path, path.parent), bundle_root)
        if _replace_token(lines[line - 1], resource, new_text) is None:
            plan.manual.append(Manual(path, line, unit, f'source "{resource}" moved to {new_text}: edit it by hand'))
            continue
        plan.originals.setdefault(path, list(lines))
        plan.edits.append(Edit(path, line, resource, new_text, unit, "knowledge", f"source {resource} moved to {new_text}"))


def _rewrite_path(old: str, source: Path, target: Path, instruction: InstructionFile, root: Path) -> str:
    """The new path, written the way the old one was: from the same base, with `./` or a trailing `/`."""
    if old.startswith("/"):
        new = "/" + _relative(target, root)
    else:
        parts = [p for p in PurePosixPath(old.rstrip("/")).parts if p != "."]
        if ".." in parts:
            base = instruction.path.parent
        else:
            base = Path(source)
            for _ in parts:
                base = base.parent
        new = _relative(target, base)
        if old.startswith("./") and not new.startswith("../"):
            new = "./" + new
    if old.endswith("/") and not new.endswith("/"):
        new += "/"
    return new


def renamed_script(history: History, manifest: Path | None, name: str) -> str | None:
    """The script's new name if git history shows it renamed: the same command now under one other name."""
    if not history.dated or manifest is None or not name:
        return None
    relative = history.relative(manifest)
    current = _scripts(_read(manifest))
    for commit in commits_changing_count(history.root, json.dumps(name), relative):
        before = _scripts(file_at(history.root, f"{commit}^", relative))
        after = _scripts(file_at(history.root, commit, relative))
        if name in before and name not in after:
            same = [key for key, command in current.items() if command == before[name] and key != name]
            return same[0] if len(same) == 1 else None
    return None


def _scripts(text: str | None) -> dict[str, str]:
    try:
        data = json.loads(text or "")
    except ValueError:
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return scripts if isinstance(scripts, dict) else {}


def _replace_token(line: str, old: str, new: str) -> str | None:
    """`line` with the first whole `old` (not part of a longer path) replaced, or None if there is none.

    The name must not go on: `src/config.py` is not inside `src/config.py.bak` or `src/config.py_old`,
    but a full stop that ends a sentence is not part of it."""
    pattern = re.compile(rf"(?<![\w./@-]){re.escape(old)}(?![\w/-]|\.[\w/-])( {{2,}})?")

    def replace(match: re.Match) -> str:
        padding = match.group(1)  # keep a column of aligned comments aligned
        return new + (" " * max(2, len(padding) + len(old) - len(new)) if padding else "")

    result, count = pattern.subn(replace, line, count=1)
    return result if count else None


# --- Layer 2: drafts from an LLM ------------------------------------------------------


class Provider:
    actor = ""

    def complete(self, system: str, prompt: str, unit: str, schema: dict | None = None) -> dict:
        """The model's JSON answer; `schema` (default: a section draft) shapes it where the API can."""
        raise NotImplementedError


class AnthropicProvider(Provider):
    """Claude through the official SDK (`pip install 'okf-ai[llm]'`)."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, max_tokens: int = 8000):
        self.api_key, self.model, self.max_tokens = api_key, model, max_tokens
        self.actor = _actor("anthropic", model)

    def complete(self, system: str, prompt: str, unit: str, schema: dict | None = None) -> dict:
        try:
            import anthropic
        except ImportError as exc:
            raise FixError("drafts with Claude need the anthropic package: pip install 'okf-ai[llm]'") from exc
        client = anthropic.Anthropic(api_key=self.api_key)
        extra = {}
        if self.model in FALLBACK_MODELS:  # a declined request is re-run on a fallback model server-side
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            response = client.beta.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema or DRAFT_SCHEMA}},
                **extra,
            )
        except anthropic.AuthenticationError as exc:
            raise FixError("the Anthropic API rejected ANTHROPIC_API_KEY") from exc
        except anthropic.RateLimitError as exc:
            raise FixError("rate limited by the Anthropic API, retry later") from exc
        except anthropic.APIStatusError as exc:
            raise FixError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise FixError("cannot reach the Anthropic API") from exc
        if response.stop_reason == "refusal":
            raise FixError("the model declined to draft this section")
        if response.stop_reason == "max_tokens":
            raise FixError(f"the draft hit the token limit ({self.max_tokens}); raise OKF_LLM_MAX_TOKENS")
        return _parse_answer("".join(block.text for block in response.content if block.type == "text"))


class OpenAICompatibleProvider(Provider):
    """Any OpenAI-compatible chat completions endpoint, through the standard library."""

    def __init__(self, base_url: str, api_key: str, model: str, max_tokens: int = 8000):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key, self.model, self.max_tokens = api_key, model, max_tokens
        self.actor = _actor("openai-compatible", model)

    def complete(self, system: str, prompt: str, unit: str, schema: dict | None = None) -> dict:
        body = json.dumps({
            "model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise FixError(f"{self.url} answered {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise FixError(f"cannot get an answer from {self.url}: {exc}") from exc
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise FixError(f"the draft hit the token limit ({self.max_tokens}); raise OKF_LLM_MAX_TOKENS")
            return _parse_answer(choice["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise FixError(f"unexpected answer from {self.url}") from exc


class ReplayProvider(Provider):
    """A saved model answer instead of a call: for demos without a key and for tests."""

    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.answers = data.get("units", {})
        self.actor = _actor(data.get("provider", "replay"), data.get("model", "saved-answer"))

    def complete(self, system: str, prompt: str, unit: str, schema: dict | None = None) -> dict:
        if unit not in self.answers and unit.startswith("base:"):
            unit = unit[len("base:"):]  # the same saved answer for the base branch, unless it has its own
        if unit not in self.answers:
            raise FixError(f"the saved answers have nothing for {unit}")
        return self.answers[unit]


def provider_from_env(env: dict | None = None) -> Provider | None:
    env = os.environ if env is None else env
    max_tokens = int(env.get("OKF_LLM_MAX_TOKENS") or 8000)
    if env.get("OKF_LLM_BASE_URL") and env.get("OKF_LLM_API_KEY") and env.get("OKF_LLM_MODEL"):
        return OpenAICompatibleProvider(env["OKF_LLM_BASE_URL"], env["OKF_LLM_API_KEY"], env["OKF_LLM_MODEL"],
                                        max_tokens)
    if env.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider(env["ANTHROPIC_API_KEY"], env.get("OKF_LLM_MODEL") or DEFAULT_MODEL, max_tokens)
    return None


def plan_drafts(plan: FixPlan, trust_map: TrustMap, history: History, provider: Provider,
                only: list[str] | None = None, base_commit: str | None = None, max_diff: int = 40000,
                sources: Registry | None = None) -> None:
    """Ask the model for every section whose code changed since it was confirmed (or, in a pull
    request, in this change), and keep only drafts that pass the checks. What changed comes from
    the connectors: `git diff` for files, page versions for Confluence, the changelog for Jira."""
    wanted = set(only or [])
    repository = Repository(plan.root, history)
    sources = sources if sources is not None else registry(root=plan.root, history=history)
    git = sources.git if sources.git.history is not None else registry(root=plan.root, history=history).git
    for unit in trust_map.units:
        if unit.reason not in DRAFT_REASONS or (wanted and unit.name not in wanted):
            continue
        texts = plan.after_edits()
        if unit.path not in texts:
            text = _read(unit.path)
            if text is None:
                continue
            plan.originals[unit.path] = text.split("\n")
            texts[unit.path] = text.split("\n")
        lines = texts[unit.path]
        start, end = (unit.line, unit.end) if unit.kind == "instruction" else (front_matter_end(lines) + 1, len(lines))
        draft = Draft(unit.path, unit.name, unit.kind, start, end, by=provider.actor)
        plan.drafts.append(draft)
        changed = sorted({p for p, _ in unit.changed} | set(unit.in_change))
        relatives = [r for p in changed if (r := history.relative(plan.root / p))]
        moment = max(unit.verifications)[0] if unit.verifications else unit.last_edited
        if unit.generated_at and (moment is None or unit.generated_at > moment):
            moment = unit.generated_at  # okf import or an earlier draft wrote it: what changed after that
        if base_commit and unit.in_change:
            since_commit, since = base_commit, "the base of this change"
        else:
            since_commit = moment or base_commit or ""
            since = moment.astimezone(timezone.utc).date().isoformat() if moment else "the beginning"
        diff = (git.changes_since(relatives, since_commit) or "") if relatives else ""
        remote = [r for r in unit.remote if r.signal and (moment is None or r.signal.at > moment)]
        for check in remote:
            text = sources.changes_since(check.resource, moment) if moment else None
            if text:
                diff += ("\n\n" if diff else "") + text
                changed.append(check.message)
        if not diff.strip():
            draft.rejected = "no diff of the changed sources to show the model"
            continue
        if len(diff) > max_diff:
            draft.rejected = f"the diff is {len(diff)} characters, over --max-diff {max_diff}; not sent"
            continue
        section = "\n".join(lines[start - 1 : end])
        prompt = (f"Instruction file: {_relative(unit.path, plan.root)}\n\n<section>\n{section}\n</section>\n\n"
                  f"Sources it mentions that changed: {', '.join(changed)}\n\n"
                  f"What changed in them since {since}:\n<diff>\n{diff}\n</diff>")
        try:
            answer = provider.complete(SYSTEM_PROMPT, prompt, unit.name)
        except FixError as exc:
            draft.rejected = str(exc)
            continue
        _check_draft(draft, answer, lines, unit, repository)


def _check_draft(draft: Draft, answer: dict, lines: list[str], unit, repository: Repository) -> None:
    old = lines[draft.start - 1 : draft.end]
    new_text = answer.get("section") if isinstance(answer, dict) else None
    if not isinstance(new_text, str) or not new_text.strip():
        draft.rejected = "the model returned no section"
        return
    new = new_text.rstrip("\n").split("\n")
    while new and not new[-1].strip():
        new.pop()
    blank = next((i for i, line in enumerate(reversed(old)) if line.strip()), 0)
    new += [""] * blank  # keep the empty lines that separate this section from the next one
    draft.summary = str(answer.get("summary") or "").strip().replace("\n", " ")
    if answer.get("changed") is False or [l.rstrip() for l in new] == [l.rstrip() for l in old]:
        draft.rejected = "the model says the section is still correct: confirm it with okf verify"
        return
    heading = next((l for l in old if l.strip()), "")
    if heading.startswith("#") and new[0].strip() != heading.strip():
        draft.rejected = f'the draft changed the heading to "{new[0].strip()}"'
        return
    if len(new_text) > 3 * len("\n".join(old)) + 2000:
        draft.rejected = "the draft is much longer than the section"
        return
    instruction = InstructionFile(unit.path, repository.root if unit.kind == "instruction" else unit.path.parent)
    scope = next((f.scope for f in discover(repository.root) if f.path == unit.path), None)
    if scope is not None:
        instruction = InstructionFile(unit.path, scope)
    known = {r.subject for r in references(instruction, repository, "\n".join(lines)).references
             if draft.start <= r.line <= draft.end}
    candidate = lines[: draft.start - 1] + new + lines[draft.end:]
    last = draft.start + len(new) - 1
    invented = [r.subject for r in references(instruction, repository, "\n".join(candidate)).references
                if draft.start <= r.line <= last and r.status in ("broken", "moved", "unclear") and r.subject not in known]
    if invented:
        draft.rejected = f"the draft mentions {', '.join(sorted(set(invented)))}, which does not exist"
        return
    draft.new_lines = new


# --- Output and applying ----------------------------------------------------------------


def render(plan: FixPlan) -> tuple[str, str]:
    """Unified diffs: the mechanical fixes, then the drafts on top of them."""
    edits, drafts = plan.after_edits(), plan.after_drafts()
    return (_diff(plan, plan.originals, edits), _diff(plan, edits, drafts))


def _diff(plan: FixPlan, before: dict[Path, list[str]], after: dict[Path, list[str]]) -> str:
    out = []
    for path in sorted(after):
        if before.get(path) != after[path]:
            name = _relative(path, plan.root)
            out.extend(difflib.unified_diff(before[path], after[path], f"a/{name}", f"b/{name}", lineterm=""))
    return "\n".join(out) + ("\n" if out else "")


def apply(plan: FixPlan, git_root: Path | None, now: datetime | None = None) -> list[str]:
    """Write the fixes and record every rewritten unit as generated, not verified. Returns unit names."""
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    final = plan.after_drafts()
    by_unit: dict[str, tuple[Path, str, str]] = {}
    for edit in plan.edits:
        by_unit.setdefault(edit.unit, (edit.path, edit.kind, FIX_ACTOR))
    for draft in plan.drafts:
        if not draft.rejected:
            by_unit[draft.unit] = (draft.path, draft.kind, draft.by)
    for path, lines in final.items():
        if lines == plan.originals.get(path):
            continue
        knowledge = [actor for p, kind, actor in by_unit.values() if p == path and kind == "knowledge"]
        if knowledge:
            lines = set_generated(lines, knowledge[-1], stamp)
        raw = path.read_bytes()
        newline = "\r\n" if b"\r\n" in raw else "\n"
        path.write_text("\n".join(lines), encoding="utf-8", newline=newline)
    sidecars: dict[Path, Sidecar] = {}
    for unit, (path, kind, actor) in by_unit.items():
        if kind != "instruction":
            continue
        found = find_sidecar(path.parent, git_root)
        sidecar_path = found or (git_root or plan.root) / SIDECAR
        sidecar = sidecars.setdefault(sidecar_path, Sidecar(sidecar_path))
        text = path.read_text(encoding="utf-8")
        title = unit.split("#", 1)[1] if "#" in unit else None
        span = next(((s, e) for t, s, e in sections(text) if t == title), None)
        if span is None:
            continue
        sidecar.generated(_unit_name(path, sidecar.base, title), actor, stamp,
                          section_hash(text.split("\n")[span[0] - 1 : span[1]]))
    for sidecar in sidecars.values():
        sidecar.save()
    return list(by_unit)


def _parse_answer(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise FixError("the model did not answer with JSON") from exc
    if not isinstance(data, dict):
        raise FixError("the model did not answer with a JSON object")
    return data


def _actor(producer: str, model: str) -> str:
    """`<producer>/<version>` (OKF §7) from a model id that may itself contain / or :."""
    version = re.sub(r"[\s/:]+", "-", model.strip()) or "unknown"
    return f"{re.sub(r'[^A-Za-z0-9_.-]+', '-', producer)}/{version}"


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
