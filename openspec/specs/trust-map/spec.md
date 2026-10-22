# Trust Map Specification

## Purpose
`okf trust [repo]` строит карту доверия: для каждого раздела инструкций ИИ-агентов и каждого файла знаний OKF показывает, подтверждён ли он после последнего изменения описываемого кода, что перепроверить и что сломано — без разметки репозитория. `okf verify` подтверждает раздел или документ одним действием и записывает, кто и когда это сделал.

## Requirements

### Requirement: Единицы инструкций
Команда `okf trust` SHALL делить каждый файл инструкций (`AGENTS.md` и `CLAUDE.md` на любом уровне, `.cursor/rules/*.mdc`, `.cursorrules`, `.github/copilot-instructions.md`, `.md` в `.ruler/` и `.rulesync/`) на единицы по заголовкам второго уровня `##` вне блоков кода, считая текст до первого раздела отдельной единицей `<file>` (если в нём есть что-то кроме заголовков), а файл без разделов — одной единицей.

#### Scenario: Разделы и вступление
- GIVEN `AGENTS.md` с вступительным абзацем и разделами `## Auth` и `## Billing`
- WHEN запускается `okf trust`
- THEN в карте три единицы: `AGENTS.md`, `AGENTS.md#Auth`, `AGENTS.md#Billing`

#### Scenario: Файл без разделов
- GIVEN `CLAUDE.md` без заголовков `##`
- WHEN запускается `okf trust`
- THEN `CLAUDE.md` — одна единица без `#раздела`

#### Scenario: Повтор заголовка и заголовок в коде
- GIVEN в файле два раздела `## Notes` и строка `## Fake` внутри блока кода
- WHEN запускается `okf trust`
- THEN единицы называются `…#Notes` и `…#Notes (2)`, а `## Fake` разделом не считается

#### Scenario: Пустое вступление
- GIVEN файл начинается с `# AGENTS.md` и сразу `## Auth`
- WHEN запускается `okf trust`
- THEN отдельной единицы для вступления нет

#### Scenario: Роутер okf agents не единица
- GIVEN в репозитории есть `knowledge/AGENTS.md`, сгенерированный `okf agents`
- WHEN запускается `okf trust`
- THEN роутер в карту не попадает

### Requirement: Единицы знаний OKF
Команда `okf trust` SHALL считать единицей каждый файл `.md` с YAML-шапкой, где `type` — строка (кроме `index.md`, `log.md`, `AGENTS.md`, `CLAUDE.md` и файлов инструкций), а с `--bundle DIR` (можно повторять) — только документы-концепты указанных бандлов.

#### Scenario: Документ знаний в любом месте
- GIVEN `knowledge/auth_flow.md` с шапкой `type: Architecture`
- WHEN запускается `okf trust`
- THEN в карте есть единица `knowledge/auth_flow.md`

#### Scenario: Markdown без type
- GIVEN `docs/notes.md` без шапки
- WHEN запускается `okf trust`
- THEN этот файл не единица карты

#### Scenario: Только указанный бандл
- GIVEN документы OKF в `knowledge/` и `other/`
- WHEN запускается `okf trust --bundle knowledge`
- THEN в карте только документы из `knowledge/`

### Requirement: Источники единицы инструкций
Источниками раздела инструкций SHALL быть существующие файлы, которые упоминаются в его тексте путём или запускаются его командами, кроме масок, папок, документов (`.md`, `.mdx`, `.markdown`, `.txt`, `.rst`), манифестов за `npm run` и `make` и обёрток сборки (`gradlew`, `mvnw`).

#### Scenario: Пути и скрипты
- GIVEN раздел упоминает `src/auth.py` и `./scripts/seed.sh`
- WHEN строится карта
- THEN источники раздела — `src/auth.py` и `scripts/seed.sh`

#### Scenario: Правка зависимостей не требует перепроверки
- GIVEN раздел говорит `npm test`, в `package.json` поменялась только версия зависимости
- WHEN строится карта
- THEN `package.json` не источник раздела и раздел не становится «перепроверить» из-за него

#### Scenario: Папка и маска — область, а не код
- GIVEN раздел упоминает `src/` и `src/**/*.py`
- WHEN в `src/` меняется файл
- THEN раздел не становится «перепроверить» из-за этого

### Requirement: Источники единицы знаний OKF
Источниками файла знаний SHALL быть значения `sources[].resource`, разрешённые как в `okf stale` (пути от файла и от корня бандла, ссылки GitHub на файлы этого репозитория), а описания области с пробелами и другие URL не считаются источниками и не влияют на уровень; несуществующий источник делает документ «сломано» с сообщением `source "<resource>" does not exist`, а переехавший по истории git — «перепроверить».

#### Scenario: Источник-путь
- GIVEN `knowledge/auth_flow.md` с `resource: ../src/auth.py`, файл существует
- WHEN строится карта
- THEN источник документа — `src/auth.py`

#### Scenario: Внешний URL не источник
- GIVEN `resource: https://wiki.example.com/auth`
- WHEN строится карта
- THEN этот источник не влияет на уровень документа

#### Scenario: Источника нет
- GIVEN `resource: /src/gone.py`, файла нет и он не переименовывался
- WHEN строится карта
- THEN документ «сломано»: `[ERROR] knowledge/x.md: trust: source "/src/gone.py" does not exist`

#### Scenario: Источник переехал
- GIVEN `resource: ../src/config.py`, файл переименован в `src/settings.py` 2026-09-20
- WHEN строится карта
- THEN документ «перепроверить» с сообщением `../src/config.py moved to src/settings.py on 2026-09-20; …`

### Requirement: Даты подтверждения, правки и кода
Карта SHALL брать последнее подтверждение раздела инструкций из `.okf/trust.yml`, а файла OKF — из `verified` в шапке; дату правки раздела — по последнему изменению его строк в истории git, а файла OKF — по последнему коммиту файла; дату кода — по последнему коммиту источника с учётом переименований, а для незакоммиченных правок — по времени изменения файла.

#### Scenario: Незакоммиченная правка кода
- GIVEN раздел подтверждён вчера, `src/auth.py` изменён сегодня и не закоммичен
- WHEN запускается `okf trust`
- THEN раздел «перепроверить», дата изменения `src/auth.py` — сегодняшняя

#### Scenario: Переименованный источник сохраняет историю
- GIVEN `src/config.py` изменён в июне и переименован в `src/settings.py` 2026-09-20
- WHEN строится карта
- THEN дата кода `src/settings.py` — 2026-09-20

#### Scenario: Каталог вне git
- GIVEN каталог не является репозиторием git
- WHEN запускается `okf trust <dir>`
- THEN карта строится без дат: изменения кода не делают единицы «перепроверить»

### Requirement: Уровень «сломано»
Единица SHALL получать уровень «сломано» (строка `ERROR`), если она ссылается на несуществующий файл, скрипт `package.json`, цель `Makefile`, рецепт `justfile` или маску без совпадений, с сообщением о первой проблеме и `(and <N> more)`, если их больше.

#### Scenario: Нет npm-скрипта
- GIVEN `CLAUDE.md` говорит `npm run test:unit`, скрипта нет
- WHEN запускается `okf trust`
- THEN выводится `[ERROR] CLAUDE.md: trust: "npm run test:unit": no script "test:unit" in package.json`

#### Scenario: Несколько проблем
- GIVEN раздел ссылается на три несуществующих файла
- WHEN запускается `okf trust`
- THEN сообщение — первая проблема и `(and 2 more)`

### Requirement: Уровень «перепроверить»
Единица SHALL получать уровень «перепроверить» (строка `WARNING`), если упомянутый файл переехал, если код менялся после последнего подтверждения (а без подтверждений — после последней правки единицы), если раздел правили после подтверждения (хэш текста не совпадает с записанным), если у файла OKF наступил `stale_after` или если у файла OKF с автором-человеком (или без автора) `generated.at` позже последнего `verified`.

#### Scenario: Код изменён после подтверждения
- GIVEN `AGENTS.md#Auth` подтверждён `human:teamlead_ivan` 2026-09-05, `src/auth.py` изменён 2026-10-20
- WHEN запускается `okf trust`
- THEN выводится `[WARNING] AGENTS.md#Auth: trust: src/auth.py changed 2026-10-20, last verified 2026-09-05 by human:teamlead_ivan`

#### Scenario: Не подтверждён, код новее раздела
- GIVEN раздел написан 2026-06-01 и не подтверждался, `src/auth.py` изменён 2026-10-20
- WHEN запускается `okf trust`
- THEN сообщение — `src/auth.py changed 2026-10-20, section last edited 2026-06-01 and never verified`

#### Scenario: Раздел правили после подтверждения
- GIVEN раздел подтверждён, затем его текст изменили
- WHEN запускается `okf trust`
- THEN сообщение — `section edited after it was verified; last verified <date> by <actor>`

#### Scenario: Пробелы в конце строк не считаются правкой
- GIVEN после подтверждения в разделе изменились только пробелы в конце строк
- WHEN запускается `okf trust`
- THEN раздел не становится «перепроверить» из-за правки

#### Scenario: Наступил stale_after
- GIVEN файл OKF с `stale_after` в прошлом
- WHEN запускается `okf trust`
- THEN сообщение — `stale_after <date> has passed; last verified …` или `…; never verified`

#### Scenario: Содержимое перегенерировано человеком после проверки
- GIVEN файл OKF с `generated: {by: human:ivan, at: 2026-10-10T00:00:00Z}` и последним `verified` 2026-10-01
- WHEN запускается `okf trust`
- THEN сообщение — `content regenerated 2026-10-10 after it was verified; last verified 2026-10-01 by …`

### Requirement: Уровень «подтверждено»
Единица SHALL получать уровень «подтверждено» (строка `OK`) с сообщением `verified <date> by <actor>; sources unchanged since` (или `; no code references found`), если последнее подтверждение не раньше изменений её кода, различая подтверждение человеком (`human-verified`) и процессом (`process-verified`).

#### Scenario: Подтверждено человеком
- GIVEN `AGENTS.md#Billing` подтверждён `human:maria_backend` 2026-09-05, `src/billing.py` с тех пор не менялся
- WHEN запускается `okf trust`
- THEN выводится `[OK] AGENTS.md#Billing: trust: verified 2026-09-05 by human:maria_backend; sources unchanged since`

#### Scenario: Подтверждено процессом после изменения
- GIVEN человек подтвердил раздел до изменения кода, а `process:ci` — после
- WHEN строится карта
- THEN уровень — `process-verified`, сообщение называет `process:ci`

### Requirement: Уровень «не подтверждено»
Единица SHALL получать уровень «не подтверждено» (строка `INFO`) с сообщением `not verified; last edited <date>; sources unchanged since` (или `; no code references found`), если подтверждений нет, но код не менялся после её последней правки.

#### Scenario: Новый раздел
- GIVEN раздел `.cursor/rules/backend.mdc` и его код закоммичены 2026-09-01, подтверждений нет, код с тех пор не менялся
- WHEN запускается `okf trust`
- THEN выводится `[INFO] .cursor/rules/backend.mdc: trust: not verified; last edited 2026-09-01; sources unchanged since`

#### Scenario: Раздел без связей с кодом
- GIVEN раздел «пиши тесты на pytest» без путей и команд
- WHEN запускается `okf trust`
- THEN сообщение заканчивается на `; no code references found`, уровень — не ошибка

### Requirement: Правка инструментом понижает доверие
Единица, которую после последнего подтверждения переписал не человек (`generated.by` — `process:okf-fix`, `<producer>/<model>` или другой не `human:` автор с `generated.at` позже последнего `verified`), SHALL получать уровень «не подтверждено» с сообщением `edited by <actor> on <date>; not verified[, last verified <date> by <actor>]`.

#### Scenario: После okf fix
- GIVEN `okf fix --apply` исправил `AGENTS.md#Команды` 2026-10-22
- WHEN запускается `okf trust`
- THEN выводится `[INFO] AGENTS.md#Команды: trust: edited by process:okf-fix on 2026-10-22; not verified`

#### Scenario: После черновика LLM
- GIVEN черновик `anthropic/claude-opus-5-5` применён к `AGENTS.md#Auth`, ранее подтверждённому 2026-09-05
- WHEN запускается `okf trust`
- THEN сообщение — `edited by anthropic/claude-opus-5-5 on 2026-10-22; not verified, last verified 2026-09-05 by human:teamlead_ivan`

#### Scenario: Подтверждение после правки
- GIVEN после правки инструментом человек выполнил `okf verify`
- WHEN запускается `okf trust`
- THEN единица снова «подтверждено»

### Requirement: Сводка и порядок вывода
Команда SHALL печатать в stderr сводку `okf trust: <N> units: <V> verified and current, <R> to recheck, <B> broken, <U> not verified`, а в stdout — строку `[LEVEL] <file>[#<section>]: trust: <message>` на каждую единицу в порядке «сломано», «перепроверить», «подтверждено», «не подтверждено» (внутри уровня — по порядку файлов), затем строки `[INFO] <file>: trust: <note>` о ссылках и сгенерированных копиях.

#### Scenario: Демо-репозиторий
- GIVEN демо-история `wheelo-demo` на `main`
- WHEN запускается `okf trust`
- THEN в stderr `okf trust: 16 units: 9 verified and current, 3 to recheck, 1 broken, 3 not verified`
- AND первая строка stdout — `[ERROR] CLAUDE.md: trust: …`

### Requirement: Что меняет pull request
С `--since REF` (синоним `--base`) команда SHALL показывать только единицы, чьи источники или упомянутые пути изменены с merge-base с REF, с сообщением `<paths> changed in this change; <last verification>`, и дописывать к сводке `; <K> to recheck because of this change`.

#### Scenario: PR меняет код биллинга
- GIVEN ветка `pr/billing-tariff` меняет `src/billing.py`
- WHEN запускается `okf trust --since main`
- THEN выводится `[WARNING] AGENTS.md#Billing: trust: src/billing.py changed in this change; last verified 2026-09-05 by human:maria_backend`
- AND сводка заканчивается на `; 4 to recheck because of this change`
- AND единицы, не связанные с изменёнными файлами, не выводятся

#### Scenario: Вне репозитория git
- GIVEN каталог не является репозиторием git
- WHEN запускается `okf trust <dir> --since main`
- THEN код выхода 2 и в stderr `okf: error: --since needs a git repository`

#### Scenario: Неизвестная ветка
- GIVEN ref не существует
- WHEN запускается `okf trust --since no-such-ref`
- THEN код выхода 2 и в stderr сообщение об ошибке git

### Requirement: Раздел, исправленный в том же PR, не помечается
С `--since` единица, чей код изменён и которую тот же набор изменений тоже поправил (для раздела — изменённые строки внутри раздела, для файла OKF — сам файл), SHALL выводиться как `[INFO] <unit>: trust: <paths> and this section|file changed together in this change` и не считаться «перепроверить из-за этого изменения» (краевой случай PRD №4).

#### Scenario: Код и раздел в одном PR
- GIVEN PR меняет `src/auth.py` и строку в разделе `AGENTS.md#Auth`, а `src/billing.py` из раздела `#Billing` тоже изменён без правки раздела
- WHEN запускается `okf trust --since main`
- THEN `AGENTS.md#Auth` выводится как `[INFO] AGENTS.md#Auth: trust: src/auth.py and this section changed together in this change`
- AND «перепроверить из-за этого изменения» только `AGENTS.md#Billing`

#### Scenario: Правка другого раздела того же файла
- GIVEN PR меняет `src/billing.py` и только раздел `#Auth` в `AGENTS.md`
- WHEN запускается `okf trust --since main`
- THEN `AGENTS.md#Billing` остаётся «перепроверить»

### Requirement: Коды выхода
Команда `okf trust` SHALL возвращать код выхода 0, а с `--strict` — 1, если в карте есть «сломано» или «перепроверить» (с `--since` — если есть единицы, которые нужно перепроверить из-за этого изменения).

#### Scenario: Без strict
- GIVEN в карте есть «сломано»
- WHEN запускается `okf trust`
- THEN код выхода 0

#### Scenario: Strict с проблемами
- GIVEN в карте есть «сломано»
- WHEN запускается `okf trust --strict`
- THEN код выхода 1

#### Scenario: Strict в PR, где всё поправлено вместе с кодом
- GIVEN PR поправил и код, и описывающий его раздел
- WHEN запускается `okf trust --since main --strict`
- THEN код выхода 0

### Requirement: Вывод для машин
С `--json` команда SHALL печатать в stdout JSON с полями `summary` (`units`, `verified`, `recheck`, `broken`, `unverified`, `in_change`, `history`: `full` или `shallow`), `units` (для каждой показанной единицы: `unit`, `file`, `section`, `line`, `kind`, `level`, `reason`, `message`, `sources`, `changed`, `in_change`, `updated_in_change`, `broken`, `moved`, `verified`, `last_edited`, `links`) и `notes`.

#### Scenario: JSON-сводка
- GIVEN 4 единицы, одна «сломано», три «не подтверждено», полная история
- WHEN запускается `okf trust --json`
- THEN `summary` равен `{"units": 4, "verified": 0, "recheck": 0, "broken": 1, "unverified": 3, "in_change": null, "history": "full"}`
- AND `units[0].level` равен `broken`

#### Scenario: Связи с кодом
- GIVEN раздел упоминает существующий файл, заглушку и путь из `.gitignore`
- WHEN запускается `okf trust --json`
- THEN в `links` у этих связей статусы `ok`, `unclear` и `unknown`

### Requirement: Аннотации GitHub
С `--format github` команда SHALL печатать только единицы «сломано» и «перепроверить» как команды `::error` и `::warning` GitHub Actions на строку заголовка раздела, с именем раздела в начале сообщения.

#### Scenario: Аннотация
- GIVEN одна единица «сломано» и три «не подтверждено»
- WHEN запускается `okf trust --format github`
- THEN в stdout ровно одна строка, начинающаяся с `::error `

### Requirement: Заглушки и результаты сборки не делают единицу сломанной
Пути-заглушки (`path/to/file.ts`, `src/foo.py`, `your-project/…`, `example/…`) SHALL получать статус связи «неясно» (`unclear`), а пути из `.gitignore` любого уровня и обычные результаты сборки (`dist/`, `node_modules/`, `.env`) — статус «неизвестно» (`unknown`), и ни те, ни другие не делают единицу «сломано» (краевые случаи PRD №1 и №2).

#### Scenario: Заглушка в примере
- GIVEN раздел упоминает только `path/to/file.ts`
- WHEN запускается `okf trust`
- THEN раздел не «сломано»

#### Scenario: Результат сборки
- GIVEN раздел упоминает `dist/bundle.js`, папки `dist` нет, она в `.gitignore`
- WHEN запускается `okf trust`
- THEN раздел не «сломано»

### Requirement: Неполная история git
В неполной (shallow) истории git карта MUST NOT выдумывать даты изменений: даты кода неизвестны, ни одна единица не становится «перепроверить» из-за дат, в stderr выводится предупреждение с примером `fetch-depth: 0`, а в `--json` — `"history": "shallow"` (краевой случай PRD №3).

#### Scenario: Клон глубиной 1
- GIVEN клон `git clone --depth 1`, раздел не подтверждался, код менялся после раздела
- WHEN запускается `okf trust`
- THEN раздел «не подтверждено», а не «перепроверить»
- AND в stderr выводится предупреждение, начинающееся с `okf trust: warning: the git history is shallow`, с подсказками `fetch-depth: 0` и `git fetch --unshallow`
- AND код выхода 0

#### Scenario: merge-base в неполной истории
- GIVEN неполный клон, где merge-base с базовой веткой не находится
- WHEN запускается `okf trust --since origin/main`
- THEN код выхода 2 и сообщение об ошибке подсказывает `fetch-depth: 0`

### Requirement: Вложенные инструкции в монорепозитории
Пути во вложенной инструкции (`packages/api/AGENTS.md`) SHALL искаться сначала от её папки, потом от корня репозитория, а связь, найденная от корня, помечается в `--json` статусом `ok:root` (краевой случай PRD №5).

#### Scenario: Пути вложенной инструкции
- GIVEN `packages/api/AGENTS.md` упоминает `src/server.ts` (есть в `packages/api/src/`), `scripts/release.sh` (есть только в корне) и `src/gone.ts` (нигде нет)
- WHEN запускается `okf trust --json`
- THEN статусы связей — `ok`, `ok:root` и `broken`

### Requirement: CLAUDE.md как ссылка на AGENTS.md
`CLAUDE.md`, который является симлинком или однострочной ссылкой на `AGENTS.md`, SHALL не давать своих единиц, а давать заметку `Link to AGENTS.md; its sections are checked there`; импорт `@AGENTS.md` в `CLAUDE.md` не делает разделы `CLAUDE.md` зависимыми от правок `AGENTS.md` (краевой случай PRD №6).

#### Scenario: Однострочная ссылка
- GIVEN `CLAUDE.md` содержит только `AGENTS.md`
- WHEN запускается `okf trust`
- THEN единицы только из `AGENTS.md`, а в stdout есть `[INFO] CLAUDE.md: trust: Link to AGENTS.md; its sections are checked there`

#### Scenario: Импорт @AGENTS.md
- GIVEN `CLAUDE.md` начинается с `@AGENTS.md`, после этого `AGENTS.md` правили
- WHEN запускается `okf trust`
- THEN вступление `CLAUDE.md` не имеет источников и остаётся «не подтверждено», а не «перепроверить»

### Requirement: Копии Ruler и rulesync
Файлы инструкций, сгенерированные Ruler или rulesync (маркер в файле или блок Ruler в `.gitignore`), SHALL не давать своих единиц, а давать заметку `Generated from .ruler/ (Ruler)` или `Generated from .rulesync/ (rulesync)`, и проверяется только источник в `.ruler/` или `.rulesync/` (краевой случай PRD №7).

#### Scenario: Ruler
- GIVEN `.ruler/instructions.md` с битым путём и его копии `AGENTS.md` и `CLAUDE.md`
- WHEN запускается `okf trust`
- THEN единственная единица — `.ruler/instructions.md#Auth` с уровнем «сломано»
- AND для копий выводятся заметки `Generated from .ruler/ (Ruler); its sections are checked there`

### Requirement: Переехавший файл
Упомянутый файл, которого нет, но который по истории git переименован (в том числе несколько раз) в существующий, SHALL делать единицу «перепроверить» с сообщением `<as written> moved to <new path> on <date>; <last verification>`, а не «сломано» (краевой случай PRD №8).

#### Scenario: Скрипт переехал
- GIVEN `AGENTS.md#Команды` упоминает `./scripts/seed_db.sh`, переименованный в `scripts/seed.sh` 2026-08-20, и не подтверждался
- WHEN запускается `okf trust`
- THEN выводится `[WARNING] AGENTS.md#Команды: trust: ./scripts/seed_db.sh moved to scripts/seed.sh on 2026-08-20; never verified`

#### Scenario: Два переименования
- GIVEN `src/config.py` → `src/settings.py` → `src/conf/settings.py` (2026-10-01)
- WHEN запускается `okf trust`
- THEN сообщение — `src/config.py moved to src/conf/settings.py on 2026-10-01; never verified`

### Requirement: Подтверждение раздела инструкций
Команда `okf verify FILE#SECTION` SHALL записывать в боковой файл `.okf/trust.yml` запись `{unit, hash, sources, verified: [{by, at}]}` для раздела, не меняя сам файл инструкций, и печатать в stderr `okf verify: <unit> verified by <actor> at <datetime>`.

#### Scenario: Подтвердить раздел
- GIVEN `AGENTS.md` с разделом `## Auth`
- WHEN запускается `okf verify AGENTS.md#Auth --by human:ivan --at 2026-09-05T10:00:00Z`
- THEN в `.okf/trust.yml` появляется запись `unit: AGENTS.md#Auth` с хэшем текста, источниками и `verified: [{by: human:ivan, at: 2026-09-05T10:00:00Z}]`
- AND `AGENTS.md` не изменился
- AND в stderr `okf verify: AGENTS.md#Auth verified by human:ivan at 2026-09-05T10:00:00Z`, код выхода 0

#### Scenario: Повторное подтверждение
- GIVEN раздел уже подтверждён
- WHEN его подтверждают снова
- THEN в `verified` записи добавляется ещё одна запись, хэш и источники обновляются

### Requirement: Боковой файл подтверждений
Команда `okf verify` SHALL писать в ближайший `.okf/trust.yml` вверх по папкам от файла инструкций до корня git, а если его нет — создавать `.okf/trust.yml` в корне git (вне git — в рабочей папке), с ключами единиц относительно папки бокового файла и записями, отсортированными по имени единицы.

#### Scenario: Первый запуск
- GIVEN в репозитории нет `.okf/trust.yml`
- WHEN запускается `okf verify packages/api/AGENTS.md#API`
- THEN создаётся `.okf/trust.yml` в корне git с записью `packages/api/AGENTS.md#API`

#### Scenario: Вложенный боковой файл
- GIVEN есть `packages/api/.okf/trust.yml`
- WHEN запускается `okf verify packages/api/AGENTS.md#API`
- THEN запись пишется туда с ключом `AGENTS.md#API`

### Requirement: Выбор раздела
Команда `okf verify` SHALL находить раздел по точному заголовку, затем без учёта регистра, затем по slug (`#getting-started`); `FILE` без `#` подтверждает все разделы файла, а `FILE#` — только текст до первого раздела.

#### Scenario: Без учёта регистра и по slug
- GIVEN раздел `## Getting Started`
- WHEN запускается `okf verify "AGENTS.md#getting started"` или `okf verify AGENTS.md#getting-started`
- THEN подтверждается `AGENTS.md#Getting Started`

#### Scenario: Весь файл
- GIVEN в `AGENTS.md` вступление и два раздела
- WHEN запускается `okf verify AGENTS.md`
- THEN подтверждаются три единицы

#### Scenario: Только вступление
- GIVEN в `AGENTS.md` вступление и разделы
- WHEN запускается `okf verify AGENTS.md#`
- THEN подтверждается только единица `AGENTS.md`

#### Scenario: Нет такого раздела
- GIVEN в `AGENTS.md` разделы `Auth` и `Billing`
- WHEN запускается `okf verify AGENTS.md#Deploy`
- THEN код выхода 2 и в stderr `okf: error: no section "Deploy" in AGENTS.md; sections: "Auth", "Billing"`

#### Scenario: Нет вступления
- GIVEN `AGENTS.md` начинается сразу с раздела
- WHEN запускается `okf verify AGENTS.md#`
- THEN код выхода 2 и сообщение `AGENTS.md has no text before its first section`

### Requirement: Подтверждение документа OKF
Для файла знаний OKF команда `okf verify FILE` SHALL дописывать запись `{by, at}` в `verified` шапки, сохраняя прежние записи (одиночный словарь становится списком) и не меняя остальной файл.

#### Scenario: Подтвердить документ
- GIVEN `knowledge/auth_flow.md` с `verified: {by: human:ivan, at: 2026-10-01T00:00:00Z}`
- WHEN запускается `okf verify knowledge/auth_flow.md --by human:maria --at 2026-10-22T10:00:00Z`
- THEN `verified` — список из двух записей, тело и другие поля шапки не изменились

#### Scenario: Раздел у документа OKF
- GIVEN `knowledge/auth_flow.md` — документ OKF
- WHEN запускается `okf verify knowledge/auth_flow.md#Intro`
- THEN код выхода 2 и сообщение `knowledge/auth_flow.md is an OKF document: it has no sections to verify`

#### Scenario: Ни инструкция, ни OKF
- GIVEN `docs/notes.md` без шапки с `type`
- WHEN запускается `okf verify docs/notes.md`
- THEN код выхода 2 и сообщение `notes.md is neither an agent instruction file nor an OKF document`

#### Scenario: Нет файла
- GIVEN файла нет
- WHEN запускается `okf verify gone.md`
- THEN код выхода 2 и сообщение `file not found: gone.md`

### Requirement: Кто подтверждает
Команда `okf verify` SHALL записывать актора из `--by`, а по умолчанию — `human:` плюс `git config user.email` (иначе `user.name`, пробелы заменяются на `-`), и отказывать с кодом выхода 2, если актор не в формате OKF или его нельзя определить.

#### Scenario: Актор по умолчанию
- GIVEN `git config user.email` — `ivan@example.com`
- WHEN запускается `okf verify AGENTS.md#Auth`
- THEN записывается `by: human:ivan@example.com`

#### Scenario: Нет git-личности
- GIVEN не заданы ни `user.email`, ни `user.name`, и нет `--by`
- WHEN запускается `okf verify AGENTS.md#Auth`
- THEN код выхода 2 и сообщение `cannot tell who verifies: set git config user.email or pass --by human:<id>`

#### Scenario: Неверный актор
- GIVEN `--by ivan`
- WHEN запускается `okf verify AGENTS.md#Auth --by ivan`
- THEN код выхода 2 и сообщение `"ivan" is not an actor: use human:<id>, process:<id> or <producer>/<version>`

### Requirement: Массовое подтверждение
С `--all-current` команда `okf verify` SHALL подтверждать все единицы инструкций в `--repo` (по умолчанию `.`) с уровнем «не подтверждено», включая переписанные инструментом, и не трогать единицы «сломано», «перепроверить», уже подтверждённые и файлы знаний OKF.

#### Scenario: Подтвердить оставшиеся
- GIVEN `AGENTS.md` с вступлением и разделами `Auth` (подтверждён) и `Billing` (не подтверждён, код не менялся)
- WHEN запускается `okf verify --all-current --by human:ivan`
- THEN подтверждаются вступление и `AGENTS.md#Billing`, в stderr две строки `verified by`

#### Scenario: Правки okf fix тоже подтверждаются
- GIVEN `okf fix --apply` переписал `AGENTS.md#Команды`, и в карте он `edited by process:okf-fix …; not verified`
- WHEN запускается `okf verify --all-current`
- THEN `AGENTS.md#Команды` тоже подтверждается

#### Scenario: Подтверждать нечего
- GIVEN все единицы подтверждены или требуют перепроверки
- WHEN запускается `okf verify --all-current`
- THEN в stderr `okf verify: nothing to verify`, код выхода 0

#### Scenario: Нет аргументов
- GIVEN не указаны ни единицы, ни `--all-current`
- WHEN запускается `okf verify`
- THEN код выхода 2 и сообщение `name what to verify (FILE[#SECTION]) or pass --all-current`
