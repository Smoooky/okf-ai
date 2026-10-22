# Project Init Specification

## Purpose
`okf init [repo]` одной командой ставит в репозиторий каркас okf-ai: бандл знаний OKF с черновиками, боковой файл подтверждений, проверку в GitHub Actions и подсказку агентам в `AGENTS.md`. Ничего существующего не перезаписывается без `--force`, а `--from-agents` предлагает документы знаний из разделов уже написанных инструкций.

## Requirements

### Requirement: Бандл знаний
Команда `okf init` SHALL создавать в `knowledge/` бандл OKF: `index.md` с `okf_version: "0.2"` и ссылками на все документы, `log.md` с записью о создании, три шаблона — `architecture.md` (`type: Architecture`), `local_setup.md` (`type: Guide`) и `runbook.md` (`type: Runbook`) — и роутер `knowledge/AGENTS.md`, сгенерированный как `okf agents`.

#### Scenario: Пустой репозиторий
- GIVEN репозиторий с `AGENTS.md`, без `knowledge/`
- WHEN запускается `okf init`
- THEN созданы `knowledge/index.md`, `knowledge/log.md`, `knowledge/architecture.md`, `knowledge/local_setup.md`, `knowledge/runbook.md` и `knowledge/AGENTS.md`
- AND `okf validate knowledge` не находит ошибок

### Requirement: Шаблоны — черновики, а не подтверждённое знание
Каждый документ, который пишет `okf init`, MUST иметь `status: draft`, `generated: {by: process:okf-init, at: <время запуска>}` и не иметь `verified`, а шаблон без найденного кода — `sources: []` с подсказкой, что туда вписать.

#### Scenario: Шаблон в карте доверия
- GIVEN `okf init` выполнен 2026-10-22
- WHEN запускается `okf trust`
- THEN `knowledge/runbook.md` — «не подтверждено» с сообщением `edited by process:okf-init on 2026-10-22; not verified`

### Requirement: Боковой файл подтверждений
Команда `okf init` SHALL создавать `.okf/trust.yml` с пустым списком `units: []` и комментарием, что его пишет `okf verify`.

#### Scenario: Файл создан
- GIVEN в репозитории нет `.okf/trust.yml`
- WHEN запускается `okf init`
- THEN `.okf/trust.yml` создан и содержит `units: []`

### Requirement: Workflow проверки
Команда `okf init` SHALL создавать `.github/workflows/okf.yml` из шаблона с теми же шагами задачи `knowledge`, что в workflow самого okf-ai, но с `OKF_REPO: .`, `OKF_BUNDLE: knowledge`, пустым `OKF_VALIDATE_ARGS`, установкой okf из git-репозитория okf-ai и без задачи модульных тестов.

#### Scenario: Настройки шаблона
- GIVEN `okf init` выполнен
- WHEN читается `.github/workflows/okf.yml`
- THEN `env.OKF_REPO` равен `.`, `env.OKF_BUNDLE` — `knowledge`, задачи `tests` нет

### Requirement: Подсказка агентам в AGENTS.md
Если в корне репозитория есть `AGENTS.md`, команда SHALL один раз дописывать в его конец раздел `## Knowledge base` с маркером `<!-- okf init: knowledge router -->` и ссылкой на `knowledge/AGENTS.md`, не меняя остальной текст, а без `AGENTS.md` — не создавать его.

#### Scenario: Первый запуск
- GIVEN корневой `AGENTS.md` без маркера
- WHEN запускается `okf init`
- THEN `AGENTS.md` начинается с прежнего текста и заканчивается разделом `## Knowledge base` со ссылкой на `knowledge/AGENTS.md`, в stderr `okf init: updated AGENTS.md`

#### Scenario: Повторный запуск
- GIVEN раздел с маркером уже дописан
- WHEN `okf init` запускается снова, в том числе с `--force`
- THEN маркер в `AGENTS.md` встречается один раз

### Requirement: Ничего не перезаписывается без --force
Команда `okf init` MUST NOT менять существующие файлы бандла, `.okf/trust.yml` и workflow без `--force`: такой файл остаётся как был и попадает в строку `okf init: kept <path> (it exists; --force overwrites it)`, а с `--force` он перезаписывается и печатается как `updated`.

#### Scenario: Свой runbook
- GIVEN `knowledge/runbook.md` уже переписан человеком
- WHEN снова запускается `okf init`
- THEN файл не изменился, в stderr `okf init: kept knowledge/runbook.md (it exists; --force overwrites it)`

#### Scenario: С --force
- GIVEN `knowledge/runbook.md` переписан человеком
- WHEN запускается `okf init --force`
- THEN файл снова шаблонный, в stderr `okf init: updated knowledge/runbook.md`

### Requirement: Вывод и коды выхода
Команда SHALL печатать в stderr строку `okf init: created|updated|kept <path>` на каждый файл и в конце `okf init: next: fill in knowledge/, then okf trust and okf verify <file>`, возвращая 0, а для несуществующего каталога — код выхода 2 и `okf: error: directory not found: <repo>`.

#### Scenario: Нет каталога
- GIVEN каталога нет
- WHEN запускается `okf init missing`
- THEN код выхода 2 и в stderr `okf: error: directory not found: missing`

### Requirement: Документы из разделов инструкций
С `--from-agents` команда SHALL дополнительно предлагать документ знаний на каждый непустой раздел `##` корневых `AGENTS.md` и `CLAUDE.md` (не вложенных): файл `knowledge/<slug заголовка>.md` (кириллица транслитерируется), `title` — заголовок раздела, `description: From the <unit> section of the agent instructions.`, `sources` — файлы, на которые ссылается раздел, относительно `knowledge/`, тело — текст раздела с относительными ссылками, переписанными от `knowledge/`, и ссылка на документ в `index.md`; раздел, чьё имя файла совпадает с уже предложенным или с шаблоном, пропускается.

#### Scenario: Раздел Auth
- GIVEN в `AGENTS.md` раздел `## Auth` с `` `src/auth.py` `` и ссылкой `[the schema](db/schema.sql)`
- WHEN запускается `okf init --from-agents`
- THEN создан `knowledge/auth.md` с `sources:` и `- resource: ../src/auth.py`, ссылкой `[the schema](../db/schema.sql)` и `type: Guide`
- AND в `knowledge/index.md` есть `[Auth](auth.md)`, а `okf validate knowledge` не находит ошибок и битых ссылок

### Requirement: Тип по заголовку раздела
Для предложенного документа команда SHALL угадывать `type` по словам заголовка: «архитект», architecture, design — `Architecture`; runbook, incident, «инцидент», «дежур», on-call — `Runbook`; api, endpoint, «эндпоинт» — `API Endpoint`; «правил», policy, rules, «политик» — `Policy`; иначе `Guide`.

#### Scenario: Русский заголовок
- GIVEN в `AGENTS.md` раздел `## Архитектура`
- WHEN запускается `okf init --from-agents`
- THEN создан `knowledge/arkhitektura.md` с `type: Architecture`
