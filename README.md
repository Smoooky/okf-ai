# okf-ai

**Держит инструкции для ИИ-агентов и знания в формате OKF актуальными вслед за кодом.**

Агенты пишут код по `AGENTS.md`, `CLAUDE.md` и правилам Cursor. Эти файлы стареют молча: скрипт переименовали,
npm-команду убрали, а агент продолжает их вызывать. okf-ai ловит такие расхождения локально и в каждом pull request.

- `okf agents-check` — проверяет инструкции для агентов: упомянутые пути существуют, у `npm run X` есть скрипт,
  у `make X` — цель, `./scripts/x.sh` на месте; `AGENTS.md` и `CLAUDE.md` не противоречат друг другу;
  в PR предупреждает, какие инструкции задел дифф.
- `okf validate` — валидатор базы знаний [OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
  плюс строгий профиль okf-ai ([спека](etc/spec/cli-validator-v2.md));
- `okf stale` — какие документы базы знаний могли устареть после изменения кода;
- `okf agents` — собирает для бандла `AGENTS.md`, компактное оглавление-роутер для агентов;
- [GitHub Action](.github/workflows/okf.yml) — всё это на каждом pull request.

Концепция — в [брифе](etc/docs/BRIEF.md).

## Установка

Нужен Python 3.10+ и Git.

```bash
git clone https://github.com/Smoooky/okf-ai.git
cd okf-ai
pip install -e ".[test]"
```

На Windows вместо `pip` и `python` — `py -3.12 -m pip` и `py -3.12`. Если папка `Scripts` не в `PATH`,
команда `okf` не найдётся; тогда запускайте `py -3.12 -m okf ...` — это то же самое.

Тесты:

```bash
python -m pytest
```

Все команды печатают по строке на проблему, итоговая строка уходит в stderr:

```text
[LEVEL] file_path: field_name: message
```

`--format github` печатает то же как команды GitHub Actions — они становятся аннотациями в PR.

## `okf agents-check [repo] [--strict] [--changed FILE...] [--base REF]`

```text
[WARNING] examples/demo/AGENTS.md: command: "./scripts/seed_db.sh" does not exist (line 14)
[WARNING] examples/demo/CLAUDE.md: command: "npm run test:unit": no script "test:unit" in package.json (line 6)
[WARNING] examples/demo/CLAUDE.md: consistency: Instructions for different agents disagree: AGENTS.md runs "npm test", CLAUDE.md runs "npm run test:unit" (line 6)
```

**Какие файлы.** `AGENTS.md` и `CLAUDE.md` в корне и во вложенных папках, `.cursor/rules/**/*.mdc`, `.cursorrules`,
`.github/copilot-instructions.md`. Пропускаются `node_modules`, `.git`, виртуальные окружения и прочие скрытые папки.

**Что из них достаётся.**
- Пути: в обратных кавычках, в markdown-ссылках, импорты `@path` в `CLAUDE.md`, «голые» пути вида `src/auth.py` в тексте.
  Голый путь считается, только если его первая папка существует, — так `and/or` и `CI/CD` не принимаются за пути.
  Суффиксы `:42` и `#L10` отбрасываются, маски (`src/**/*.py`) должны совпасть хотя бы с одним файлом.
- Команды: из shell-блоков кода и из `` `...` ``: `npm`/`pnpm`/`yarn`/`bun`, `make`, `just`, `pytest путь`,
  `python путь.py`, `./scripts/...`, `bash/node путь`. Понимает `&&`, `|`, `cd dir && ...`, `FOO=1 cmd`, `uv run`/`poetry run`.
- `globs:` в шапке правил Cursor.

**Что проверяется.**

| Проверка | Пример сообщения |
|---|---|
| путь существует (от файла, от его папки, от корня) | `"src/config.py" does not exist` |
| у `npm run X`, `pnpm X`, `yarn X` есть скрипт в ближайшем `package.json` | `no script "test:unit" in package.json` |
| менеджер пакетов совпадает с lock-файлом или `packageManager` | `this project uses pnpm (pnpm-lock.yaml)` |
| у `make X` есть цель в ближайшем `Makefile`, у `just X` — рецепт | `no target "deploy" in Makefile` |
| файл скрипта или теста существует | `"pytest tests/test_gone.py": tests/test_gone.py does not exist` |
| маски и `globs:` Cursor что-то находят | `"web/**/*.tsx" matches no files` |
| `AGENTS.md` и `CLAUDE.md` в одной папке не расходятся: разные команды для одной задачи, разные менеджеры пакетов, разные пути к одноимённому файлу | `AGENTS.md runs "npm test", CLAUDE.md runs "npm run test:unit"` |

По умолчанию всё это WARNING и код выхода `0`; с `--strict` битые пути и команды — ERROR и код `1`
(расхождения между файлами остаются WARNING). Если в `Makefile` есть `include` или шаблонные цели, отсутствие цели не сообщается.

**В pull request** (`--base origin/main` или `--changed файлы...`) дополнительно:
- файл, на который ссылается инструкция, переименован — `"src/config.py" was renamed to src/settings.py in this change`;
- удалён — `was deleted or renamed in this change`;
- изменён — WARNING `changed in this change; the instruction may be outdated`, или INFO, если инструкцию поправили в том же PR.

## `okf validate <bundle> [--strict]`

**По умолчанию — OKF v0.2.** Обязателен только `type`; незнакомые типы и лишние ключи — не ошибка.
Официальные примеры бандлов проходят без ошибок (один лежит в [tests/fixtures](tests/fixtures/okf-official)).

| Правило | Уровень |
|---|---|
| у документа есть YAML-шапка, она парсится и это словарь | ERROR |
| `type` есть, непустая строка | ERROR |
| `sources` — список записей, у каждой есть `resource` | ERROR |
| `generated` содержит `by`; у каждой записи `verified` есть `by` и `at` | ERROR |
| акторы — `human:<id>`, `process:<id>` или `<producer>/<version>` | ERROR |
| `status` — `draft`, `stable` или `deprecated` | ERROR |
| `stale_after`, все `at`, `last_modified`, `usage_window` — ISO 8601 с UTC-смещением | ERROR |
| `Attested Computation` содержит `runtime` | ERROR |
| у `index.md` нет шапки (корневой может содержать только `okf_version`) | ERROR |
| `tags` — YAML-список строк | WARNING |
| даты в заголовках `log.md` — `YYYY-MM-DD` | WARNING |
| markdown-ссылки ведут на существующие файлы | WARNING |

**`--strict` — правила okf-ai** поверх OKF:

| Правило | Уровень |
|---|---|
| `sources` непустой | ERROR |
| `verified` есть | ERROR |
| `stale_after` есть и не раньше последней `verified[].at` | ERROR |
| документ, который написал не человек (`generated.by` — агент или процесс), может быть `stable`, только если в `verified` есть `human:` | ERROR |
| `tags` — YAML-список строк | ERROR |
| у `log.md` нет шапки | ERROR |
| `type` из [словаря команды](etc/spec/cli-validator-v2.md#приложение-2-словарь-type-для---strict) | WARNING |
| на документ ссылается хотя бы один другой файл (нет «сирот») | WARNING |

Поля первой версии командной спеки (`provenance.sources`, `trust.confidence`, `freshness.*`) для OKF — лишние ключи;
`--strict` подскажет, на что их заменить. Таблица соответствия — в [спеке v2](etc/spec/cli-validator-v2.md#приложение-3-поля-v1--okf-v02).

## `okf stale <bundle> [--changed FILE...] [--base REF]`

Сопоставляет изменённые файлы с `sources[].resource` документов:

```text
[WARNING] examples/demo/knowledge/auth_flow.md: sources: Source ../src/auth.py changed (examples/demo/src/auth.py); document may be outdated, ask human:teamlead_ivan to review it
```

- `resource`: `/path` — от корня бандла; `./path`, `../path` — от файла; `path` — от файла или от корня бандла
  (так пишут официальные примеры); `https://github.com/<owner>/<repo>/blob/<ref>/<path>` — файл этого репозитория.
  Папка ловит изменения внутри, маска — подходящие файлы.
- Документ изменён вместе с источником — `[INFO] ... document was updated in the same change`.
- Отдельно помечает документы, у которых наступил `stale_after`; `--now 2027-03-01` «перематывает время».
- Код выхода всегда `0`, `2` — если не удалось вызвать git.

## `okf agents <bundle>`

Пишет `<bundle>/AGENTS.md`: короткую инструкцию и таблицу документов — заголовок с описанием, `type`, `tags`,
свежесть, уровень доверия (`human-reviewed` / `machine-confirmed` / `unverified`) и путь. Агент читает роутер
и открывает только нужные файлы. Пример — [examples/demo/knowledge/AGENTS.md](examples/demo/knowledge/AGENTS.md).
У роутера есть OKF-шапка (`type: Agent Router`), так что бандл остаётся валидным и для чужих инструментов.
`-o -` — в stdout, `--check` — код `1`, если файл устарел, `--now` — посчитать свежесть на другой момент.

## GitHub Action

[`.github/workflows/okf.yml`](.github/workflows/okf.yml) на каждый pull request и push в `main`:

1. pytest;
2. `okf agents-check $OKF_REPO --base origin/<базовая ветка>` — инструкции агентов;
3. `okf validate $OKF_BUNDLE --strict` и `okf stale --base ...` — база знаний;
4. отчёт в лог, в job summary и аннотациями на строки; в PR из этого же репозитория — обновляемым комментарием.

Ошибки валят проверку, предупреждения — нет. Чтобы подключить к своему репозиторию, скопируйте файл
и поменяйте `OKF_REPO` (обычно `.`) и `OKF_BUNDLE`; `OKF_AGENTS_ARGS: --strict` сделает битые ссылки в инструкциях ошибками.

## Демо

[`examples/demo`](examples/demo) — мини-репозиторий выдуманного сервиса аренды самокатов Wheelo:
`AGENTS.md` и `CLAUDE.md` для агентов, правило Cursor, `package.json`, `Makefile`, `scripts/`, код в `src/`
и база знаний в `knowledge/` (9 документов OKF). В [`examples/demo-pr`](examples/demo-pr) — заготовки изменений,
в [`examples/broken`](examples/broken) — по файлу на каждую ошибку валидатора.

### Часть 1. Инструкции агентов (1 минута)

**a. Инструкции уже разошлись с кодом:**

```bash
okf agents-check examples/demo
```

```text
[WARNING] examples/demo/AGENTS.md: command: "./scripts/seed_db.sh" does not exist (line 14)
[WARNING] examples/demo/CLAUDE.md: command: "npm run test:unit": no script "test:unit" in package.json (line 6)
[WARNING] examples/demo/CLAUDE.md: consistency: Instructions for different agents disagree: AGENTS.md runs "npm test", CLAUDE.md runs "npm run test:unit" (line 6)
```

Скрипт давно переименован в `seed.sh`, а `AGENTS.md` об этом не знает; Claude Code и Codex гоняют разные тесты.

**b. PR переименовывает файл настроек:**

```bash
git switch -c demo/rename-config
git mv examples/demo/src/config.py examples/demo/src/settings.py
okf agents-check examples/demo --base main
okf stale examples/demo/knowledge --base main
```

```text
[WARNING] examples/demo/AGENTS.md: path: "src/config.py" was renamed to src/settings.py in this change (line 22)
[WARNING] examples/demo/CLAUDE.md: path: "src/config.py" was renamed to src/settings.py in this change (line 8)
[WARNING] examples/demo/knowledge/local_setup_guide.md: sources: Source ../src/config.py changed (examples/demo/src/config.py); document may be outdated, ask human:teamlead_ivan to review it
```

В GitHub то же самое приходит аннотациями на строки `AGENTS.md` и `CLAUDE.md` и комментарием в PR.

**c. Чиним — всё зелёное:**

```bash
cp examples/demo-pr/AGENTS.fixed.md examples/demo/AGENTS.md
cp examples/demo-pr/CLAUDE.fixed.md examples/demo/CLAUDE.md
sed -i 's#../src/config.py#../src/settings.py#' examples/demo/knowledge/local_setup_guide.md
okf agents-check examples/demo --base main --strict && okf stale examples/demo/knowledge --base main
```

Предупреждений нет, код выхода `0`; остаются только `[INFO] ... updated in the same change`.

### Часть 2. База знаний (1 минута)

```bash
okf validate examples/broken --strict          # что ловит валидатор: 19 ошибок
git switch -c demo/auth-ttl main
cp examples/demo-pr/auth.py examples/demo/src/auth.py
okf stale examples/demo/knowledge --base main   # auth_flow.md мог устареть
cp examples/demo-pr/auth_flow.md examples/demo/knowledge/auth_flow.md
okf validate examples/demo/knowledge --strict   # ERROR: агент пометил документ stable без проверки человеком
sed -i 's/by: process:okf-ci/by: human:teamlead_ivan/' examples/demo/knowledge/auth_flow.md
okf validate examples/demo/knowledge --strict && okf agents examples/demo/knowledge   # тимлид подтвердил — зелёное
```

Ключевая ошибка второго шага:

```text
[ERROR] examples/demo/knowledge/auth_flow.md: verified: Document generated by "wheelo-docs-agent/1.4" is status: stable without human review; add a human:<id> entry to verified or set status: draft
```

Бонус: `okf stale examples/demo/knowledge --now 2027-03-01` показывает документы, у которых истёк срок свежести.

Чтобы показать демо на GitHub, после шагов делайте `git commit -am "..." && git push`
(в первый раз — `git push -u origin <ветка>` и откройте PR). Вернуть всё как было:
`git checkout -- examples && git switch main` и удалить демо-ветки через `git branch -D`.

## Структура

```text
src/okf/        instructions.py (agents-check), schema.py (все поля и правила OKF, профили okf и strict),
                validate.py, stale.py, agents.py, bundle.py, git.py, cli.py
tests/          pytest; fixtures/okf-official — официальный пример acme_retail (Apache-2.0)
examples/       demo (мини-репозиторий + knowledge/), demo-pr, broken
etc/            бриф, спеки (v1 и v2), конкурентный анализ, интервью-кит
```
