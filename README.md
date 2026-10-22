# okf-ai

**okf-ai показывает, каким инструкциям и знаниям для ИИ-агентов можно верить прямо сейчас — что проверено, а что устарело вслед за кодом.**

Агенты пишут код по `AGENTS.md`, `CLAUDE.md`, правилам Cursor и базе знаний. Эти тексты стареют молча:
код меняется, а раздел, который его описывает, никто не перечитал. Одна команда на вашем репозитории,
без разметки и настройки, показывает карту доверия: что подтверждено после последнего изменения кода,
что перепроверить и где ссылки ведут в никуда.

- `okf trust` — карта доверия по разделам инструкций и файлам базы знаний; `okf verify` — подтвердить раздел в одно действие;
- `okf agents-check` и `okf stale` — страж в PR: битые пути и команды в инструкциях, документы, чей код поменялся;
- `okf validate` — валидатор базы знаний [OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
  плюс строгий профиль okf-ai ([спека](etc/spec/cli-validator-v2.md)); `okf agents` — роутер `AGENTS.md` для бандла;
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

Команды печатают по строке на находку, сводка уходит в stderr:

```text
[LEVEL] file_path: field_name: message
```

`--format github` печатает то же как команды GitHub Actions — они становятся аннотациями в PR.

## `okf trust [repo] [--since REF] [--strict] [--json]`

```text
okf trust: 16 units: 9 verified and current, 2 to recheck, 2 broken, 3 not verified
[ERROR] AGENTS.md#Команды: trust: "./scripts/seed_db.sh" does not exist
[ERROR] CLAUDE.md: trust: "npm run test:unit": no script "test:unit" in package.json
[WARNING] AGENTS.md#Auth: trust: src/auth.py changed 2026-10-20, last verified 2026-09-05 by human:teamlead_ivan
[WARNING] knowledge/auth_flow.md: trust: src/auth.py changed 2026-10-20, last verified 2026-10-19 by human:teamlead_ivan
[OK] AGENTS.md#Billing: trust: verified 2026-09-05 by human:maria_backend; sources unchanged since
[INFO] AGENTS.md#Правила: trust: not verified; last edited 2026-09-01; sources unchanged since
```

**Единицы.** Каждый раздел (`##`) инструкций для агентов: `AGENTS.md` и `CLAUDE.md` на любом уровне,
`.cursor/rules/*.mdc`, `.cursorrules`, `.github/copilot-instructions.md`, `.ruler/*.md`; текст до первого раздела —
отдельная единица `AGENTS.md`, файл без разделов — одна единица. Плюс каждый файл знаний OKF — любой `.md`
с `type` в шапке (или только бандлы из `--bundle DIR`). Роутер, который пишет `okf agents`, не считается.

**Для каждой единицы:**
- *источники* — для инструкций выводятся из текста, как в `agents-check`: пути, ссылки, `package.json` для
  `npm run`, `Makefile` для `make`, файлы скриптов и тестов (маски вида `src/**/*.py` — нет, это область
  действия, а не код); для OKF — `sources[].resource`;
- *последнее подтверждение* — `.okf/trust.yml` для инструкций, `verified` в шапке для OKF;
  если подтверждений нет — когда раздел последний раз правили (`git blame` по его строкам);
- *дата кода* — последний коммит по каждому источнику (`git log -1 --format=%cI -- путь`),
  незакоммиченные правки — по времени изменения файла.

**Уровни:**

| Уровень | Строка | Когда |
|---|---|---|
| сломано | `ERROR` | раздел ссылается на несуществующий файл, скрипт `package.json`, цель `Makefile` |
| перепроверить | `WARNING` | код менялся после подтверждения (или, если подтверждений нет, после правки раздела); раздел правили после подтверждения; у OKF — `generated.at` позже `verified` или наступил `stale_after` |
| подтверждено | `OK` | последнее подтверждение позже изменений кода: человеком (`human:`) или процессом (`process:`) |
| не подтверждено | `INFO` | подтверждений нет, но и код с тех пор не менялся |

`--since origin/main` — только то, что этот набор изменений делает «перепроверить»: каждая единица, чей
источник изменён, с указанием файла. `--json` — то же для машин. Код выхода `0`; с `--strict` — `1`, если есть
«сломано» или «перепроверить».

## `okf verify FILE[#SECTION]... [--by ACTOR] [--all-current]`

```bash
okf verify AGENTS.md#Auth                 # один раздел
okf verify AGENTS.md                      # все разделы файла; AGENTS.md# — только текст до первого раздела
okf verify knowledge/auth_flow.md         # файл знаний OKF
okf verify --all-current                  # все неподтверждённые разделы, чей код не менялся
```

- Для инструкций пишет в боковой файл `.okf/trust.yml` (ближайший вверх по папкам, иначе в корне git):
  `{unit: AGENTS.md#Auth, hash, sources, verified: [{by, at}]}`. Сами инструкции не трогает; хэш замечает,
  если раздел потом поправили.
- Для OKF дописывает запись в `verified` в шапке, остальной файл не меняется.
- `--by` по умолчанию — `human:` + `git config user.email` (или `user.name`). Раздел ищется по точному заголовку,
  без учёта регистра или по slug (`#getting-started`).

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
- изменён файл кода (не `.md`) — WARNING `changed in this change; the instruction may be outdated`,
  или INFO, если инструкцию поправили в том же PR. Правка документа, на который инструкция ссылается, нормальна и не сообщается.

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

## `okf agents <bundle>`

Пишет `<bundle>/AGENTS.md`: короткую инструкцию и таблицу документов — заголовок с описанием, `type`, `tags`,
свежесть, уровень доверия (`human-reviewed` / `machine-confirmed` / `unverified`) и путь. Агент читает роутер
и открывает только нужные файлы. Пример — [examples/demo/knowledge/AGENTS.md](examples/demo/knowledge/AGENTS.md).
У роутера есть OKF-шапка (`type: Agent Router`), так что бандл остаётся валидным и для чужих инструментов.
`-o -` — в stdout, `--check` — код `1`, если файл устарел, `--now` — посчитать свежесть на другой момент.

## GitHub Action

[`.github/workflows/okf.yml`](.github/workflows/okf.yml) на каждый pull request и push в `main`:

1. pytest;
2. `okf trust $OKF_REPO --since origin/<базовая ветка>` — какие разделы инструкций и документы знаний этот PR
   делает «перепроверить», с указанием изменённого файла; на push — вся карта;
3. `okf agents-check $OKF_REPO --base ...` — битые пути и команды в инструкциях;
4. `okf validate $OKF_BUNDLE --strict` и `okf stale --base ...` — база знаний;
5. отчёт в лог, в job summary и аннотациями на строки; в PR из этого же репозитория — обновляемым комментарием.

Ошибки валят проверку, предупреждения — нет. Чтобы подключить к своему репозиторию, скопируйте файл
и поменяйте `OKF_REPO` (обычно `.`) и `OKF_BUNDLE`; `OKF_AGENTS_ARGS: --strict` сделает битые ссылки в инструкциях ошибками.

## Демо

[`examples/demo`](examples/demo) — мини-репозиторий выдуманного сервиса аренды самокатов Wheelo:
`AGENTS.md` и `CLAUDE.md` для агентов, правило Cursor, `package.json`, `Makefile`, `scripts/`, код в `src/`
и база знаний в `knowledge/` (9 документов OKF). В [`examples/demo-pr`](examples/demo-pr) — заготовки изменений,
в [`examples/broken`](examples/broken) — по файлу на каждую ошибку валидатора.

Для карты доверия нужна история: [`examples/make_demo_history.py`](examples/make_demo_history.py) собирает
из `examples/demo` отдельный git-репозиторий с коммитами за полгода — код в июне, инструкции в сентябре,
5 сентября тимлид подтвердил разделы Auth и Billing, 20 октября поменялся `src/auth.py`, а в ветке
`pr/billing-tariff` лежит PR с новой ценой минуты.

```bash
python examples/make_demo_history.py ../wheelo-demo
cd ../wheelo-demo
```

### Главное: карта доверия (2 минуты)

**1. Чему можно верить прямо сейчас:**

```bash
okf trust
```

```text
okf trust: 16 units: 9 verified and current, 2 to recheck, 2 broken, 3 not verified
[ERROR] AGENTS.md#Команды: trust: "./scripts/seed_db.sh" does not exist
[ERROR] CLAUDE.md: trust: "npm run test:unit": no script "test:unit" in package.json
[WARNING] AGENTS.md#Auth: trust: src/auth.py changed 2026-10-20, last verified 2026-09-05 by human:teamlead_ivan
[WARNING] knowledge/auth_flow.md: trust: src/auth.py changed 2026-10-20, last verified 2026-10-19 by human:teamlead_ivan
[OK] AGENTS.md#Billing: trust: verified 2026-09-05 by human:maria_backend; sources unchanged since
...
```

Из 16 разделов и документов перечитать нужно два, починить — два; остальное подтверждено или не менялось.
Никакой разметки в репозитории для этого не понадобилось, кроме `.okf/trust.yml` от прошлых подтверждений.

**2. PR меняет код — Action пишет, что перепроверить:**

```bash
git switch pr/billing-tariff
okf trust --since main
```

```text
okf trust: 16 units: 6 verified and current, 6 to recheck, 2 broken, 2 not verified; 4 to recheck because of this change
[WARNING] AGENTS.md#Billing: trust: src/billing.py changed in this change; last verified 2026-09-05 by human:maria_backend
[WARNING] .cursor/rules/backend.mdc: trust: src/billing.py changed in this change; never verified
[WARNING] knowledge/billing_service.md: trust: src/billing.py changed in this change; last verified 2026-10-05 by human:maria_backend
[WARNING] knowledge/payment_failures_runbook.md: trust: src/billing.py changed in this change; last verified 2026-10-16 by human:sre_pavel
```

На GitHub это же попадает в job summary и комментарий PR (шаг `okf trust --since origin/<base>` в Action).

**3. Тимлид перечитал раздел Auth — всё ещё верно; чиним сломанное — всё зелёное:**

```bash
git switch main
sed -i 's/seed_db.sh/seed.sh/' AGENTS.md
sed -i 's/npm run test:unit/npm test/' CLAUDE.md
okf verify AGENTS.md#Auth knowledge/auth_flow.md
okf trust --strict
```

```text
okf trust: 16 units: 11 verified and current, 0 to recheck, 0 broken, 5 not verified
```

Код выхода `0`. `okf verify --all-current` подтвердит и оставшиеся пять, где код не менялся.

### Страж в PR: инструкции агентов (1 минута)

В самом репозитории okf-ai, на `examples/demo`:

```bash
okf agents-check examples/demo                       # 3 предупреждения: битый скрипт, нет npm-скрипта, AGENTS.md и CLAUDE.md расходятся
git switch -c demo/rename-config
git mv examples/demo/src/config.py examples/demo/src/settings.py
okf agents-check examples/demo --base main           # "src/config.py" was renamed to src/settings.py in this change (line 20)
okf stale examples/demo/knowledge --base main        # local_setup_guide.md мог устареть
cp examples/demo-pr/AGENTS.fixed.md examples/demo/AGENTS.md
cp examples/demo-pr/CLAUDE.fixed.md examples/demo/CLAUDE.md
sed -i 's#../src/config.py#../src/settings.py#' examples/demo/knowledge/local_setup_guide.md
okf agents-check examples/demo --base main --strict  # чисто, код выхода 0
```

### База знаний OKF (1 минута)

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

Чтобы показать демо на GitHub, после шагов делайте `git commit -am "..." && git push`
(в первый раз — `git push -u origin <ветка>` и откройте PR). Вернуть всё как было:
`git checkout -- examples && git switch main` и удалить демо-ветки через `git branch -D`.

## Структура

```text
src/okf/        trust.py (карта доверия, verify), instructions.py (agents-check), schema.py (поля и правила OKF,
                профили okf и strict), validate.py, stale.py, agents.py, bundle.py, git.py, cli.py
tests/          pytest; fixtures/okf-official — официальный пример acme_retail (Apache-2.0)
examples/       demo (мини-репозиторий + knowledge/), make_demo_history.py, demo-pr, broken
etc/            бриф, спеки (v1 и v2), конкурентный анализ, интервью-кит
```
