# CI Action Specification

## Purpose
GitHub Action `.github/workflows/okf.yml` запускает проверки okf-ai на каждом pull request и push в `main`: тесты, карту доверия, предложенные правки, контрольные вопросы, страж инструкций и базы знаний — и собирает отчёт в лог, job summary, аннотации, обновляемый комментарий PR и страницу-артефакт. Задача проверки только сообщает и предлагает: она ничего не коммитит и не открывает PR. По желанию задание `auto-pr` превращает правки в pull request `[OKF-Update]`, а задание `notify` по расписанию напоминает подтверждавшим, что пора перепроверить.

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
Задача `Agent instructions and knowledge` MUST NOT коммитить, пушить или открывать pull request: `okf fix` запускается без `--apply` и `--pr`, а его дифф попадает в отчёт в раздел `okf fix: proposed changes (not committed)`.

#### Scenario: Есть механическая правка
- GIVEN в инструкциях упомянут переехавший файл
- WHEN выполняется workflow
- THEN дифф правки показан в job summary блоком `diff`, а ветка PR не изменилась

### Requirement: Черновики LLM только с секретом
Workflow SHALL запускать `okf fix --draft`, только если задан секрет `ANTHROPIC_API_KEY` или заданы все три `OKF_LLM_API_KEY`, `OKF_LLM_BASE_URL` и `OKF_LLM_MODEL`, а иначе дописывать в отчёт строку, начинающуюся с `LLM drafts skipped: set`.

#### Scenario: Секрета нет
- GIVEN в репозитории не заданы секреты LLM
- WHEN выполняется шаг `okf fix`
- THEN показываются только механические правки и строка `LLM drafts skipped: …`

#### Scenario: Задан только ключ OKF_LLM_API_KEY
- GIVEN задан секрет `OKF_LLM_API_KEY`, но не заданы `OKF_LLM_BASE_URL` и `OKF_LLM_MODEL`
- WHEN выполняется шаг `okf fix`
- THEN `--draft` не добавляется, в отчёте строка `LLM drafts skipped: set …`

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

### Requirement: Запуск по расписанию и вручную
Workflow SHALL также запускаться по расписанию `0 7 * * 1-5` (будни, 07:00 UTC) и вручную (`workflow_dispatch` с булевым входом `okf-auto-pr`, по умолчанию `false`), причём задача `Agent instructions and knowledge` по расписанию не запускается.

#### Scenario: Запуск по расписанию
- GIVEN наступило время расписания
- WHEN GitHub обрабатывает событие `schedule`
- THEN задача `knowledge` пропускается, а запускается задача `notify`

#### Scenario: Ручной запуск
- GIVEN пользователь нажал Run workflow, не отметив `okf-auto-pr`
- WHEN GitHub обрабатывает событие `workflow_dispatch`
- THEN задание `auto-pr` не запускается

### Requirement: Страница карты доверия артефактом
Задача `Agent instructions and knowledge` SHALL записывать карту доверия страницей `okf trust "$OKF_REPO" --html report.html` (в PR — с `--since origin/<base>`) и загружать её артефактом `okf-trust-report` даже при упавших шагах, а если страницы нет — ничего не загружать без ошибки.

#### Scenario: Pull request
- GIVEN pull request в `main`
- WHEN выполняется задача `knowledge`
- THEN среди артефактов запуска есть `okf-trust-report` с `report.html` о том, что этот PR делает «перепроверить»

#### Scenario: Шаг упал раньше
- GIVEN шаг до записи страницы упал и `report.html` не создан
- WHEN выполняется шаг загрузки артефакта
- THEN шаг не падает и артефакт не загружается

### Requirement: Автоматический pull request выключен по умолчанию
Задание `auto-pr` SHALL запускаться только на push в `main` при переменной репозитория `OKF_AUTO_PR` равной `true` или при ручном запуске с `okf-auto-pr`, и выполнять `okf fix "$OKF_REPO" --pr` (с `--draft`, если задан `ANTHROPIC_API_KEY` или все три `OKF_LLM_API_KEY`, `OKF_LLM_BASE_URL` и `OKF_LLM_MODEL`) на полной истории git.

#### Scenario: Переменная не задана
- GIVEN в репозитории нет переменной `OKF_AUTO_PR`
- WHEN происходит push в `main`
- THEN задание `auto-pr` не запускается

#### Scenario: Включено переменной
- GIVEN `OKF_AUTO_PR=true`, в `main` упомянут переехавший файл
- WHEN происходит push в `main`
- THEN `okf fix --pr` открывает pull request `[OKF-Update]` или обновляет уже открытый

#### Scenario: Pull request
- GIVEN `OKF_AUTO_PR=true`
- WHEN GitHub обрабатывает событие `pull_request`
- THEN задание `auto-pr` не запускается

### Requirement: Права задания auto-pr
Задание `auto-pr` SHALL запрашивать только права `contents: write` и `pull-requests: write` и передавать `okf fix --pr` токен запуска как `GH_TOKEN`.

#### Scenario: Конфигурация задания
- GIVEN файл workflow
- WHEN читается задание `auto-pr`
- THEN `permissions` равен `{contents: write, pull-requests: write}`, а у шага `okf fix --pr` `GH_TOKEN: ${{ github.token }}`

### Requirement: Напоминания по расписанию
Задача `notify` SHALL запускаться только по расписанию с правами `contents: read` и выполнять `okf notify "$OKF_REPO"` на полной истории git, только если задан секрет `OKF_SLACK_WEBHOOK` или `OKF_TEAMS_WEBHOOK`, а без них все её шаги пропускаются.

#### Scenario: Секрет не задан
- GIVEN в репозитории нет секретов вебхуков
- WHEN срабатывает расписание
- THEN шаги задачи `notify` пропускаются, ничего не отправляется

#### Scenario: Задан вебхук Slack
- GIVEN задан секрет `OKF_SLACK_WEBHOOK`
- WHEN срабатывает расписание
- THEN `okf notify` отправляет напоминания тем, кто подтверждал разделы, которые теперь «перепроверить»

### Requirement: Контрольные вопросы в отчёте
Задача `Agent instructions and knowledge` SHALL запускать `okf shadow "$OKF_REPO"` (в PR — с `--base origin/<base>`), только если есть `$OKF_REPO/.okf/shadow.yml` и ключ LLM, никогда не валить из-за него проверку и добавлять в отчёт раздел `okf shadow: control questions` с результатом или строкой `No control questions in $OKF_REPO/.okf/shadow.yml.` либо `Shadow test skipped: no LLM key.`.

#### Scenario: Вопросов нет
- GIVEN в `$OKF_REPO/.okf/` нет `shadow.yml`
- WHEN выполняется шаг `okf shadow`
- THEN `okf shadow` не запускается, а в разделе отчёта строка `No control questions in …`

#### Scenario: Вопросы есть, ключа нет
- GIVEN `shadow.yml` есть, секреты LLM не заданы
- WHEN выполняется шаг `okf shadow`
- THEN в разделе отчёта `Shadow test skipped: no LLM key.`

#### Scenario: Вопрос стал хуже в PR
- GIVEN `shadow.yml` и ключ LLM заданы, PR сделал документ «перепроверить»
- WHEN выполняется шаг `okf shadow`
- THEN в разделе отчёта строка `worse than origin/<base>`, а задача не падает из-за этого

### Requirement: Коннекторы из настроек репозитория
Задачи `knowledge`, `auto-pr` и `notify` SHALL передавать okf настройки коннекторов из переменных репозитория (`OKF_CONFLUENCE_URL`, `OKF_JIRA_URL`, `OKF_ATLASSIAN_EMAIL`) и секретов (`OKF_ATLASSIAN_TOKEN`, `OKF_ATLASSIAN_PAT`, `OKF_NOTION_TOKEN`, `OKF_SLACK_TOKEN`), так что без них шаги работают только по git и в сеть к этим системам не ходят.

#### Scenario: Настроек нет
- GIVEN ни переменные, ни секреты коннекторов не заданы
- WHEN выполняется workflow
- THEN удалённые источники документов получают статус `unknown: connector not configured`, а уровни карты считаются по git
