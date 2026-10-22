# OKF Validation Specification

## Purpose
`okf validate <bundle>` проверяет, что бандл знаний соответствует Open Knowledge Format v0.2 (профиль `okf`, по умолчанию). `okf validate <bundle> --strict` дополнительно применяет правила команды okf-ai (профиль `strict`): у каждого знания есть источник, проверка и срок свежести, и ИИ не может выдать непроверенный человеком документ за готовый.

## Requirements

### Requirement: Состав проверяемых файлов
Команда `okf validate` SHALL считать документом-концептом каждый файл `.md` бандла, кроме служебных `index.md` и `log.md` на любом уровне и файла `AGENTS.md` в корне бандла, и пропускать скрытые папки, `node_modules`, `__pycache__` и `venv`.

#### Scenario: Вложенные служебные файлы не концепты
- GIVEN в бандле есть `sub/index.md` и `sub/log.md` без шапки
- WHEN пользователь запускает `okf validate <bundle>`
- THEN эти файлы не проверяются как концепты и ошибки `type` для них нет

#### Scenario: Корневой AGENTS.md не проверяется
- GIVEN в корне бандла лежит `AGENTS.md` без YAML-шапки
- WHEN пользователь запускает `okf validate <bundle>`
- THEN для `AGENTS.md` не выводится ни одной находки
- AND ссылки из него не учитываются при поиске сирот

#### Scenario: Вложенный AGENTS.md проверяется как концепт
- GIVEN в бандле есть `team/AGENTS.md` без YAML-шапки
- WHEN пользователь запускает `okf validate <bundle>`
- THEN выводится ERROR `frontmatter` для `team/AGENTS.md`

#### Scenario: Скрытые папки пропускаются
- GIVEN в бандле есть `.drafts/a.md` без шапки
- WHEN пользователь запускает `okf validate <bundle>`
- THEN файл `.drafts/a.md` не проверяется

### Requirement: Каталог бандла должен существовать
Команда `okf validate` SHALL завершаться с кодом выхода 2 и сообщением `okf: error: bundle directory not found: <bundle>` в stderr, если каталог бандла не существует.

#### Scenario: Нет каталога
- GIVEN каталога `missing/` нет
- WHEN пользователь запускает `okf validate missing`
- THEN код выхода 2
- AND в stderr выводится `okf: error: bundle directory not found: missing`

### Requirement: Шапка документа
Каждый документ-концепт MUST начинаться с закрытого блока YAML-шапки `---`, который разбирается в словарь; иначе валидатор выводит ERROR с полем `frontmatter` (OKF §4, §11).

#### Scenario: Нет шапки
- GIVEN документ не начинается со строки `---`
- WHEN запускается `okf validate`
- THEN выводится `[ERROR] <file>: frontmatter: File must start with a YAML front matter block '---'`

#### Scenario: Шапка не закрыта
- GIVEN документ начинается с `---`, но закрывающей строки `---` нет
- WHEN запускается `okf validate`
- THEN выводится ERROR `frontmatter` с сообщением `Front matter is not closed with '---'`

#### Scenario: Синтаксическая ошибка YAML
- GIVEN в шапке YAML с синтаксической ошибкой
- WHEN запускается `okf validate`
- THEN выводится ERROR `frontmatter` с сообщением, начинающимся с `Invalid YAML:`, и номером строки ошибки

#### Scenario: Шапка пустая, список или скаляр
- GIVEN шапка пустая, или это YAML-список, или скаляр
- WHEN запускается `okf validate`
- THEN выводится ERROR `frontmatter`

#### Scenario: BOM не мешает
- GIVEN файл в UTF-8 с BOM и корректной шапкой
- WHEN запускается `okf validate`
- THEN ошибки `frontmatter` нет

#### Scenario: Файл не читается как UTF-8
- GIVEN файл `.md` в бандле не является текстом UTF-8
- WHEN запускается `okf validate`
- THEN выводится ERROR с полем `file` и сообщением `Cannot read file as UTF-8 text: ...`

### Requirement: Поле type
Документ-концепт MUST содержать поле `type` — непустую строку; незнакомые значения `type` и любые лишние ключи шапки в профиле `okf` не являются ошибкой (OKF §4.1, §11).

#### Scenario: Документ только с type
- GIVEN шапка содержит только `type: Anything`
- WHEN запускается `okf validate`
- THEN находок нет и код выхода 0

#### Scenario: Нет type
- GIVEN в шапке нет `type`
- WHEN запускается `okf validate`
- THEN выводится ERROR `type`: `Field is required`

#### Scenario: Пустой type
- GIVEN `type:` пустой или из пробелов
- WHEN запускается `okf validate`
- THEN выводится ERROR `type`: `Field must not be empty`

#### Scenario: type не строка
- GIVEN `type: [a, b]`
- WHEN запускается `okf validate`
- THEN выводится ERROR `type` с сообщением `Must be a string, got list`

#### Scenario: Лишние ключи
- GIVEN в шапке есть ключи, которых нет в OKF (например, `owner`, `provenance`)
- WHEN запускается `okf validate` без `--strict`
- THEN эти ключи не дают находок

### Requirement: Формат tags в профиле okf
Валидатор SHALL выводить WARNING `tags`, если поле `tags` есть, не равно `null` и не является YAML-списком строк.

#### Scenario: Строка вместо списка
- GIVEN `tags: a, b`
- WHEN запускается `okf validate`
- THEN выводится WARNING `tags` с сообщением `Must be a YAML list of strings like [a, b], got string`
- AND код выхода 0

#### Scenario: Список с нестроковыми элементами
- GIVEN `tags: [a, 1]`
- WHEN запускается `okf validate`
- THEN выводится WARNING `tags`

#### Scenario: Корректные tags или их нет
- GIVEN `tags: [auth, security]` или поля `tags` нет
- WHEN запускается `okf validate`
- THEN находки `tags` нет

### Requirement: Структура sources
Если поле `sources` есть, оно MUST быть списком словарей, у каждого из которых есть непустая строка `resource`; существование `resource` не проверяется (OKF §5.1).

#### Scenario: sources не список
- GIVEN `sources: /src/auth.py`
- WHEN запускается `okf validate`
- THEN выводится ERROR `sources`

#### Scenario: Запись не словарь
- GIVEN `sources: [/src/auth.py]`
- WHEN запускается `okf validate`
- THEN выводится ERROR `sources[0]`

#### Scenario: Нет resource
- GIVEN запись `sources` без `resource` или с пустым `resource`
- WHEN запускается `okf validate`
- THEN выводится ERROR `sources[i].resource`: `Field is required in every sources entry`

#### Scenario: resource не строка
- GIVEN `resource: 42`
- WHEN запускается `okf validate`
- THEN выводится ERROR `sources[i].resource`

#### Scenario: Любой вид resource допустим
- GIVEN `resource` — URL, путь `/…` от корня бандла, относительный путь или описание области со пробелами
- WHEN запускается `okf validate`
- THEN ошибок `sources` нет, даже если файла не существует

### Requirement: Структура generated
Если поле `generated` есть, оно MUST быть словарём с непустым полем `by`; поле `at` необязательно (OKF §5.2).

#### Scenario: generated не словарь
- GIVEN `generated: human:ivan`
- WHEN запускается `okf validate`
- THEN выводится ERROR `generated`

#### Scenario: Нет by
- GIVEN `generated: {at: 2026-10-19T10:00:00Z}`
- WHEN запускается `okf validate`
- THEN выводится ERROR `generated.by`: `Field is required in generated`

#### Scenario: Плохое generated.at
- GIVEN `generated: {by: human:ivan, at: 2026-10-19}`
- WHEN запускается `okf validate`
- THEN выводится ERROR `generated.at`

### Requirement: Структура verified
Если поле `verified` есть, оно MUST быть словарём `{by, at}` или списком таких словарей, где у каждой записи есть `by` и `at`; одиночный словарь считается списком из одной записи (OKF §5.2).

#### Scenario: Одиночный словарь
- GIVEN `verified: {by: human:ivan, at: 2026-10-19T10:00:00Z}`
- WHEN запускается `okf validate`
- THEN находок `verified` нет

#### Scenario: verified не словарь и не список
- GIVEN `verified: yes`
- WHEN запускается `okf validate`
- THEN выводится ERROR `verified`

#### Scenario: Запись списка не словарь
- GIVEN `verified: [human:ivan]`
- WHEN запускается `okf validate`
- THEN выводится ERROR `verified[0]`

#### Scenario: Нет by или at
- GIVEN запись `verified` без `by` или без `at`
- WHEN запускается `okf validate`
- THEN выводится ERROR `verified[i].by` или `verified[i].at` с сообщением `Field is required in every verified entry`

### Requirement: Формат акторов
Значения `generated.by` и `verified[].by` MUST иметь вид `human:<id>`, `process:<id>` или `<producer>/<version>` (OKF §7).

#### Scenario: Допустимые акторы
- GIVEN акторы `human:teamlead_ivan`, `process:okf-ci`, `docs-agent/1.4`
- WHEN запускается `okf validate`
- THEN находок об акторах нет

#### Scenario: Недопустимый актор
- GIVEN `generated: {by: ivan}`
- WHEN запускается `okf validate`
- THEN выводится ERROR `generated.by` с сообщением `Actor "ivan" must be human:<id>, process:<id> or <producer>/<version>`

### Requirement: Значение status
Поле `status`, если оно есть, MUST иметь одно из значений `draft`, `stable`, `deprecated`; документ без `status` считается `stable` (OKF §5.4).

#### Scenario: Допустимый status
- GIVEN `status: draft`
- WHEN запускается `okf validate`
- THEN находки `status` нет

#### Scenario: Значение вне словаря
- GIVEN `status: published`
- WHEN запускается `okf validate`
- THEN выводится ERROR `status`: `Value "published" must be one of draft, stable, deprecated`

### Requirement: Формат времени
Поля `stale_after`, `generated.at`, `verified[].at`, `sources[].last_modified`, `usage_window.from` и `usage_window.to` (в корне шапки и в записях `sources`) MUST быть датой-временем ISO 8601 с явным смещением UTC; дата без времени — ошибка.

#### Scenario: Дата без времени
- GIVEN `stale_after: 2027-10-19`
- WHEN запускается `okf validate`
- THEN выводится `[ERROR] <file>: stale_after: Value "2027-10-19" must be an ISO 8601 datetime with a UTC offset, e.g. 2026-06-30T14:00:00Z`

#### Scenario: Время без смещения
- GIVEN `stale_after: 2027-10-19T00:00:00`
- WHEN запускается `okf validate`
- THEN выводится ERROR `stale_after`

#### Scenario: Корректное время, в том числе без кавычек
- GIVEN `stale_after: 2027-04-19T00:00:00Z` или `2027-04-19T03:00:00+03:00`, с кавычками или без
- WHEN запускается `okf validate`
- THEN находки `stale_after` нет

#### Scenario: usage_window без границы
- GIVEN `usage_window: {from: 2026-01-01T00:00:00Z}`
- WHEN запускается `okf validate`
- THEN выводится ERROR `usage_window.to`: `Field is required`

#### Scenario: Наступивший stale_after не ошибка валидации
- GIVEN `stale_after` в прошлом
- WHEN запускается `okf validate`
- THEN находки `stale_after` нет: протухание сообщают `okf stale`, `okf trust` и `okf agents`

### Requirement: Attested Computation
Документ с `type: Attested Computation` MUST содержать непустое поле `runtime` (OKF §10.2).

#### Scenario: Нет runtime
- GIVEN `type: Attested Computation` без `runtime`
- WHEN запускается `okf validate`
- THEN выводится ERROR `runtime`: `Field is required for type Attested Computation`

#### Scenario: runtime указан
- GIVEN `type: Attested Computation` и `runtime: python3.12`
- WHEN запускается `okf validate`
- THEN находки `runtime` нет

### Requirement: Шапка index.md
Файл `index.md` MUST NOT содержать YAML-шапку, кроме корневого `index.md` бандла, шапка которого может содержать только ключ `okf_version` (OKF §3.1, §8).

#### Scenario: Корневой index.md с okf_version
- GIVEN корневой `index.md` с шапкой `okf_version: "0.2"`
- WHEN запускается `okf validate`
- THEN находок нет

#### Scenario: Другая версия OKF
- GIVEN корневой `index.md` с `okf_version: "0.3"`
- WHEN запускается `okf validate`
- THEN выводится WARNING `okf_version`: `Bundle declares OKF 0.3; okf validates against 0.2`

#### Scenario: Лишние ключи в корневом index.md
- GIVEN корневой `index.md` с шапкой `okf_version: "0.2"` и `title: X`
- WHEN запускается `okf validate`
- THEN выводится ERROR `frontmatter`, перечисляющий лишний ключ `title`

#### Scenario: Шапка во вложенном index.md
- GIVEN `sub/index.md` с любой шапкой
- WHEN запускается `okf validate`
- THEN выводится ERROR `frontmatter`

#### Scenario: Битый YAML в index.md
- GIVEN `index.md` с шапкой, которая не разбирается
- WHEN запускается `okf validate`
- THEN выводится ERROR `frontmatter`

### Requirement: Заголовки log.md
Валидатор SHALL выводить WARNING `log` для каждого заголовка второго уровня в `log.md`, который не является датой `YYYY-MM-DD` (OKF §9).

#### Scenario: Заголовок не дата
- GIVEN в `log.md` есть заголовок `## Октябрь`
- WHEN запускается `okf validate`
- THEN выводится WARNING `log`: `Date heading "Октябрь" must use YYYY-MM-DD`

#### Scenario: Несуществующая дата
- GIVEN в `log.md` есть заголовок `## 2026-13-40`
- WHEN запускается `okf validate`
- THEN выводится WARNING `log`

#### Scenario: Шапка в log.md в профиле okf
- GIVEN `log.md` с корректной YAML-шапкой
- WHEN запускается `okf validate` без `--strict`
- THEN ошибки нет: OKF шапку в `log.md` не запрещает

#### Scenario: Битая шапка в log.md
- GIVEN `log.md` с шапкой, которая не разбирается
- WHEN запускается `okf validate`
- THEN выводится ERROR `frontmatter`

### Requirement: Битые ссылки
Валидатор SHALL выводить WARNING `link` с сообщением `Broken link to <target>` для каждой markdown-ссылки (inline, reference-style, картинки), которая от корня бандла (`/…`) или относительно файла ведёт на несуществующий файл (OKF §6.1).

#### Scenario: Битая относительная ссылка
- GIVEN документ ссылается на `[x](missing.md)`, а файла нет
- WHEN запускается `okf validate`
- THEN выводится `[WARNING] <file>: link: Broken link to missing.md`
- AND код выхода 0, если ошибок нет

#### Scenario: Битая ссылка от корня бандла
- GIVEN документ во вложенной папке ссылается на `/concepts/missing_file.md`
- WHEN запускается `okf validate`
- THEN выводится WARNING `link`: `Broken link to /concepts/missing_file.md`

#### Scenario: Что не проверяется
- GIVEN в документе внешние ссылки `https://…`, якоря `#раздел`, сноски `[^id]` и ссылки внутри кода
- WHEN запускается `okf validate`
- THEN находок `link` для них нет

### Requirement: Профиль strict требует sources
В профиле `strict` документ-концепт MUST содержать непустой список `sources`.

#### Scenario: Нет sources
- GIVEN `--strict` и в шапке нет `sources` или `sources: []`
- WHEN запускается `okf validate --strict`
- THEN выводится ERROR `sources`: `List at least one source, e.g. - resource: /src/auth.py`

#### Scenario: В профиле okf sources необязательны
- GIVEN в шапке нет `sources`
- WHEN запускается `okf validate` без `--strict`
- THEN находки `sources` нет

### Requirement: Профиль strict требует verified
В профиле `strict` документ-концепт MUST содержать непустое поле `verified`.

#### Scenario: Нет verified
- GIVEN `--strict` и `verified` нет, пустое или `[]`
- WHEN запускается `okf validate --strict`
- THEN выводится ERROR `verified`: `Field is required: record the review, e.g. {by: human:<id>, at: <datetime>}`

### Requirement: Профиль strict требует срок свежести
В профиле `strict` документ-концепт MUST содержать `stale_after`, который не раньше самой поздней `verified[].at`.

#### Scenario: Нет stale_after
- GIVEN `--strict` и `stale_after` нет
- WHEN запускается `okf validate --strict`
- THEN выводится ERROR `stale_after`: `Field is required, e.g. 2026-06-30T14:00:00Z`

#### Scenario: Протух раньше проверки
- GIVEN `stale_after: 2026-01-01T00:00:00Z` и `verified` с `at: 2026-10-19T10:00:00Z`
- WHEN запускается `okf validate --strict`
- THEN выводится ERROR `stale_after`: `2026-01-01T00:00:00Z is earlier than the latest verified.at 2026-10-19T10:00:00Z`

#### Scenario: stale_after позже проверки
- GIVEN `stale_after` позже всех `verified[].at`
- WHEN запускается `okf validate --strict`
- THEN находки `stale_after` нет

### Requirement: ИИ не выдаёт себя за человека
В профиле `strict` документ, автор которого (`generated.by`) не `human:`, со статусом `stable` (явно или по умолчанию) и непустым `verified` без единой записи `human:`, MUST давать ERROR `verified`.

#### Scenario: Агент пометил документ stable без человека
- GIVEN `generated: {by: docs-agent/1.4}`, `status` не указан, `verified: [{by: process:okf-ci, at: …}]`
- WHEN запускается `okf validate --strict`
- THEN выводится `[ERROR] <file>: verified: Document generated by "docs-agent/1.4" is status: stable without human review; add a human:<id> entry to verified or set status: draft`
- AND код выхода 1

#### Scenario: Черновик агента допустим
- GIVEN тот же документ со `status: draft`
- WHEN запускается `okf validate --strict`
- THEN этой ошибки нет

#### Scenario: Человек подтвердил
- GIVEN тот же документ, и в `verified` есть запись `human:teamlead_ivan`
- WHEN запускается `okf validate --strict`
- THEN этой ошибки нет

#### Scenario: Документ написал человек, проверил процесс
- GIVEN `generated.by: human:ivan` и `verified` только от `process:ci`
- WHEN запускается `okf validate --strict`
- THEN этой ошибки нет

#### Scenario: В профиле okf правило не действует
- GIVEN документ агента со `status: stable` без проверки человеком
- WHEN запускается `okf validate` без `--strict`
- THEN ошибки `verified` нет: в OKF это просто уровень доверия machine-confirmed

### Requirement: Формат tags в профиле strict
В профиле `strict` поле `tags`, если оно есть и не `null`, MUST быть YAML-списком строк; нарушение — ERROR `tags`.

#### Scenario: Строка вместо списка в strict
- GIVEN `tags: a, b`
- WHEN запускается `okf validate --strict`
- THEN выводится ERROR `tags` и код выхода 1

### Requirement: Словарь type в профиле strict
В профиле `strict` валидатор SHALL выводить WARNING `type` с подсказкой ближайшего значения, если `type` не входит в словарь команды: `Concept`, `Architecture`, `Table`, `Dataset`, `Metric`, `API Endpoint`, `Runbook`, `Playbook`, `Guide`, `Reference`, `Policy`, `Service`, `Repository`, `Glossary Term`, `Attested Computation`.

#### Scenario: Похожее значение
- GIVEN `type: Endpoint`
- WHEN запускается `okf validate --strict`
- THEN выводится `[WARNING] <file>: type: Value "Endpoint" is not in the okf-ai type dictionary (did you mean "API Endpoint"?)`
- AND код выхода 0, если ошибок нет

#### Scenario: Отличие только регистром и разделителями
- GIVEN `type: api-endpoint`
- WHEN запускается `okf validate --strict`
- THEN подсказка — `"API Endpoint"`

#### Scenario: Значение из словаря
- GIVEN `type: Runbook`
- WHEN запускается `okf validate --strict`
- THEN находки `type` нет

#### Scenario: Без strict словарь не применяется
- GIVEN `type: Endpoint`
- WHEN запускается `okf validate` без `--strict`
- THEN находки `type` нет

### Requirement: Шапка log.md в профиле strict
В профиле `strict` файл `log.md` MUST NOT содержать YAML-шапку.

#### Scenario: Шапка в log.md
- GIVEN `log.md` с корректной шапкой
- WHEN запускается `okf validate --strict`
- THEN выводится ERROR `frontmatter`: `log.md must not contain YAML front matter`

### Requirement: Сироты в профиле strict
В профиле `strict` валидатор SHALL выводить WARNING `link` с сообщением `Orphan file: no other file in the bundle links to it` для документа-концепта, на который не ссылается ни один другой файл бандла.

#### Scenario: Документ без входящих ссылок
- GIVEN на `a.md` никто не ссылается
- WHEN запускается `okf validate --strict`
- THEN выводится WARNING `link` для `a.md` о сироте

#### Scenario: Ссылка из любого файла засчитывается
- GIVEN на `a.md` ссылается `index.md` или другой документ
- WHEN запускается `okf validate --strict`
- THEN предупреждения о сироте для `a.md` нет

#### Scenario: Ссылки из AGENTS.md и на себя не считаются
- GIVEN на `a.md` ссылаются только корневой `AGENTS.md` и сам `a.md`
- WHEN запускается `okf validate --strict`
- THEN выводится WARNING о сироте для `a.md`

#### Scenario: Без strict сироты не ищутся
- GIVEN на `a.md` никто не ссылается
- WHEN запускается `okf validate` без `--strict`
- THEN предупреждения о сироте нет

### Requirement: Подсказки миграции с полей v1
В профиле `strict` сообщение об отсутствующем `sources`, `verified` или `stale_after` SHALL подсказывать замену, если в шапке есть старые поля командной спеки v1 `provenance`, `trust` или `freshness`.

#### Scenario: Старые поля v1
- GIVEN шапка с `provenance.sources`, `trust.verified_by` и `freshness.stale_after` вместо полей OKF
- WHEN запускается `okf validate --strict`
- THEN ошибка `sources` содержит `(found provenance.sources: OKF v0.2 uses top-level sources)`
- AND ошибка `verified` содержит `(found trust.verified_by: OKF v0.2 uses verified)`
- AND ошибка `stale_after` содержит `(found freshness.stale_after: OKF v0.2 uses top-level stale_after)`

### Requirement: Официальные примеры OKF проходят
Профиль `okf` SHALL не выдавать ни одной ошибки на официальном примере бандла OKF (`tests/fixtures/okf-official`, acme_retail).

#### Scenario: Официальный бандл
- GIVEN официальный пример бандла OKF
- WHEN запускается `okf validate tests/fixtures/okf-official`
- THEN ошибок нет и код выхода 0

### Requirement: Формат вывода
Каждая находка SHALL печататься в stdout одной строкой `[LEVEL] file_path: field_name: message`, где `file_path` — путь относительно рабочей папки с прямыми слэшами, а сводка `okf validate (<profile>): <N> files, <E> errors, <W> warnings` печатается в stderr.

#### Scenario: Строка находки
- GIVEN в `docs/user.md` битая ссылка на `/concepts/missing_file.md`
- WHEN пользователь запускает `okf validate docs` из корня репозитория
- THEN в stdout выводится `[WARNING] docs/user.md: link: Broken link to /concepts/missing_file.md`

#### Scenario: Сводка в stderr
- GIVEN бандл из 3 файлов с одной ошибкой и двумя предупреждениями
- WHEN запускается `okf validate <bundle> --strict`
- THEN в stderr выводится `okf validate (strict): 3 files, 1 errors, 2 warnings`

### Requirement: Аннотации GitHub
С `--format github` валидатор SHALL печатать каждую находку командой GitHub Actions `::error|warning|notice file=<path>,line=<n>,title=okf <field>::<message>` с экранированием `%`, `\r`, `\n`, а в свойствах также `:` и `,`.

#### Scenario: Ошибка как аннотация
- GIVEN ERROR `type` в строке 2 файла `a.md`
- WHEN запускается `okf validate <bundle> --format github`
- THEN выводится строка, начинающаяся с `::error file=a.md,line=2,title=okf type::`

#### Scenario: Строка неизвестна
- GIVEN у находки нет номера строки
- WHEN запускается `okf validate --format github`
- THEN в аннотации `line=1`

### Requirement: Коды выхода
Команда `okf validate` SHALL возвращать код выхода 1, если найдена хотя бы одна ошибка (ERROR), и 0, если находок нет или есть только предупреждения.

#### Scenario: Чистый бандл
- GIVEN бандл без находок
- WHEN запускается `okf validate`
- THEN код выхода 0

#### Scenario: Только предупреждения
- GIVEN бандл только с WARNING
- WHEN запускается `okf validate`
- THEN код выхода 0

#### Scenario: Есть ошибка
- GIVEN бандл с хотя бы одним ERROR
- WHEN запускается `okf validate`
- THEN код выхода 1
