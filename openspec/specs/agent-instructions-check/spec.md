# Agent Instructions Check Specification

## Purpose
`okf agents-check [repo]` — страж инструкций для ИИ-агентов: находит `AGENTS.md`, `CLAUDE.md`, правила Cursor и Copilot, достаёт из них пути и команды и проверяет их по репозиторию, сравнивает `AGENTS.md` с `CLAUDE.md` в одной папке, а в pull request сообщает, какие упомянутые файлы этот набор изменений переименовал, удалил или поменял.

## Requirements

### Requirement: Поиск файлов инструкций
Команда `okf agents-check` SHALL проверять `AGENTS.md`, `CLAUDE.md` и `.cursorrules` на любом уровне, `.github/copilot-instructions.md`, `.cursor/rules/**/*.mdc` и `.md` в `.ruler/` и `.rulesync/`, пропуская `.git`, `node_modules`, виртуальные окружения, `dist`, `build`, `vendor`, `third_party` и скрытые папки, кроме `.cursor`, `.github`, `.ruler`, `.rulesync`.

#### Scenario: Все виды инструкций
- GIVEN в репозитории есть `AGENTS.md`, `packages/api/AGENTS.md`, `CLAUDE.md`, `.cursor/rules/backend.mdc`, `.cursorrules` и `.github/copilot-instructions.md`
- WHEN пользователь запускает `okf agents-check`
- THEN проверяется каждый из этих файлов

#### Scenario: Чужие инструкции в зависимостях
- GIVEN `node_modules/pkg/AGENTS.md` и `vendor/lib/CLAUDE.md`
- WHEN запускается `okf agents-check`
- THEN эти файлы не проверяются

#### Scenario: Нет каталога
- GIVEN каталога `missing/` нет
- WHEN запускается `okf agents-check missing`
- THEN код выхода 2 и в stderr `okf: error: directory not found: missing`

### Requirement: Извлечение путей
Команда SHALL извлекать пути из inline-кода, markdown-ссылок, импортов `@path` в `CLAUDE.md` и «голых» слов текста вида `src/auth.py`, причём голый путь учитывается, только если его первая папка существует, суффиксы `:42` и `#L10` отбрасываются, а шапка правил Cursor и блоки кода не на shell не считаются текстом.

#### Scenario: Голое слово, не путь
- GIVEN в тексте встречаются `and/or` и `CI/CD`, а папок `and` и `CI` нет
- WHEN запускается `okf agents-check`
- THEN эти слова не проверяются как пути

#### Scenario: Голый путь под существующей папкой
- GIVEN в тексте написано `см. src/gone.py`, папка `src` есть, файла нет
- WHEN запускается `okf agents-check`
- THEN выводится находка о несуществующем `src/gone.py`

#### Scenario: Номер строки отбрасывается
- GIVEN в инструкции `` `src/auth.py:42` ``, файл `src/auth.py` есть
- WHEN запускается `okf agents-check`
- THEN находки нет

#### Scenario: Внешние ссылки
- GIVEN в инструкции ссылки `https://…` и якоря `#раздел`
- WHEN запускается `okf agents-check`
- THEN они не проверяются как пути

### Requirement: Извлечение команд
Команда SHALL извлекать команды из блоков кода без языка или на shell (`bash`, `sh`, `zsh`, `console` и т.п.) и из inline-кода, начинающегося с известного запускателя (`npm`, `pnpm`, `yarn`, `bun`, `make`, `just`, `pytest`, `python`, `node`, `bash`, `uv`, `poetry`, `./…`), понимая приглашения `$ `, комментарии `#`, цепочки `&&`, `|`, `;`, `cd dir && …`, переменные `FOO=1 cmd` и обёртки `uv run` и `poetry run`.

#### Scenario: Цепочка с переходом в папку
- GIVEN в shell-блоке `cd web && npm run build`, а в `web/package.json` есть скрипт `build`
- WHEN запускается `okf agents-check`
- THEN находки нет: скрипт ищется в `web/package.json`

#### Scenario: Блок кода на другом языке
- GIVEN в блоке кода с языком `python` есть строка `make deploy`
- WHEN запускается `okf agents-check`
- THEN она не проверяется как команда

#### Scenario: Обёртка poetry run
- GIVEN `` `poetry run pytest tests/test_gone.py` `` и файла нет
- WHEN запускается `okf agents-check`
- THEN выводится находка `"poetry run pytest tests/test_gone.py": tests/test_gone.py does not exist`

### Requirement: Существование путей
Команда SHALL сообщать `"<path>" does not exist (line <n>)` с полем `path` для упомянутого пути, которого нет ни от папки файла, ни от папки, к которой относится инструкция, ни от корня репозитория.

#### Scenario: Битый путь
- GIVEN в `AGENTS.md` строка 20 упоминает `` `src/config.py` ``, файла нет и в истории git он не переименовывался
- WHEN запускается `okf agents-check`
- THEN выводится `[WARNING] AGENTS.md: path: "src/config.py" does not exist (line 20)`

#### Scenario: Путь от корня во вложенной инструкции
- GIVEN `packages/api/AGENTS.md` упоминает `scripts/release.sh`, который есть только в корне репозитория
- WHEN запускается `okf agents-check`
- THEN находки нет

#### Scenario: Сокращённый путь
- GIVEN инструкция упоминает `model/time.ts`, а в репозитории ровно один файл `src/model/time.ts`
- WHEN запускается `okf agents-check`
- THEN находки нет

### Requirement: Заглушки и результаты сборки не ломаются
Команда SHALL выводить INFO вместо предупреждения для путей-заглушек (`path/to/…`, `…`, `src/foo.py`, `your-project/…`, `example/…`) и для путей, которые игнорирует git или которые являются обычными результатами сборки (`dist/`, `build/`, `node_modules/`, `.env`, `coverage/` и т.п.).

#### Scenario: Заглушка
- GIVEN инструкция упоминает `` `path/to/file.ts` ``
- WHEN запускается `okf agents-check --strict`
- THEN выводится `[INFO] AGENTS.md: path: "path/to/file.ts" looks like a placeholder, not checked (line <n>)`
- AND код выхода 0

#### Scenario: Путь из .gitignore
- GIVEN `.gitignore` содержит `generated/`, инструкция упоминает `generated/schema.ts`, папки нет
- WHEN запускается `okf agents-check`
- THEN выводится INFO `"generated/schema.ts" is ignored by git (a build output?), not checked`

#### Scenario: Результат сборки
- GIVEN инструкция упоминает `dist/index.js`, папки `dist` нет
- WHEN запускается `okf agents-check`
- THEN выводится INFO, а не WARNING

#### Scenario: Существующий путь, похожий на заглушку
- GIVEN инструкция упоминает `src/foo.py`, и такой файл есть
- WHEN запускается `okf agents-check`
- THEN находки нет

### Requirement: Переехавшие файлы
Команда SHALL сообщать `"<path>" was moved to <new path> on <date>`, если упомянутого файла нет, а история git показывает его переименование в существующий файл.

#### Scenario: Файл переименовали дважды
- GIVEN `src/config.py` переименован в `src/settings.py`, затем в `src/conf/settings.py` 2026-10-01
- WHEN запускается `okf agents-check`
- THEN выводится `[WARNING] AGENTS.md: path: "src/config.py" was moved to src/conf/settings.py on 2026-10-01 (line 3)`

### Requirement: Скрипты package.json
Для `npm run X`, `pnpm X`, `yarn X`, `bun run X` и встроенных `test`, `start`, `stop`, `restart` команда SHALL проверять, что в ближайшем вверх по папкам `package.json` есть скрипт `X`, и сообщать `"<command>": no script "X" in <package.json>`.

#### Scenario: Нет скрипта
- GIVEN `CLAUDE.md` строка 6 содержит `npm run test:unit`, а в `package.json` нет скрипта `test:unit`
- WHEN запускается `okf agents-check`
- THEN выводится `[WARNING] CLAUDE.md: command: "npm run test:unit": no script "test:unit" in package.json (line 6)`

#### Scenario: Нет package.json
- GIVEN `npm run build` и ни одного `package.json` до корня
- WHEN запускается `okf agents-check`
- THEN выводится находка `"npm run build": no package.json found`

#### Scenario: package.json не JSON
- GIVEN ближайший `package.json` не разбирается как JSON
- WHEN запускается `okf agents-check`
- THEN выводится находка `… is not valid JSON`

#### Scenario: Бинарь из зависимостей
- GIVEN `pnpm vitest`, скрипта `vitest` нет, но `vitest` есть в `devDependencies`
- WHEN запускается `okf agents-check`
- THEN находки нет

#### Scenario: npm start с server.js
- GIVEN `npm start`, скрипта `start` нет, рядом с `package.json` есть `server.js`
- WHEN запускается `okf agents-check`
- THEN находки нет

#### Scenario: Команды workspaces не угадываются
- GIVEN `pnpm -F api test` или `npm run build --workspace api`
- WHEN запускается `okf agents-check`
- THEN скрипт не проверяется и находки нет

### Requirement: Менеджер пакетов
Команда SHALL сообщать `"<command>": this project uses <manager> (<evidence>)`, если команда запускает другой менеджер пакетов, чем указан в поле `packageManager` ближайшего `package.json` или следует из lock-файла рядом с ним.

#### Scenario: npm в проекте на pnpm
- GIVEN рядом с `package.json` лежит `pnpm-lock.yaml`, инструкция говорит `npm run dev`
- WHEN запускается `okf agents-check`
- THEN выводится находка `"npm run dev": this project uses pnpm (pnpm-lock.yaml)`

#### Scenario: Поле packageManager
- GIVEN `"packageManager": "yarn@4.1.0"`, инструкция говорит `pnpm test`
- WHEN запускается `okf agents-check`
- THEN выводится находка `this project uses yarn ("packageManager" in package.json)`

### Requirement: Цели make и рецепты just
Команда SHALL сообщать `"<command>": no target "X" in <Makefile>` или `no recipe "X" in <justfile>`, если в ближайшем `Makefile` нет цели или в `justfile` нет рецепта, и не сообщать об этом, если файл может определять больше целей (`include`, шаблонные цели, `import`/`mod` в justfile) или `Makefile` генерируется CMake, autotools или meson.

#### Scenario: Нет цели
- GIVEN `make deploy`, в `Makefile` нет цели `deploy` и нет `include`
- WHEN запускается `okf agents-check`
- THEN выводится находка `"make deploy": no target "deploy" in Makefile`

#### Scenario: Makefile с include
- GIVEN `make deploy`, в `Makefile` есть `include rules.mk`
- WHEN запускается `okf agents-check`
- THEN находки нет

#### Scenario: Нет Makefile
- GIVEN `make test` и ни одного `Makefile` до корня, и нет `CMakeLists.txt`, `configure`, `configure.ac`, `meson.build`
- WHEN запускается `okf agents-check`
- THEN выводится находка `"make test": no Makefile found`

#### Scenario: Makefile генерируется
- GIVEN `make test`, `Makefile` нет, но есть `CMakeLists.txt`
- WHEN запускается `okf agents-check`
- THEN находки нет

#### Scenario: Нет рецепта just
- GIVEN `just lint`, в `justfile` нет рецепта `lint`
- WHEN запускается `okf agents-check`
- THEN выводится находка `"just lint": no recipe "lint" in justfile`

### Requirement: Файлы скриптов и тестов
Команда SHALL проверять существование файла, который запускает команда (`./scripts/x.sh`, `pytest <path>`, `python <path>.py`, `bash|node|sh <path>`), и сообщать `"<command>": <file> does not exist` или `"<file>" does not exist`.

#### Scenario: Битый скрипт
- GIVEN `AGENTS.md` строка 14 содержит `./scripts/seed_db.sh`, файла нет и в истории git он не переименовывался
- WHEN запускается `okf agents-check`
- THEN выводится `[WARNING] AGENTS.md: command: "./scripts/seed_db.sh" does not exist (line 14)`

#### Scenario: Тест удалён
- GIVEN `pytest tests/test_gone.py`, файла нет
- WHEN запускается `okf agents-check`
- THEN выводится находка `"pytest tests/test_gone.py": tests/test_gone.py does not exist`

#### Scenario: Код вместо файла
- GIVEN `python -c "print(1)"` или `node -e "…"`
- WHEN запускается `okf agents-check`
- THEN файл не ищется и находки нет

### Requirement: Маски и globs Cursor
Команда SHALL сообщать `"<pattern>" matches no files`, если маска в тексте инструкции или в поле `globs:` шапки правила Cursor не совпадает ни с одним файлом.

#### Scenario: Пустая маска Cursor
- GIVEN `.cursor/rules/web.mdc` с `globs: web/**/*.tsx`, таких файлов нет
- WHEN запускается `okf agents-check`
- THEN выводится находка `globs`: `"web/**/*.tsx" matches no files`

#### Scenario: Маска совпадает
- GIVEN `` `src/**/*.py` `` и в `src/` есть `.py`-файлы
- WHEN запускается `okf agents-check`
- THEN находки нет

### Requirement: Согласованность AGENTS.md и CLAUDE.md
Команда SHALL выводить WARNING `consistency` с сообщением `Instructions for different agents disagree: …`, если `AGENTS.md` и `CLAUDE.md` в одной папке дают разные команды для одной задачи, разные менеджеры пакетов или разные пути к одноимённому файлу, кроме случая, когда `CLAUDE.md` импортирует `AGENTS.md`.

#### Scenario: Разные команды для тестов
- GIVEN `AGENTS.md` говорит `npm test`, а `CLAUDE.md` строка 6 — `npm run test:unit`
- WHEN запускается `okf agents-check`
- THEN выводится `[WARNING] CLAUDE.md: consistency: Instructions for different agents disagree: AGENTS.md runs "npm test", CLAUDE.md runs "npm run test:unit" (line 6)`

#### Scenario: Разные менеджеры пакетов
- GIVEN `AGENTS.md` использует `pnpm`, `CLAUDE.md` — `yarn`
- WHEN запускается `okf agents-check`
- THEN выводится WARNING `consistency`: `AGENTS.md uses pnpm, CLAUDE.md uses yarn`

#### Scenario: CLAUDE.md импортирует AGENTS.md
- GIVEN `CLAUDE.md` начинается с `@AGENTS.md` и добавляет свой раздел
- WHEN запускается `okf agents-check`
- THEN находок `consistency` нет

#### Scenario: Расхождение не становится ошибкой
- GIVEN расхождение команд и флаг `--strict`
- WHEN запускается `okf agents-check --strict`
- THEN расхождение остаётся WARNING

### Requirement: Ссылки и сгенерированные копии проверяются один раз
Команда SHALL не проверять повторно `CLAUDE.md`, который является симлинком или однострочной ссылкой на `AGENTS.md`, и копии, сгенерированные Ruler или rulesync (маркер в файле или блок Ruler в `.gitignore`), а выводить для них INFO `file` с указанием источника.

#### Scenario: Однострочная ссылка
- GIVEN `CLAUDE.md` содержит только `AGENTS.md`
- WHEN запускается `okf agents-check`
- THEN единственная находка для `CLAUDE.md` — `[INFO] CLAUDE.md: file: Link to AGENTS.md; its sections are checked there`

#### Scenario: Копия Ruler
- GIVEN `.gitignore` содержит блок `# START Ruler Generated Files` с `/CLAUDE.md`, а правила лежат в `.ruler/instructions.md`
- WHEN запускается `okf agents-check`
- THEN для `CLAUDE.md` выводится INFO `Generated from .ruler/ (Ruler); its sections are checked there`
- AND битые пути сообщаются только в `.ruler/instructions.md`

### Requirement: Уровни и строгий режим
Битые пути, команды и маски SHALL выводиться как WARNING с кодом выхода 0, а с `--strict` — как ERROR с кодом выхода 1.

#### Scenario: По умолчанию
- GIVEN в инструкциях битый скрипт
- WHEN запускается `okf agents-check`
- THEN находка — WARNING, код выхода 0

#### Scenario: Строгий режим
- GIVEN в инструкциях битый скрипт
- WHEN запускается `okf agents-check --strict`
- THEN находка — ERROR, код выхода 1

### Requirement: Нечитаемый файл инструкций
Команда SHALL выводить находку `file` с сообщением `Cannot read file as UTF-8 text: …`, если файл инструкций не читается как UTF-8: WARNING с кодом выхода 0 по умолчанию и ERROR с кодом выхода 1 с `--strict`.

#### Scenario: Бинарный CLAUDE.md
- GIVEN `CLAUDE.md` не является текстом UTF-8
- WHEN запускается `okf agents-check`
- THEN выводится WARNING `file` и код выхода 0

#### Scenario: Бинарный CLAUDE.md в строгом режиме
- GIVEN `CLAUDE.md` не является текстом UTF-8
- WHEN запускается `okf agents-check --strict`
- THEN выводится ERROR `file` и код выхода 1

### Requirement: Проверка набора изменений
С `--base REF` (изменения с merge-base, включая незакоммиченные, с поиском переименований) или `--changed FILE...` (пути от корня репозитория; `-` читает их из stdin) команда SHALL сообщать об упомянутых инструкцией файлах, которые этот набор изменений переименовал, удалил или изменил.

#### Scenario: Файл переименован в PR
- GIVEN в ветке `git mv src/config.py src/settings.py`, `AGENTS.md` строка 20 упоминает `src/config.py`
- WHEN запускается `okf agents-check --base main`
- THEN выводится находка `"src/config.py" was renamed to src/settings.py in this change (line 20)` уровня WARNING (ERROR с `--strict`)

#### Scenario: Файл удалён в PR
- GIVEN упомянутый файл удалён в этом наборе изменений
- WHEN запускается `okf agents-check --base main`
- THEN выводится находка `"<path>" was deleted or renamed in this change`

#### Scenario: Код изменён, инструкция нет
- GIVEN PR меняет `src/auth.py`, упомянутый в `AGENTS.md`, и не трогает `AGENTS.md`
- WHEN запускается `okf agents-check --base main`
- THEN выводится WARNING `"src/auth.py" changed in this change; the instruction may be outdated`

#### Scenario: Код и инструкция изменены вместе
- GIVEN PR меняет и `src/auth.py`, и `AGENTS.md`
- WHEN запускается `okf agents-check --base main`
- THEN выводится INFO `"src/auth.py" changed; the instruction was updated in the same change`

#### Scenario: Правка связанного документа
- GIVEN PR меняет `docs/setup.md`, на который ссылается инструкция
- WHEN запускается `okf agents-check --base main`
- THEN находки нет

#### Scenario: Изменённые файлы из stdin
- GIVEN `git diff --name-only main | okf agents-check --changed -`
- WHEN команда читает stdin
- THEN каждая непустая строка считается изменённым путём от корня репозитория

#### Scenario: Неизвестная ветка
- GIVEN ref `no-such-ref` не существует
- WHEN запускается `okf agents-check --base no-such-ref`
- THEN код выхода 2 и в stderr `okf: error: git … failed: …`

### Requirement: Сводка и формат вывода
Команда SHALL печатать находки строками `[LEVEL] file: field: message (line <n>)` в stdout (с `--format github` — аннотациями GitHub Actions) и сводку `okf agents-check: <F> instruction files, <P> paths, <C> commands, <E> errors, <W> warnings` в stderr.

#### Scenario: Сводка
- GIVEN демо `examples/demo` с тремя предупреждениями
- WHEN запускается `okf agents-check examples/demo`
- THEN в stderr выводится строка, начинающаяся с `okf agents-check: 4 instruction files` и содержащая `0 errors, 3 warnings`

#### Scenario: Аннотации
- GIVEN битый скрипт в строке 14 `AGENTS.md`
- WHEN запускается `okf agents-check --format github`
- THEN выводится строка `::warning file=AGENTS.md,line=14,title=okf command::…`
