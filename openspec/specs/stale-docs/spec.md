# Stale Docs Specification

## Purpose
`okf stale <bundle>` находит документы базы знаний OKF, которые могли устареть: их источник (`sources[].resource`) изменён в наборе изменений или у них наступил `stale_after`. Команда подсказывает, кого попросить перепроверить документ, и никогда не валит проверку.

## Requirements

### Requirement: Изменённый источник помечает документ
Команда `okf stale` SHALL выводить WARNING `sources` с сообщением `Source <resource> changed (<changed paths>); document may be outdated[, ask <reviewer> to review it]` для каждого источника документа, совпавшего с изменённым файлом, если сам документ в этом наборе изменений не менялся.

#### Scenario: Код поменялся, документ нет
- GIVEN `examples/demo/knowledge/auth_flow.md` с `resource: ../src/auth.py`, проверенный `human:teamlead_ivan`
- WHEN запускается `okf stale examples/demo/knowledge --changed examples/demo/src/auth.py`
- THEN выводится `[WARNING] examples/demo/knowledge/auth_flow.md: sources: Source ../src/auth.py changed (examples/demo/src/auth.py); document may be outdated, ask human:teamlead_ivan to review it`

#### Scenario: Изменён файл, не связанный с документами
- GIVEN изменён только `README.md`, на который не ссылается ни один `resource`
- WHEN запускается `okf stale <bundle> --changed README.md`
- THEN находок `sources` нет

#### Scenario: Пути в выводе совпадают с resource
- GIVEN `resource: src/auth.py`, бандл в корне репозитория, изменён `src/auth.py`
- WHEN запускается `okf stale`
- THEN сообщение — `Source src/auth.py changed; document may be outdated…` без пути в скобках

### Requirement: Документ обновлён вместе с источником
Команда SHALL выводить INFO `sources` с сообщением `Source <resource> changed …; document was updated in the same change` вместо предупреждения, если в том же наборе изменений изменён и сам документ.

#### Scenario: PR правит код и документ
- GIVEN изменены `src/auth.py` и `knowledge/auth_flow.md`, который на него ссылается
- WHEN запускается `okf stale knowledge --changed src/auth.py knowledge/auth_flow.md`
- THEN для `auth_flow.md` выводится INFO, а не WARNING

### Requirement: Разрешение resource
Команда SHALL понимать `resource` так: `/path` — от корня бандла; `./path` и `../path` — от файла документа; `path` — от файла документа или от корня бандла; `https://github.com/<owner>/<repo>/blob|tree/<ref>/<path>` — файл `<path>` этого репозитория; другие URL и описания области ни с чем не сопоставляются.

#### Scenario: Путь от корня бандла
- GIVEN бандл `docs/`, документ `docs/a/x.md` с `resource: /src/auth.py`
- WHEN изменён `docs/src/auth.py`
- THEN документ помечается

#### Scenario: Путь без префикса, как в официальных примерах
- GIVEN бандл `docs/`, документ `docs/a/x.md` с `resource: src/auth.py` (путь от корня бандла без `/`)
- WHEN изменён `docs/src/auth.py`
- THEN документ помечается
- AND изменение `docs/a/src/auth.py` (путь от файла) тоже помечает документ

#### Scenario: Ссылка на GitHub
- GIVEN `resource: https://github.com/acme/app/blob/main/src/auth.py`
- WHEN изменён `src/auth.py`
- THEN документ помечается

#### Scenario: Внешний URL и описание области
- GIVEN `resource: https://wiki.example.com/page` и `resource: все сервисы биллинга`
- WHEN изменены любые файлы
- THEN эти источники не дают находок

#### Scenario: Описание области с пробелами не считается путём
- GIVEN `resource: all queries in project X` и изменён файл `all`
- WHEN запускается `okf stale`
- THEN источник пропускается как описание области, так же как в `okf trust`

### Requirement: Папки и маски в источниках
Источник-папка SHALL совпадать с любым изменённым файлом внутри неё, а источник-маска (`*`, `?`, `[`) — с изменёнными файлами, подходящими под маску.

#### Scenario: Папка
- GIVEN `resource: /src/billing/`
- WHEN изменён `src/billing/tariff.py`
- THEN документ помечается

#### Scenario: Маска
- GIVEN `resource: /src/*.py`
- WHEN изменён `src/auth.py`
- THEN документ помечается

### Requirement: Нормализация изменённых путей
Команда SHALL нормализовать изменённые пути: обратные слэши заменяются прямыми, ведущие `./` и `/` убираются, пустые строки пропускаются.

#### Scenario: Путь в стиле Windows
- GIVEN `--changed .\src\auth.py`
- WHEN документ ссылается на `src/auth.py`
- THEN документ помечается

### Requirement: К кому обращаться
Подсказка `ask <reviewer> to review it` SHALL называть последнего по времени проверявшего человека из `verified`, иначе автора `generated.by`, если он `human:`, а без человека подсказка не выводится.

#### Scenario: Последний проверявший человек
- GIVEN `verified` от `human:ivan` (2026-09-01) и `human:maria` (2026-10-01)
- WHEN источник изменён
- THEN подсказка — `ask human:maria to review it`

#### Scenario: Только автор-человек
- GIVEN `verified` нет, `generated.by: human:pavel`
- WHEN источник изменён
- THEN подсказка — `ask human:pavel to review it`

#### Scenario: Людей нет
- GIVEN `generated.by: docs-agent/1.4`, `verified` только от `process:ci`
- WHEN источник изменён
- THEN сообщение заканчивается на `document may be outdated` без подсказки

### Requirement: Наступивший stale_after
Команда SHALL выводить WARNING `stale_after` с сообщением `<stale_after> has passed (now <now>); document is stale[, ask <reviewer> to review it]`, если момент `--now` (по умолчанию текущий) не раньше `stale_after`, независимо от изменённых файлов.

#### Scenario: Срок прошёл
- GIVEN `stale_after: 2026-11-10T00:00:00Z`, проверял `human:maria_backend`
- WHEN запускается `okf stale <bundle> --now 2026-11-10`
- THEN выводится WARNING `stale_after`: `2026-11-10T00:00:00Z has passed (now 2026-11-10T00:00:00Z); document is stale, ask human:maria_backend to review it`

#### Scenario: Срок не наступил
- GIVEN `stale_after: 2027-04-19T00:00:00Z`
- WHEN запускается `okf stale <bundle> --now 2026-10-22`
- THEN находки `stale_after` нет

#### Scenario: Неверный --now
- GIVEN `--now tomorrow`
- WHEN запускается `okf stale . --now tomorrow`
- THEN команда завершается ошибкой использования с кодом выхода 2

### Requirement: Документы с битой шапкой пропускаются
Команда SHALL пропускать документы без шапки или с битой шапкой: о них сообщает `okf validate`.

#### Scenario: Битая шапка
- GIVEN документ без YAML-шапки и изменённые файлы
- WHEN запускается `okf stale`
- THEN для этого документа находок нет

### Requirement: Источник изменённых файлов
Команда SHALL брать изменённые файлы из `--changed FILE...` (пути от корня репозитория, `-` читает их из stdin) и из `--base REF` (изменения с merge-base с REF до рабочей копии, включая незакоммиченные, оба имени переименованных файлов), а корнем репозитория считать `--repo-root`, иначе корень git, иначе рабочую папку.

#### Scenario: Изменения против базовой ветки
- GIVEN в ветке изменён `examples/demo/src/auth.py` относительно `main`
- WHEN запускается `okf stale examples/demo/knowledge --base main`
- THEN `auth_flow.md` помечается как возможно устаревший

#### Scenario: Изменённые файлы из stdin
- GIVEN `git diff --name-only main | okf stale knowledge --changed -`
- WHEN команда читает stdin
- THEN каждая непустая строка считается изменённым файлом

#### Scenario: Без изменений
- GIVEN нет ни `--changed`, ни `--base`
- WHEN запускается `okf stale <bundle>`
- THEN проверяется только `stale_after`

### Requirement: Коды выхода
Команда `okf stale` SHALL возвращать код выхода 0 при любых находках и 2, если каталог бандла не найден или не удалось вызвать git для `--base`.

#### Scenario: Находки не валят проверку
- GIVEN несколько документов могли устареть
- WHEN запускается `okf stale`
- THEN код выхода 0

#### Scenario: Неизвестный ref
- GIVEN ref `no-such-ref-okf` не существует
- WHEN запускается `okf stale examples/demo/knowledge --base no-such-ref-okf`
- THEN код выхода 2 и в stderr сообщение об ошибке git

#### Scenario: Нет бандла
- GIVEN каталога нет
- WHEN запускается `okf stale missing`
- THEN код выхода 2 и в stderr `okf: error: bundle directory not found: missing`

### Requirement: Сводка и формат вывода
Команда SHALL печатать находки строками `[LEVEL] file: field: message` (с `--format github` — аннотациями GitHub Actions) в stdout и сводку `okf stale: <N> changed files, <X> documents may be outdated, <U> updated alongside their sources, <E> past stale_after` в stderr.

#### Scenario: Сводка
- GIVEN изменён один файл, один документ мог устареть, у одного наступил `stale_after`
- WHEN запускается `okf stale`
- THEN в stderr выводится `okf stale: 1 changed files, 1 documents may be outdated, 0 updated alongside their sources, 1 past stale_after`
