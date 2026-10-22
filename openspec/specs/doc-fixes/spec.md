# Doc Fixes Specification

## Purpose
`okf fix [repo]` предлагает правки для того, что нашли `okf trust` и `okf agents-check`: механические без ИИ (переехавший файл, переименованный скрипт, переехавший источник OKF) и, с `--draft` и ключом пользователя, черновики от LLM для разделов, чей код поменялся. Правки печатаются диффом или пишутся с `--apply`, и правленое остаётся «не подтверждено», пока человек не выполнит `okf verify`.

## Requirements

### Requirement: Вывод правок
Команда `okf fix` SHALL печатать предложенные правки unified diff в stdout (сначала механические, затем черновики поверх них), в stderr — по строке на правку и на то, что нужно исправить вручную, и сводку `okf fix: <N> mechanical fixes, <D> drafts, <M> need a manual fix`, не меняя файлы без `--apply`.

#### Scenario: Дифф без записи
- GIVEN в демо-истории `./scripts/seed_db.sh` переехал в `./scripts/seed.sh`
- WHEN запускается `okf fix`
- THEN в stdout дифф `AGENTS.md` с заменой `./scripts/seed_db.sh` на `./scripts/seed.sh`
- AND в stderr `okf fix: AGENTS.md#Команды: ./scripts/seed_db.sh moved to ./scripts/seed.sh`
- AND рабочая копия не изменилась, код выхода 0

#### Scenario: Дифф применяется git
- GIVEN вывод сохранён в `fix.patch`
- WHEN выполняется `git apply fix.patch`
- THEN правки применяются к рабочей копии

#### Scenario: Нет каталога
- GIVEN каталога нет
- WHEN запускается `okf fix missing`
- THEN код выхода 2 и в stderr `okf: error: directory not found: missing`

### Requirement: Новый путь переехавшего файла
Если упомянутый в инструкции файл по истории git переехал, команда SHALL заменять в этой строке только этот путь целиком на новый, записанный в том же виде (от той же базы, с `./`, с ведущим `/` или с `/` в конце, как было), сохраняя выравнивание комментариев.

#### Scenario: Сохранение вида и выравнивания
- GIVEN строка `./scripts/seed_db.sh      # тестовые данные`, файл переехал в `scripts/seed.sh`
- WHEN запускается `okf fix`
- THEN строка становится `./scripts/seed.sh         # тестовые данные`

#### Scenario: Путь — часть более длинного
- GIVEN строка ``see `src/a.py` and `src/a.pyc` ``, `src/a.py` переехал в `lib/a.py`
- WHEN запускается `okf fix`
- THEN строка становится ``see `lib/a.py` and `src/a.pyc` ``
- AND строка `vendor/src/a.py` не меняется

#### Scenario: Более длинный путь стоит в строке первым
- GIVEN строка ``backup `src/config.py.bak`, real `src/config.py` ``, `src/config.py` переехал в `src/settings.py`
- WHEN запускается `okf fix`
- THEN строка становится ``backup `src/config.py.bak`, real `src/settings.py` ``
- AND пути вида `src/config.py_old` и `src/config.py-x` тоже не меняются, а точка в конце предложения после пути продолжением имени не считается

#### Scenario: Путь от корня во вложенной инструкции
- GIVEN `packages/api/AGENTS.md` упоминает `scripts/start.sh` (от своей папки) и `/docs/api.md` (от корня), файлы переехали в `packages/api/bin/start.sh` и `docs/reference/api.md`
- WHEN запускается `okf fix`
- THEN правки — `scripts/start.sh` → `bin/start.sh` и `/docs/api.md` → `/docs/reference/api.md`

#### Scenario: Строку нельзя поправить точно
- GIVEN путь найден, но заменить его целым токеном в строке не удаётся
- WHEN запускается `okf fix`
- THEN правка не делается, а в stderr — `… moved to …, but the line could not be edited exactly` как ручная правка

### Requirement: Переименование в этом pull request
С `--since REF` команда SHALL исправлять пути к файлам, которые этот набор изменений переименовал, на их новые имена.

#### Scenario: Переименование в ветке
- GIVEN в ветке `git mv src/config.py src/settings.py`, инструкция упоминает `src/config.py`
- WHEN запускается `okf fix --since main`
- THEN в диффе `src/config.py` заменён на `src/settings.py`

#### Scenario: --since вне git
- GIVEN каталог не является репозиторием git
- WHEN запускается `okf fix <dir> --since main`
- THEN код выхода 2 и сообщение `--since needs a git repository`

### Requirement: Переименованный скрипт package.json
Если `npm run X` указывает на скрипт, которого нет в `package.json`, а по истории git та же команда теперь записана ровно под одним другим именем, команда SHALL заменять имя скрипта на новое, а иначе — сообщать, что нужна ручная правка.

#### Scenario: Скрипт переименован
- GIVEN скрипт `test:unit` с командой `vitest run` переименован в `unit` с той же командой
- WHEN запускается `okf fix`
- THEN `npm run test:unit` меняется на `npm run unit`, причина — `script "test:unit" is now "unit" in package.json`

#### Scenario: Неоднозначное переименование
- GIVEN та же команда теперь записана под двумя разными именами
- WHEN запускается `okf fix`
- THEN правки нет, в stderr — `…: needs a manual fix`

### Requirement: Переехавший источник OKF
Если `sources[].resource` файла знаний OKF не существует, а по истории git файл переехал, команда SHALL заменять путь в шапке на новый в том же виде.

#### Scenario: Источник переехал
- GIVEN `knowledge/local_setup_guide.md` с `resource: ../src/config.py`, файл переименован в `src/settings.py`
- WHEN запускается `okf fix`
- THEN в диффе шапки `../src/config.py` заменён на `../src/settings.py`, причина — `source ../src/config.py moved to ../src/settings.py`

#### Scenario: Источник удалён
- GIVEN источник удалён без замены
- WHEN запускается `okf fix`
- THEN в stderr `okf fix: <file> (line <n>): source "<resource>" does not exist: needs a manual fix`

### Requirement: Правки не выдумываются
Для удалённого без замены пути, отсутствующего скрипта, цели или маски без совпадений команда MUST NOT предлагать правку; вместо неё в stderr выводится `okf fix: <unit> (line <n>): <problem>: needs a manual fix`.

#### Scenario: Несуществующий npm-скрипт
- GIVEN `CLAUDE.md` строка 6 содержит `npm run test:unit`, такого скрипта нет и не было
- WHEN запускается `okf fix`
- THEN в stderr `okf fix: CLAUDE.md (line 6): "npm run test:unit": no script "test:unit" in package.json: needs a manual fix`
- AND в диффе `CLAUDE.md` нет

### Requirement: Что не правится
Команда SHALL не править копии, сгенерированные Ruler или rulesync, `CLAUDE.md`-ссылки на `AGENTS.md` и роутер `okf agents`, а с `--only UNIT` (можно повторять) — ничего, кроме указанных единиц.

#### Scenario: Только одна единица
- GIVEN поправить можно `AGENTS.md#Команды` и `AGENTS.md#Auth`
- WHEN запускается `okf fix --only AGENTS.md#Auth`
- THEN в диффе только правки `AGENTS.md#Auth`

#### Scenario: Копия Ruler
- GIVEN `CLAUDE.md` — копия из `.ruler/`, в обоих битый переехавший путь
- WHEN запускается `okf fix`
- THEN правится только источник в `.ruler/`

### Requirement: Применение правок
С `--apply` команда SHALL записывать правки в рабочую копию, сохраняя переводы строк файла (`\r\n` или `\n`), и печатать в stderr `okf fix: applied to <units>; they stay not verified until okf verify`.

#### Scenario: Применить
- GIVEN есть механическая правка
- WHEN запускается `okf fix --apply`
- THEN файл изменён, в stderr — строка `applied to …`

#### Scenario: Файл с CRLF
- GIVEN файл инструкций с переводами строк `\r\n`
- WHEN запускается `okf fix --apply`
- THEN в файле остаются `\r\n`

#### Scenario: Нечего применять
- GIVEN правок нет
- WHEN запускается `okf fix --apply`
- THEN файлы не меняются, код выхода 0

### Requirement: Правленое не подтверждено
Каждая применённая правка MUST записываться как `generated: {by, at}` — в `.okf/trust.yml` для раздела инструкций и в шапку для файла OKF — с актором `process:okf-fix` для механических правок и `<producer>/<model>` для черновиков, и никогда как `verified`.

#### Scenario: После механической правки
- GIVEN `okf fix --apply` исправил `AGENTS.md#Команды`
- WHEN запускается `okf trust`
- THEN `AGENTS.md#Команды` — `[INFO] … edited by process:okf-fix on <date>; not verified`
- AND в `.okf/trust.yml` у записи есть `generated`, а `verified` не добавлен

#### Scenario: Файл OKF после правки
- GIVEN `okf fix --apply` поправил источник в `knowledge/local_setup_guide.md`
- WHEN открыть шапку файла
- THEN `generated` равен `{ by: process:okf-fix, at: <now> }`, записи `verified` не изменились

### Requirement: Какие разделы получают черновик
С `--draft` (или `--replay`) команда SHALL просить черновик только для единиц, чей код изменился после подтверждения или последней правки (а с `--since` — в этом наборе изменений), и передавать модели только путь файла, текст единицы, список изменённых источников и их `git diff` с момента последнего подтверждения (с `--since` — с базы изменения).

#### Scenario: Раздел с изменённым кодом
- GIVEN `AGENTS.md#Auth` подтверждён 2026-09-05, `src/auth.py` изменён 2026-10-20
- WHEN запускается `okf fix --draft`
- THEN модель получает текст раздела `## Auth`, `src/auth.py` и дифф `src/auth.py` с 2026-09-05

#### Scenario: Раздел без изменений кода
- GIVEN раздел «подтверждено» или «не подтверждено» без изменений кода
- WHEN запускается `okf fix --draft`
- THEN черновик для него не запрашивается

### Requirement: Ключ LLM пользователя
Команда SHALL брать модель из переменных окружения: `OKF_LLM_BASE_URL` + `OKF_LLM_API_KEY` + `OKF_LLM_MODEL` — OpenAI-совместимый эндпоинт (приоритет), иначе `ANTHROPIC_API_KEY` — Claude с моделью `OKF_LLM_MODEL` или по умолчанию `claude-opus-5-5`, с лимитом ответа `OKF_LLM_MAX_TOKENS` (по умолчанию 8000).

#### Scenario: Ключ Anthropic
- GIVEN задан только `ANTHROPIC_API_KEY`
- WHEN запускается `okf fix --draft`
- THEN черновики пишет Claude `claude-opus-5-5`, актор — `anthropic/claude-opus-5-5`

#### Scenario: OpenAI-совместимый эндпоинт
- GIVEN заданы `OKF_LLM_BASE_URL`, `OKF_LLM_API_KEY`, `OKF_LLM_MODEL=qwen/qwen3:32b` и `ANTHROPIC_API_KEY`
- WHEN запускается `okf fix --draft`
- THEN используется OpenAI-совместимый эндпоинт, актор — `openai-compatible/qwen-qwen3-32b`

#### Scenario: Нет ключа
- GIVEN ни одна из переменных не задана
- WHEN запускается `okf fix --draft`
- THEN в stderr `okf fix: no LLM key, so no drafts: set ANTHROPIC_API_KEY, or OKF_LLM_BASE_URL + OKF_LLM_API_KEY + OKF_LLM_MODEL for an OpenAI-compatible endpoint; showing the mechanical fixes only`
- AND выводятся только механические правки, код выхода 0

### Requirement: Лимит диффа
Команда MUST NOT отправлять модели дифф длиннее `--max-diff` символов (по умолчанию 40 000) и не обрезает его, а отклоняет черновик с причиной.

#### Scenario: Дифф больше лимита
- GIVEN дифф источников раздела — 50 000 символов
- WHEN запускается `okf fix --draft`
- THEN модель не вызывается, в stderr `okf fix --draft: <unit>: no draft: the diff is 50000 characters, over --max-diff 40000; not sent`

#### Scenario: Пустой дифф
- GIVEN дифф изменённых источников пуст
- WHEN запускается `okf fix --draft`
- THEN черновик отклонён: `no diff of the changed sources to show the model`

### Requirement: Проверка черновика
Черновик SHALL отклоняться с причиной, если модель не вернула текст раздела, сказала, что раздел верен (`changed: false`) или вернула его без изменений, изменила заголовок раздела или вернула текст намного длиннее раздела (больше чем втрое плюс 2000 символов).

#### Scenario: Изменён заголовок
- GIVEN модель вернула раздел с заголовком `## Аутентификация` вместо `## Auth`
- WHEN проверяется черновик
- THEN черновик отклонён: `the draft changed the heading to "## Аутентификация"`

#### Scenario: Раздел всё ещё верен
- GIVEN модель ответила `changed: false`
- WHEN проверяется черновик
- THEN черновик отклонён: `the model says the section is still correct: confirm it with okf verify`

#### Scenario: Пустой ответ
- GIVEN в ответе модели нет текста раздела
- WHEN проверяется черновик
- THEN черновик отклонён: `the model returned no section`

### Requirement: Пути и команды черновика проверяются
Каждый путь и каждая команда, которые черновик добавляет в раздел, MUST проходить ту же проверку, что в `okf agents-check`; новое несуществующее, переехавшее или похожее на заглушку упоминание отклоняет черновик с причиной `the draft mentions <subjects>, which does not exist`.

#### Scenario: Выдуманная команда
- GIVEN модель добавила в раздел `npm run auth:reset`, такого скрипта нет
- WHEN проверяется черновик
- THEN черновик отклонён, в stderr `okf fix --draft: <unit>: no draft: the draft mentions "npm run auth:reset", which does not exist`

#### Scenario: Выдуманный путь
- GIVEN модель добавила `` `src/auth/locks.py` ``, файла нет
- WHEN проверяется черновик
- THEN черновик отклонён

#### Scenario: Старое битое упоминание
- GIVEN битое упоминание было в разделе и до черновика
- WHEN проверяется черновик
- THEN черновик из-за него не отклоняется

#### Scenario: Принятый черновик
- GIVEN черновик прошёл все проверки
- WHEN запускается `okf fix --draft`
- THEN в stderr `okf fix --draft: <unit>: <summary> (by <actor>; not verified)`, в stdout дифф раздела

### Requirement: Отказы модели не роняют команду
Ошибка вызова модели (неверный ключ, лимит запросов, ошибка HTTP, сеть недоступна, отказ модели, достигнут лимит токенов, ответ не JSON) SHALL отклонять черновик этой единицы с причиной, не прерывая остальные правки и не меняя код выхода 0.

#### Scenario: Неверный ключ
- GIVEN `ANTHROPIC_API_KEY` неверный
- WHEN запускается `okf fix --draft`
- THEN в stderr `okf fix --draft: <unit>: no draft: the Anthropic API rejected ANTHROPIC_API_KEY`, механические правки выводятся, код выхода 0

#### Scenario: Лимит токенов
- GIVEN ответ модели обрезан по лимиту токенов
- WHEN запускается `okf fix --draft`
- THEN причина — `the draft hit the token limit (8000); raise OKF_LLM_MAX_TOKENS`

#### Scenario: Ответ не JSON
- GIVEN модель ответила текстом, а не JSON
- WHEN запускается `okf fix --draft`
- THEN причина — `the model did not answer with JSON`

### Requirement: Сохранённый ответ модели
С `--replay FILE` команда SHALL брать ответы для черновиков из сохранённого JSON-файла (ответы по именам единиц, актор из его полей `provider` и `model`) вместо вызова модели, проверяя их так же, как живые ответы.

#### Scenario: Демо без ключа
- GIVEN `.okf/auth_draft.example.json` с ответом для `AGENTS.md#Auth`
- WHEN запускается `okf fix --draft --only AGENTS.md#Auth --replay .okf/auth_draft.example.json --apply`
- THEN черновик применяется, в stderr `… (by anthropic/claude-opus-5-5; not verified)`

#### Scenario: Нет ответа для единицы
- GIVEN в файле нет ответа для `AGENTS.md#Billing`
- WHEN для неё запрашивается черновик
- THEN причина — `the saved answers have nothing for AGENTS.md#Billing`

#### Scenario: Файл не читается
- GIVEN файла ответа нет или это не JSON
- WHEN запускается `okf fix --replay missing.json`
- THEN код выхода 2 и в stderr `okf: error: cannot read missing.json: …`
