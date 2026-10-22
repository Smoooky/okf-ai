# CI Action Specification

## Purpose
GitHub Action `.github/workflows/okf.yml` запускает проверки okf-ai на каждом pull request и push в `main`: тесты, карту доверия, предложенные правки, страж инструкций и базы знаний — и собирает отчёт в лог, job summary, аннотации и обновляемый комментарий PR. Action только сообщает и предлагает: он ничего не коммитит и не открывает PR.

## Requirements

### Requirement: Когда запускается
Workflow SHALL запускаться на каждое событие `pull_request` и на `push` в ветку `main`.

#### Scenario: Pull request
- GIVEN открыт или обновлён pull request
- WHEN GitHub обрабатывает событие
- THEN запускаются задачи `Unit tests` и `Agent instructions and knowledge`

#### Scenario: Push в другую ветку
- GIVEN push в ветку `feature/x` без pull request
- WHEN GitHub обрабатывает событие
- THEN workflow не запускается

### Requirement: Модульные тесты
Задача `Unit tests` SHALL устанавливать пакет с зависимостями `.[test]` на Python 3.12 и запускать `pytest -q` с правами только `contents: read`.

#### Scenario: Тест падает
- GIVEN один тест не проходит
- WHEN выполняется задача `Unit tests`
- THEN задача завершается с ошибкой

### Requirement: Полная история git
Задача `Agent instructions and knowledge` MUST получать полную историю репозитория (`actions/checkout` с `fetch-depth: 0`), чтобы даты изменений и merge-base с базовой веткой были известны.

#### Scenario: Конфигурация checkout
- GIVEN файл `.github/workflows/okf.yml`
- WHEN читается шаг `actions/checkout` задачи `knowledge`
- THEN в нём `fetch-depth: 0`

### Requirement: Минимальные права
Задача `Agent instructions and knowledge` SHALL запрашивать только права `contents: read` и `pull-requests: write` (для комментария с отчётом).

#### Scenario: Права задачи
- GIVEN файл workflow
- WHEN читается блок `permissions` задачи `knowledge`
- THEN в нём только `contents: read` и `pull-requests: write`

### Requirement: Что проверяется и где
Workflow SHALL брать папку инструкций из `OKF_REPO`, бандл знаний из `OKF_BUNDLE`, дополнительные аргументы `okf agents-check` из `OKF_AGENTS_ARGS` и `okf validate` из `OKF_VALIDATE_ARGS` (по умолчанию `--strict`).

#### Scenario: Подключение к своему репозиторию
- GIVEN файл workflow скопирован, `OKF_REPO: .`, `OKF_BUNDLE: docs/knowledge`
- WHEN запускается workflow
- THEN `okf trust`, `okf fix` и `okf agents-check` работают по корню репозитория, а `okf validate` и `okf stale` — по `docs/knowledge`

#### Scenario: Битые ссылки как ошибки
- GIVEN `OKF_AGENTS_ARGS: --strict`
- WHEN в инструкциях есть битый путь
- THEN `okf agents-check` возвращает 1 и проверка падает

### Requirement: Режим pull request и push
В pull request workflow SHALL запускать `okf trust` и `okf fix` с `--since origin/<base>`, а `okf agents-check` и `okf stale` с `--base origin/<base>`; на push — без этих аргументов, по всей карте.

#### Scenario: PR в main
- GIVEN pull request в `main`
- WHEN выполняется шаг `okf trust`
- THEN команда — `okf trust $OKF_REPO --since origin/main`, и в отчёте раздел называется `okf trust: what this PR makes to recheck`

#### Scenario: Push в main
- GIVEN push в `main`
- WHEN выполняется шаг `okf trust`
- THEN команда — `okf trust $OKF_REPO` без `--since`, раздел отчёта — `okf trust: trust map`

### Requirement: Правки только предлагаются
Action MUST NOT коммитить, пушить или открывать pull request: `okf fix` запускается без `--apply`, а его дифф попадает в отчёт в раздел `okf fix: proposed changes (not committed)`.

#### Scenario: Есть механическая правка
- GIVEN в инструкциях упомянут переехавший файл
- WHEN выполняется workflow
- THEN дифф правки показан в job summary блоком `diff`, а ветка PR не изменилась

### Requirement: Черновики LLM только с секретом
Workflow SHALL запускать `okf fix --draft`, только если в репозитории задан секрет `ANTHROPIC_API_KEY` или `OKF_LLM_API_KEY` (с переменными `OKF_LLM_BASE_URL` и `OKF_LLM_MODEL`), а иначе дописывать в отчёт строку `LLM drafts skipped: no ANTHROPIC_API_KEY or OKF_LLM_API_KEY secret.`.

#### Scenario: Секрета нет
- GIVEN в репозитории не заданы секреты LLM
- WHEN выполняется шаг `okf fix`
- THEN показываются только механические правки и строка `LLM drafts skipped: …`

#### Scenario: PR из форка
- GIVEN pull request из форка, которому GitHub не передаёт секреты
- WHEN выполняется шаг `okf fix`
- THEN черновики пропускаются так же, как без секрета

#### Scenario: Секрет задан
- GIVEN задан секрет `ANTHROPIC_API_KEY`
- WHEN выполняется шаг `okf fix`
- THEN `okf fix` запускается с `--draft`, черновики попадают в дифф отчёта

### Requirement: Аннотации на строках
Workflow SHALL запускать `okf trust`, `okf agents-check`, `okf validate` и `okf stale` с `--format github`, чтобы находки стали аннотациями на строках файлов в PR.

#### Scenario: Битый путь в инструкции
- GIVEN `AGENTS.md` строка 14 ссылается на несуществующий скрипт
- WHEN выполняется workflow
- THEN в PR появляется аннотация на строке 14 `AGENTS.md`

### Requirement: Отчёт в job summary
Workflow SHALL собирать отчёт `okf-report.md` с маркером `<!-- okf-ai-report -->`, заголовком с `OKF_REPO` и `OKF_BUNDLE` и разделами `okf trust`, `okf fix`, `okf agents-check`, `okf validate`, `okf stale`, где заголовок раздела помечен ❌ при ненулевом коде выхода, ⚠️ при строках `[WARNING]` и ✅ иначе, а пустой вывод заменён на `No issues.`, и добавлять его в job summary даже при упавших шагах.

#### Scenario: Ошибка валидатора
- GIVEN `okf validate` вернул 1
- WHEN собирается отчёт
- THEN раздел называется `❌ okf validate: OKF v0.2 knowledge`

#### Scenario: Только предупреждения
- GIVEN `okf agents-check` вернул 0 и вывел строки `[WARNING]`
- WHEN собирается отчёт
- THEN раздел называется `⚠️ okf agents-check: instructions for AI agents`

#### Scenario: Находок нет
- GIVEN `okf stale` ничего не вывел
- WHEN собирается отчёт
- THEN раздел `✅ okf stale: documents that may be outdated` содержит `No issues.`

### Requirement: Обновляемый комментарий PR
Для pull request из того же репозитория workflow SHALL публиковать отчёт комментарием и при повторных запусках обновлять прежний комментарий бота с маркером `<!-- okf-ai-report -->`, а не создавать новый; неудача публикации не валит задачу.

#### Scenario: Повторный запуск
- GIVEN в PR уже есть комментарий бота с маркером
- WHEN workflow запускается снова
- THEN этот комментарий обновляется

#### Scenario: PR из форка
- GIVEN pull request из форка
- WHEN выполняется workflow
- THEN комментарий не публикуется, отчёт есть только в job summary

### Requirement: Что валит проверку
Задача SHALL завершаться с ошибкой и сообщением `okf found errors, see the job summary`, только если `okf agents-check` или `okf validate` вернули ненулевой код; предупреждения, карта доверия, `okf stale` и `okf fix` проверку не валят.

#### Scenario: Только предупреждения
- GIVEN `okf agents-check` и `okf validate` вернули 0, `okf trust` нашёл «перепроверить», `okf stale` нашёл устаревшие документы
- WHEN завершается задача
- THEN задача успешна

#### Scenario: Ошибка в базе знаний
- GIVEN `okf validate --strict` нашёл ERROR
- WHEN завершается задача
- THEN задача падает после публикации отчёта
