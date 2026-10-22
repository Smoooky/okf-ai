# Agents Router Specification

## Purpose
`okf agents <bundle>` пишет `<bundle>/AGENTS.md` — короткий роутер бандла для ИИ-агентов: инструкцию и таблицу документов с типом, тегами, свежестью, уровнем доверия и путём, чтобы агент открывал только нужные файлы, а не читал весь бандл.

## Requirements

### Requirement: Генерация роутера
Команда `okf agents <bundle>` SHALL записывать в `<bundle>/AGENTS.md` таблицу `| Document | Type | Tags | Freshness | Trust | Path |` с одной строкой на каждый документ-концепт с корректной шапкой (теги — YAML-список или строка `a, b`, как их читает и `okf view`) и печатать в stderr `okf agents: wrote <path> (<N> documents)`.

#### Scenario: Роутер для бандла
- GIVEN бандл с документом `auth_flow.md` (`title: Auth flow`, `description: SMS login and JWT tokens.`, `type: Architecture`, `tags: [auth, security]`, `stale_after: 2027-10-19T00:00:00Z`, проверен `human:teamlead_ivan`)
- WHEN пользователь запускает `okf agents <bundle>`
- THEN в `AGENTS.md` есть строка `| Auth flow: SMS login and JWT tokens. | Architecture | auth, security | fresh until 2027-10-19 | human-reviewed, written by human:teamlead_ivan | [auth_flow.md](auth_flow.md) |`
- AND заголовок таблицы — `## Documents (1)`
- AND код выхода 0

#### Scenario: Нет каталога бандла
- GIVEN каталога бандла нет
- WHEN запускается `okf agents missing`
- THEN код выхода 2 и в stderr `okf: error: bundle directory not found: missing`

### Requirement: Роутер остаётся OKF-концептом
Сгенерированный `AGENTS.md` SHALL начинаться с OKF-шапки `type: Agent Router` с `generated: { by: okf-ai/<version> }`, чтобы бандл оставался валидным для `okf validate` и сторонних инструментов OKF.

#### Scenario: Шапка роутера
- GIVEN роутер сгенерирован командой `okf agents`
- WHEN его шапку читает парсер OKF
- THEN `type` равен `Agent Router`, а `generated.by` начинается с `okf-ai/`

#### Scenario: Бандл с роутером валиден
- GIVEN бандл с сгенерированным `AGENTS.md`
- WHEN запускается `okf validate <bundle>`
- THEN роутер не даёт ошибок

### Requirement: Какие файлы попадают в таблицу
Роутер SHALL включать только документы-концепты: служебные `index.md` и `log.md` любого уровня и сам корневой `AGENTS.md` в таблицу не попадают, а документ без шапки или с битой шапкой пропускается с WARNING `frontmatter` в stderr.

#### Scenario: Документ с битой шапкой
- GIVEN в бандле `good.md` с корректной шапкой и `bad.md` без шапки
- WHEN запускается `okf agents <bundle>`
- THEN в таблице только `good.md`
- AND в stderr выводится `[WARNING] bad.md: frontmatter: Left out of AGENTS.md: front matter is missing or invalid`

#### Scenario: Служебные файлы корня как ссылки
- GIVEN в корне бандла есть `index.md` и `log.md`
- WHEN запускается `okf agents <bundle>`
- THEN они не строки таблицы, а перечислены в строке `Service files:` как `[index.md](index.md) (table of contents for humans)` и `[log.md](log.md) (change log)`

#### Scenario: Вложенный index.md
- GIVEN в бандле есть `sub/index.md`
- WHEN запускается `okf agents <bundle>`
- THEN `sub/index.md` не появляется в таблице

### Requirement: Порядок строк
Строки таблицы SHALL быть отсортированы по `type` без учёта регистра, а при равном типе — по пути документа.

#### Scenario: Сортировка
- GIVEN документы `z_concept.md` (`Concept`), `b_guide.md` (`guide`), `a_guide.md` (`Guide`), `table.md` (`BigQuery Table`)
- WHEN запускается `okf agents <bundle>`
- THEN типы в таблице идут в порядке `BigQuery Table`, `Concept`, `Guide`, `guide`

### Requirement: Название документа
Ячейка Document SHALL брать название из `title` шапки, иначе из первого заголовка первого уровня вне блоков кода, иначе из имени файла с заменой `_` и `-` на пробелы, и дописывать `: <description>`, если `description` непустой.

#### Scenario: Название из шапки
- GIVEN `title: From YAML` и заголовок `# From heading`
- WHEN запускается `okf agents`
- THEN ячейка начинается с `From YAML`

#### Scenario: Название из заголовка
- GIVEN `title` нет, первый `#`-заголовок вне кода — `From heading`
- WHEN запускается `okf agents`
- THEN ячейка — `From heading`

#### Scenario: Название из имени файла
- GIVEN `ride_glossary.md` без `title` и без заголовка первого уровня
- WHEN запускается `okf agents`
- THEN ячейка — `ride glossary`

### Requirement: Свежесть
Ячейка Freshness SHALL быть `no stale_after`, `fresh until <date>`, `review due <date>` (до `stale_after` 30 дней или меньше) или `stale since <date>` (момент `--now` не раньше `stale_after`), с префиксом `draft, ` или `deprecated, ` для документов с таким статусом.

#### Scenario: Свежий документ
- GIVEN сейчас 2026-10-22T12:00:00Z и `stale_after: 2027-01-01T00:00:00Z`
- WHEN запускается `okf agents`
- THEN свежесть — `fresh until 2027-01-01`

#### Scenario: Скоро пересмотр
- GIVEN сейчас 2026-10-22T12:00:00Z и `stale_after: 2026-11-21T00:00:00Z`
- WHEN запускается `okf agents`
- THEN свежесть — `review due 2026-11-21`

#### Scenario: Протух ровно сейчас
- GIVEN сейчас 2026-10-22T12:00:00Z и `stale_after: 2026-10-22T12:00:00Z`
- WHEN запускается `okf agents`
- THEN свежесть — `stale since 2026-10-22`

#### Scenario: Нет stale_after
- GIVEN в шапке нет `stale_after`
- WHEN запускается `okf agents`
- THEN свежесть — `no stale_after`

#### Scenario: Устаревший документ
- GIVEN `status: deprecated` и `stale_after: 2027-01-01T00:00:00Z`
- WHEN запускается `okf agents`
- THEN свежесть — `deprecated, fresh until 2027-01-01`

### Requirement: Уровень доверия
Ячейка Trust SHALL содержать уровень из `verified` — `human-reviewed` (есть запись `human:`), `machine-confirmed` (записи есть, но не от человека) или `unverified` (записей нет) — и `, written by <generated.by>`, если автор указан.

#### Scenario: Проверено процессом
- GIVEN `generated.by: human:teamlead_ivan` и `verified` только от `process:ci`
- WHEN запускается `okf agents`
- THEN доверие — `machine-confirmed, written by human:teamlead_ivan`

#### Scenario: Не проверено, написал агент
- GIVEN `verified: []` и `generated.by: agent/1`
- WHEN запускается `okf agents`
- THEN доверие — `unverified, written by agent/1`

#### Scenario: Ни проверки, ни автора
- GIVEN нет ни `verified`, ни `generated`
- WHEN запускается `okf agents`
- THEN доверие — `unverified`

### Requirement: Ячейки и ссылки таблицы
Роутер SHALL экранировать `|` в ячейках как `\|`, заменять переводы строк пробелами и писать пути документов ссылками относительно папки, куда записан роутер, с прямыми слэшами и пробелами как `%20`.

#### Scenario: Вертикальная черта в названии
- GIVEN `title: A | B`
- WHEN запускается `okf agents`
- THEN в ячейке стоит `A \| B`

#### Scenario: Роутер вне бандла
- GIVEN документ `docs/api/start.md` в бандле `bundle/` и `-o out/AGENTS.md`
- WHEN запускается `okf agents bundle -o out/AGENTS.md`
- THEN путь в таблице — `[docs/api/start.md](../bundle/docs/api/start.md)`

### Requirement: Вывод в stdout
С `-o -` команда `okf agents` SHALL печатать роутер в stdout и не записывать файл.

#### Scenario: Печать роутера
- GIVEN бандл с документами
- WHEN запускается `okf agents <bundle> -o -`
- THEN текст роутера выводится в stdout, файл `AGENTS.md` не создаётся и не меняется, код выхода 0

### Requirement: Проверка актуальности роутера
С `--check` команда `okf agents` SHALL ничего не записывать и возвращать код выхода 1 со строкой ``[ERROR] <path>: agents: File is out of date, run `okf agents <bundle>` `` в stdout, если записанный роутер отличается от того, что был бы сгенерирован сейчас.

#### Scenario: Роутер устарел
- GIVEN в бандл добавили документ после генерации `AGENTS.md`
- WHEN запускается `okf agents <bundle> --check`
- THEN код выхода 1, выводится ERROR `agents`, файл не меняется

#### Scenario: Роутер актуален
- GIVEN `AGENTS.md` совпадает с тем, что сгенерировала бы команда
- WHEN запускается `okf agents <bundle> --check`
- THEN код выхода 0 и в stderr `okf agents: <path> is up to date`

#### Scenario: Роутера нет
- GIVEN в бандле нет `AGENTS.md`
- WHEN запускается `okf agents <bundle> --check`
- THEN код выхода 1

### Requirement: Момент оценки свежести
Команда `okf agents` SHALL оценивать свежесть на момент `--now` (дата `YYYY-MM-DD` — полночь UTC, либо ISO-время со смещением), а без `--now` — на текущий момент.

#### Scenario: Перемотка времени
- GIVEN `stale_after: 2027-03-01T00:00:00Z`
- WHEN запускается `okf agents <bundle> --now 2027-03-01`
- THEN свежесть документа — `stale since 2027-03-01`

#### Scenario: Неверный --now
- GIVEN значение `--now tomorrow`
- WHEN запускается `okf agents <bundle> --now tomorrow`
- THEN команда завершается ошибкой использования с кодом выхода 2
