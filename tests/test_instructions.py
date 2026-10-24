"""`okf agents-check`: instructions for AI agents against the code."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from okf.git import Change, changes_since
from okf.instructions import analyze, check_repository, discover, mentions, split_commands

WARN, ERR, INFO = "WARNING", "ERROR", "INFO"
PACKAGE = json.dumps({"scripts": {"dev": "vite", "test": "vitest", "lint": "eslint ."}})


@pytest.fixture
def repo(make_bundle):
    """A repository factory: {path: text} -> root."""
    return make_bundle


def check(root, strict=False, changes=None):
    root = Path(root).resolve()
    report = check_repository(root, strict, changes, root)
    return [(i.level, i.path.relative_to(root).as_posix(), i.field, i.message) for i in report.issues]


def short(issues):
    return [(level, path, field) for level, path, field, _ in issues]


# --- finding instruction files ---


def test_discovers_every_kind_of_instruction_file(repo):
    root = repo({
        "AGENTS.md": "", "CLAUDE.md": "", ".cursorrules": "", ".github/copilot-instructions.md": "",
        ".cursor/rules/backend.mdc": "", ".cursor/rules/web/react.mdc": "", "packages/web/AGENTS.md": "",
        "packages/web/.cursor/rules/ui.mdc": "", "docs/README.md": "", ".cursor/settings.json": "",
        "node_modules/x/AGENTS.md": "", ".git/AGENTS.md": "", ".venv/CLAUDE.md": "", ".hidden/AGENTS.md": "",
    })
    found = {f.path.relative_to(root).as_posix(): f.scope.relative_to(root).as_posix() for f in discover(root)}
    assert found == {
        "AGENTS.md": ".", "CLAUDE.md": ".", ".cursorrules": ".", ".github/copilot-instructions.md": ".",
        ".cursor/rules/backend.mdc": ".", ".cursor/rules/web/react.mdc": ".", "packages/web/AGENTS.md": "packages/web",
        "packages/web/.cursor/rules/ui.mdc": "packages/web",
    }


# --- pulling out paths and commands ---


def found(text, claude=False):
    return [(m.kind, m.text, m.line) for m in mentions(text, claude)]


def test_paths_from_code_links_and_prose():
    text = (
        "Edit `src/auth.py:42` and `src/api/#L3`.\n"
        "Schema: [schema](db/schema.sql#tables), [web](https://example.com/a.md), [top](#intro).\n"
        "Config lives in src/config.py, see ./scripts/seed.sh.\n"
    )
    assert found(text) == [
        ("path", "src/auth.py", 1),
        ("path", "src/api/", 1),
        ("path", "db/schema.sql", 2),
        ("path", "src/config.py", 3),
        ("path", "./scripts/seed.sh", 3),
    ]


def test_bare_prose_paths_are_loose_code_paths_are_not():
    [prose, code] = mentions("see src/auth.py\n`docs/x.md`\n")
    assert (prose.text, prose.loose) == ("src/auth.py", True)
    assert (code.text, code.loose) == ("docs/x.md", False)


@pytest.mark.parametrize(
    "text",
    ["and/or", "CI/CD", "50/50", "10/22/2026", "https://github.com/a/b.md", "github.com/a/b", "@types/node",
     "/etc/hosts", "~/notes.md", "<name>/x.md", "e.g./i.e.", "`git commit -m 'fix/feat'`", "`POST /rides`"],
)
def test_not_paths(text):
    assert [m for m in mentions(text) if m.kind == "path" and not m.loose] == []


def test_commands_from_shell_blocks_and_inline_code():
    text = (
        "Run `npm run dev` or `make test`, not `make` the word.\n"
        "```bash\n"
        "$ npm install\n"
        "# a comment\n"
        "FOO=1 ./scripts/seed.sh   # seed\n"
        "```\n"
        "```python\n"
        "import src.auth  # python/code.py is not a command\n"
        "```\n"
        "```\n"
        "pytest tests/\n"
        "```\n"
    )
    assert [(m.text, m.line) for m in mentions(text) if m.kind == "command"] == [
        ("npm run dev", 1),
        ("make test", 1),
        ("make", 1),
        ("npm install", 3),
        ("FOO=1 ./scripts/seed.sh   # seed", 5),
        ("pytest tests/", 11),
    ]


def test_claude_imports():
    text = "See @docs/agents.md and @AGENTS.md, mail me@example.com, not `@scope/pkg`.\n"
    assert found(text, claude=True) == [("path", "docs/agents.md", 1), ("path", "AGENTS.md", 1)]
    assert found(text, claude=False) == []


def test_cursor_front_matter_is_skipped():
    text = "---\ndescription: x\nglobs: src/**/*.ts, `tests/x.ts`\n---\nUse `src/app.ts`.\n"
    assert found(text) == [("path", "src/app.ts", 5)]


# --- understanding commands ---


def targets(command, cwd=Path("/r")):
    result = []
    for words in split_commands(command):
        found_targets, cwd = analyze(words, cwd)
        result.extend((t.kind, t.name, t.cwd.as_posix(), t.runner) for t in found_targets)
    return result


@pytest.mark.parametrize(
    "command,expected",
    [
        ("npm run test:unit -- --watch", [("script", "test:unit", "/r", "npm")]),
        ("npm test", [("script", "test", "/r", "npm")]),
        ("npm t", [("script", "test", "/r", "npm")]),
        ("npm install && npm ci", []),
        ("npm -w web run build", []),
        ("npm --prefix web run build", [("script", "build", "/r/web", "npm")]),
        ("pnpm install", []),
        ("pnpm lint", [("script", "lint", "/r", "pnpm")]),
        ("pnpm --filter web dev", []),
        ("pnpm -C web dev", [("script", "dev", "/r/web", "pnpm")]),
        ("yarn", []),
        ("yarn build", [("script", "build", "/r", "yarn")]),
        ("yarn workspace web build", []),
        ("yarn --cwd web dev", [("script", "dev", "/r/web", "yarn")]),
        ("bun run dev", [("script", "dev", "/r", "bun")]),
        ("bun test", []),
        ("bun run scripts/x.ts", [("file", "scripts/x.ts", "/r", "bun")]),
        ("cd web && pnpm dev", [("script", "dev", "/r/web", "pnpm")]),
        ("FOO=1 npm run dev", [("script", "dev", "/r", "npm")]),
        ("make -C db migrate seed", [("make", "migrate", "/r/db", "make"), ("make", "seed", "/r/db", "make")]),
        ("make -j 4 VAR=1 test", [("make", "test", "/r", "make")]),
        ("make", []),
        ("sudo make install", [("make", "install", "/r", "make")]),
        ("just test fast", [("just", "test", "/r", "just")]),
        ("just --list", []),
        ("pytest tests/test_a.py::test_x -k 'a or b' -q", [("file", "tests/test_a.py", "/r", "pytest")]),
        ("python -m pytest tests/", [("file", "tests/", "/r", "pytest")]),
        ("py -3.12 -m pytest", []),
        ("uv run pytest tests/x.py", [("file", "tests/x.py", "/r", "pytest")]),
        ("python manage.py migrate", [("file", "manage.py", "/r", "python")]),
        ("python -m http.server", []),
        ("python3 -c 'print(1)'", []),
        ("./scripts/seed.sh --fast", [("file", "./scripts/seed.sh", "/r", "./scripts/seed.sh")]),
        ("bash scripts/x.sh", [("file", "scripts/x.sh", "/r", "bash")]),
        ("node scripts/build.js | tee log", [("file", "scripts/build.js", "/r", "node")]),
        ("npx prettier .", []),
        ("echo 'unbalanced", []),
    ],
)
def test_analyze(command, expected):
    assert targets(command) == expected


# --- checks: paths ---


def test_existing_paths_pass(repo):
    root = repo({
        "AGENTS.md": "`src/auth.py`, [schema](/db/schema.sql), `src/`, src/billing.py, `src/*.py`\n",
        "src/auth.py": "", "src/billing.py": "", "db/schema.sql": "",
    })
    assert check(root) == []


def test_missing_path_is_warning_or_error_in_strict(repo):
    root = repo({"AGENTS.md": "Config: `src/config.py`.\n", "src/auth.py": ""})
    assert check(root) == [(WARN, "AGENTS.md", "path", '"src/config.py" does not exist (line 1)')]
    assert short(check(root, strict=True)) == [(ERR, "AGENTS.md", "path")]


def test_unreadable_file_is_warning_or_error_in_strict(repo, capsys):
    from okf.cli import main

    root = repo({"src/auth.py": ""})
    (root / "AGENTS.md").write_bytes("Вход: `src/auth.py`\n".encode("cp1251"))
    assert short(check(root)) == [(WARN, "AGENTS.md", "file")]
    assert short(check(root, strict=True)) == [(ERR, "AGENTS.md", "file")]
    assert main(["agents-check", str(root)]) == 0 and main(["agents-check", str(root), "--strict"]) == 1
    capsys.readouterr()


def test_prose_path_counts_only_under_an_existing_directory(repo):
    root = repo({"AGENTS.md": "Use src/old.py, not client/server.js or Node.js/React.\n", "src/auth.py": ""})
    assert short(check(root)) == [(WARN, "AGENTS.md", "path")]


def test_paths_resolve_from_file_scope_and_root(repo):
    root = repo({
        "packages/web/AGENTS.md": "`src/app.ts` and `packages/shared/x.ts` and [up](../shared/x.ts)\n",
        "packages/web/src/app.ts": "", "packages/shared/x.ts": "",
        ".cursor/rules/a.mdc": "Edit `packages/web/src/app.ts`.\n",
    })
    assert check(root) == []


def test_glob_must_match(repo):
    root = repo({"AGENTS.md": "`src/**/*.py` and `legacy/*.js`\n", "src/a/b.py": "", "legacy/readme.md": ""})
    assert check(root) == [(WARN, "AGENTS.md", "path", '"legacy/*.js" matches no files (line 1)')]


def test_cursor_globs_must_match(repo):
    root = repo({".cursor/rules/a.mdc": "---\nglobs: src/**/*.py, web/**/*.tsx\n---\nRules.\n", "src/x.py": ""})
    assert check(root) == [(WARN, ".cursor/rules/a.mdc", "globs", '"web/**/*.tsx" matches no files (line 2)')]


def test_claude_import_must_exist(repo):
    root = repo({"CLAUDE.md": "@docs/agents.md\n@AGENTS.md\n", "AGENTS.md": "Rules.\n"})
    assert check(root) == [(WARN, "CLAUDE.md", "path", '"docs/agents.md" does not exist (line 1)')]


# --- checks: commands ---


def test_npm_scripts(repo):
    root = repo({"AGENTS.md": "`npm run dev`, `npm test`, `npm run test:unit`\n", "package.json": PACKAGE})
    assert check(root) == [
        (WARN, "AGENTS.md", "command", '"npm run test:unit": no script "test:unit" in package.json (line 1)')
    ]


def test_nearest_package_json(repo):
    root = repo({
        "package.json": PACKAGE,
        "web/package.json": json.dumps({"scripts": {"storybook": "x"}}),
        "web/AGENTS.md": "`npm run storybook` and `npm run dev`\n",
        "AGENTS.md": "`cd web && npm run storybook`\n",
    })
    assert short(check(root)) == [(WARN, "web/AGENTS.md", "command")]


def test_missing_or_broken_package_json(repo):
    assert "no package.json found" in check(repo({"AGENTS.md": "`npm run dev`\n"}))[0][3]
    root = repo({"AGENTS.md": "`npm run dev`\n", "package.json": "{oops"})
    assert "is not valid JSON" in check(root)[0][3]


def test_shorthand_binaries_and_npm_start_fallback(repo):
    package = json.dumps({"scripts": {}, "devDependencies": {"vitest": "1"}})
    root = repo({"AGENTS.md": "`pnpm vitest`, `npm start`\n", "package.json": package, "pnpm-lock.yaml": "",
                 "server.js": ""})
    assert short(check(root)) == [(WARN, "AGENTS.md", "command")]  # npm in a pnpm project
    assert "this project uses pnpm (pnpm-lock.yaml)" in check(root)[0][3]


def test_package_manager_field(repo):
    package = json.dumps({"packageManager": "yarn@4.1.0", "scripts": {"dev": "x"}})
    root = repo({"AGENTS.md": "`yarn dev` then `npm run dev`\n", "package.json": package})
    [issue] = check(root)
    assert issue[3] == '"npm run dev": this project uses yarn ("packageManager" in package.json) (line 1)'


def test_make_targets(repo):
    makefile = ".PHONY: test\ntest lint: deps\n\tpytest\nVERSION := 1\nbuild::\n\techo\n"
    root = repo({"AGENTS.md": "`make test`, `make lint build`, `make deploy`, `make VERSION`\n", "Makefile": makefile})
    assert [i[3] for i in check(root)] == [
        '"make deploy": no target "deploy" in Makefile (line 1)',
        '"make VERSION": no target "VERSION" in Makefile (line 1)',
    ]


@pytest.mark.parametrize("makefile", ["include common.mk\n", "%:\n\t@echo $@\n"])
def test_make_targets_we_cannot_see_are_not_reported(repo, makefile):
    assert check(repo({"AGENTS.md": "`make deploy`\n", "Makefile": makefile})) == []


def test_missing_makefile(repo):
    assert "no Makefile found" in check(repo({"AGENTS.md": "`make test`\n"}))[0][3]


def test_just_recipes(repo):
    justfile = "alias t := test\ntest filter='':\n    pytest {{filter}}\n@lint:\n    ruff .\nversion := '1'\n"
    root = repo({"AGENTS.md": "`just test`, `just t`, `just lint`, `just deploy`, `just version`\n",
                 "justfile": justfile})
    assert [i[3] for i in check(root)] == [
        '"just deploy": no recipe "deploy" in justfile (line 1)',
        '"just version": no recipe "version" in justfile (line 1)',
    ]


def test_script_files(repo):
    text = "```bash\n./scripts/seed.sh\npytest tests/test_a.py tests/test_gone.py\npython tools/gen.py\ncd web && ./build.sh\n```\n"
    root = repo({"AGENTS.md": text, "scripts/seed.sh": "", "tests/test_a.py": "", "web/build.sh": ""})
    assert [i[3] for i in check(root)] == [
        '"pytest tests/test_a.py tests/test_gone.py": tests/test_gone.py does not exist (line 3)',
        '"python tools/gen.py": tools/gen.py does not exist (line 4)',
    ]


def test_strict_makes_command_problems_errors(repo):
    root = repo({"AGENTS.md": "`npm run nope`\n", "package.json": PACKAGE})
    assert short(check(root, strict=True)) == [(ERR, "AGENTS.md", "command")]


# --- AGENTS.md vs CLAUDE.md ---


def test_agents_and_claude_disagree_on_commands(repo):
    root = repo({
        "AGENTS.md": "`npm test`, `npm run lint`\n",
        "CLAUDE.md": "Run `npm run test:unit` and `npm run lint`.\n",
        "package.json": json.dumps({"scripts": {"test": "x", "test:unit": "y", "lint": "z"}}),
    })
    assert check(root) == [
        (WARN, "CLAUDE.md", "consistency",
         'Instructions for different agents disagree: AGENTS.md runs "npm test", CLAUDE.md runs "npm run test:unit" (line 1)'),
    ]


def test_agents_and_claude_disagree_on_package_manager_and_paths(repo):
    root = repo({
        "AGENTS.md": "`npm run dev`; config in `src/config.py`\n",
        "CLAUDE.md": "`pnpm dev`; config in `src/settings/config.py`\n",
        "package.json": PACKAGE, "src/config.py": "", "src/settings/config.py": "",
    })
    messages = [i[3] for i in check(root)]
    assert messages == [
        "Instructions for different agents disagree: AGENTS.md uses npm, CLAUDE.md uses pnpm (line 1)",
        'Instructions for different agents disagree: AGENTS.md mentions "src/config.py", '
        'CLAUDE.md mentions "src/settings/config.py" (line 1)',
    ]


def test_consistent_or_separate_instructions_do_not_conflict(repo):
    root = repo({
        "AGENTS.md": "`npm test`, `npm run test:unit`\n",
        "CLAUDE.md": "`npm run test:unit`\n",
        "web/CLAUDE.md": "`npm run dev`\n",
        "package.json": json.dumps({"scripts": {"test": "x", "test:unit": "y", "dev": "z"}}),
    })
    assert check(root) == []


# --- changes in a pull request ---


def test_renamed_file_names_the_new_path(repo):
    root = repo({"AGENTS.md": "Config: `src/config.py`.\n", "src/settings.py": ""})
    changes = [Change("R", "src/settings.py", "src/config.py")]
    assert check(root, changes=changes) == [
        (WARN, "AGENTS.md", "path", '"src/config.py" was renamed to src/settings.py in this change (line 1)')
    ]


def test_deleted_file(repo):
    root = repo({"AGENTS.md": "```bash\n./scripts/old.sh\n```\n"})
    assert check(root, changes=[Change("D", "scripts/old.sh")])[0][3] == (
        '"./scripts/old.sh" was deleted or renamed in this change (line 2)'
    )


def test_modified_file_may_outdate_instruction(repo):
    root = repo({"AGENTS.md": "Auth: `src/auth.py`, billing: `src/billing.py`.\n", "src/auth.py": "", "src/billing.py": ""})
    assert check(root, changes=[Change("M", "src/auth.py")]) == [
        (WARN, "AGENTS.md", "path", '"src/auth.py" changed in this change; the instruction may be outdated (line 1)')
    ]
    changes = [Change("M", "src/auth.py"), Change("M", "AGENTS.md")]
    assert short(check(root, changes=changes)) == [(INFO, "AGENTS.md", "path")]


def test_editing_a_linked_document_is_not_a_warning(repo):
    root = repo({"AGENTS.md": "Read [conventions](docs/conventions.md).\n", "docs/conventions.md": "",
                 "docs/old.md": ""})
    assert check(root, changes=[Change("M", "docs/conventions.md")]) == []
    root = repo({"AGENTS.md": "Read [old](docs/old.md).\n"})
    (root / "docs/old.md").unlink()
    assert short(check(root, changes=[Change("D", "docs/old.md")])) == [(WARN, "AGENTS.md", "path")]


def test_changes_are_relative_to_git_root(repo):
    root = repo({"svc/AGENTS.md": "`src/auth.py`\n", "svc/src/auth.py": ""})
    report = check_repository((root / "svc").resolve(), False, [Change("M", "svc/src/auth.py")], root.resolve())
    assert [i.field for i in report.issues] == ["path"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_git_rename_detection_end_to_end(tmp_path):
    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True,
                       capture_output=True)

    (tmp_path / "src").mkdir()
    (tmp_path / "src/config.py").write_text("DEBUG = False\nPORT = 8000\nHOST = 'localhost'\n")
    (tmp_path / "AGENTS.md").write_text("Settings: `src/config.py`.\n")
    git("init", "-q", "-b", "main")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    git("checkout", "-q", "-b", "rename")
    git("mv", "src/config.py", "src/settings.py")

    changes = changes_since(tmp_path, "main")
    assert changes == [Change("R", "src/settings.py", "src/config.py")]
    assert [i.message for i in check_repository(tmp_path, False, changes, tmp_path).issues] == [
        '"src/config.py" was renamed to src/settings.py in this change (line 1)'
    ]
