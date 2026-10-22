# Shadow Testing Specification

## Purpose
`okf shadow [repo]` проверяет не тексты базы знаний, а то, как ими пользуется агент: на каждый контрольный вопрос модель по роутеру выбирает документы, читает их и отвечает, а okf проверяет, открыла ли она нужное, не опиралась ли на то, что карта доверия велит перепроверить, и есть ли в ответе ожидаемые факты. С `--base REF` те же вопросы прогоняются на базовой ветке, и видно, что стало хуже.

## Requirements

### Requirement: Файл контрольных вопросов
Команда SHALL читать вопросы из `--questions FILE` (по умолчанию `.okf/shadow.yml`, путь от `repo`): список `questions:`, где у каждого вопроса обязателен `question`, `id` по умолчанию `q<номер>`, `expect_documents` — пути от корня бандла (`./` и `/` в начале отбрасываются) и `expect_facts` — строки, которые должны быть в ответе.

#### Scenario: Вопрос без id
- GIVEN `questions:` с одним вопросом `question: Q?`, `expect_documents: [./a.md]`, `expect_facts: [1]`
- WHEN файл читается
- THEN вопрос `q1` ждёт документ `a.md` и факт `1`

#### Scenario: Нет списка вопросов
- GIVEN файл без ключа `questions:` или с пустым списком
- WHEN запускается `okf shadow`
- THEN код выхода 2 и в stderr ``okf: error: <file>: expected `questions:` with a list of questions``

#### Scenario: Вопрос без текста
- GIVEN у второго вопроса нет `question`
- WHEN запускается `okf shadow`
- THEN код выхода 2 и сообщение ``<file>: question 2 needs `question:` ``

#### Scenario: Файла нет
- GIVEN `.okf/shadow.yml` нет
- WHEN запускается `okf shadow`
- THEN код выхода 2 и сообщение `cannot read <file>: …`

### Requirement: Без ключа ничего не запускается
Команда SHALL брать модель так же, как `okf fix --draft` (`ANTHROPIC_API_KEY` или `OKF_LLM_BASE_URL` + `OKF_LLM_API_KEY` + `OKF_LLM_MODEL`), или сохранённые ответы из `--replay FILE`, а без ключа и `--replay` ничего не запускать и завершаться с кодом выхода 2 и сообщением `okf shadow: no LLM key, nothing was run: …`.

#### Scenario: Нет ключа
- GIVEN не заданы ни `ANTHROPIC_API_KEY`, ни `OKF_LLM_API_KEY`
- WHEN запускается `okf shadow`
- THEN код выхода 2, в stderr `no LLM key, nothing was run`, модель не вызывается

#### Scenario: Сохранённые ответы
- GIVEN файл с сохранёнными ответами модели
- WHEN запускается `okf shadow --replay <file>`
- THEN вопросы проверяются по этим ответам без вызова модели

### Requirement: Какой бандл проверяется
Команда SHALL проверять бандл из `--bundle DIR`, а без него — единственный бандл OKF в репозитории, и завершаться с кодом выхода 2 и `okf: error: no OKF bundle|several bundles in <repo>; name one with --bundle DIR`, если бандла нет или их несколько.

#### Scenario: Несколько бандлов
- GIVEN в репозитории два бандла
- WHEN запускается `okf shadow` без `--bundle`
- THEN код выхода 2 и сообщение `several bundles in <repo>; name one with --bundle DIR`

### Requirement: Два шага модели
На каждый вопрос команда SHALL сначала показывать модели только роутер `AGENTS.md` бандла (а если его нет — сгенерированный как `okf agents`) и вопрос и брать из ответа не больше пяти путей документов, затем передавать тексты выбранных документов и вопрос и получать ответ со списком документов, на которые модель опиралась; пути, которых нет в бандле, не открываются, а путь с папкой бандла в начале (`knowledge/x.md`) понимается как `x.md`.

#### Scenario: Роутер, затем документы
- GIVEN вопрос о цене минуты и модель, выбравшая `billing_service.md`
- WHEN проверяется вопрос
- THEN первый запрос содержит роутер со ссылкой `[billing_service.md](billing_service.md)`, второй — `<document path="billing_service.md">` с текстом документа

#### Scenario: Выдуманный путь
- GIVEN модель выбрала `knowledge/api_start_ride.md` и `nope.md`
- WHEN проверяется вопрос
- THEN открыт `api_start_ride.md`, а `nope.md` не открыт

### Requirement: Три проверки
Каждый вопрос SHALL проходить три проверки: `documents` — открыты все `expect_documents`, `trust` — среди документов, на которые опирался ответ (без списка — все открытые), нет документов уровня «перепроверить» или «сломано» по карте доверия, и `facts` — каждый из `expect_facts` есть в ответе без учёта регистра и лишних пробелов.

#### Scenario: Хороший ответ
- GIVEN модель открыла `billing_service.md` («подтверждено») и ответила «Минута — 8 ₽.», ожидается факт `8 ₽`
- WHEN проверяется вопрос
- THEN все три проверки пройдены

#### Scenario: Всё мимо
- GIVEN ожидался `billing_service.md` и факт `8 ₽`, а модель открыла `api_start_ride.md` («перепроверить») и ответила «Не знаю.»
- WHEN проверяется вопрос
- THEN не пройдены все три проверки, проблемы — `did not open billing_service.md`, `relied on api_start_ride.md (to recheck)` и `the answer lacks "8 ₽"`

### Requirement: Ошибка модели не останавливает прогон
Ошибка вызова модели на одном вопросе SHALL делать этот вопрос непройденным по всем проверкам с текстом ошибки в причине, не прерывая остальные вопросы.

#### Scenario: Лимит запросов
- GIVEN на первом вопросе модель ответила ошибкой `rate limited`, второй вопрос отвечен
- WHEN запускается прогон
- THEN первый вопрос не пройден с причиной `rate limited`, второй проверен как обычно

### Requirement: Вывод
Команда SHALL печатать в stdout `[OK] shadow: <id>: opened <документы>; all checks passed` или `[WARNING] shadow: <id>: <проблемы через "; ">` на каждый вопрос, а в stderr — сводку `okf shadow: <N> questions, <P> passed (documents <a>/<N>, trust <b>/<N>, facts <c>/<N>); answers by <актор>[; <K> worse than <REF>]`.

#### Scenario: Сводка
- GIVEN три вопроса, один пройден, два опирались на документ «перепроверить»
- WHEN прогон завершён
- THEN в stderr `3 questions, 1 passed (documents 3/3, trust 1/3, facts 3/3)`

### Requirement: Сравнение с базовой веткой
С `--base REF` команда SHALL прогонять те же вопросы на `REF` во временном `git worktree` с картой доверия той ветки, печатать `[WARNING] shadow: <id>: worse than <REF>: <проверки>` для вопросов, у которых проверка проходила на `REF` и не проходит сейчас, и удалять временный worktree после прогона.

#### Scenario: PR сделал знание ненадёжным
- GIVEN на ветке `pr/billing-tariff` документ `billing_service.md` стал «перепроверить», а на `main` был подтверждён
- WHEN запускается `okf shadow --replay <answers> --base main`
- THEN в stdout `[WARNING] shadow: minute-price: worse than main: trust`, в сводке `1 worse than main`
- AND после прогона в `git worktree list` только основная рабочая копия

#### Scenario: Вне git
- GIVEN каталог не является репозиторием git
- WHEN запускается `okf shadow --base main`
- THEN код выхода 2 и `okf: error: --base needs a git repository`

#### Scenario: Неизвестная ветка
- GIVEN `REF` не существует
- WHEN запускается `okf shadow --base no-such-ref`
- THEN код выхода 2 и сообщение `cannot check out no-such-ref: …`

### Requirement: Коды выхода
Команда `okf shadow` SHALL возвращать 0 после прогона, а с `--strict` — 1, если хотя бы один вопрос не прошёл или стал хуже, чем на `--base`.

#### Scenario: Strict с ухудшением
- GIVEN один вопрос стал хуже, чем на `main`
- WHEN запускается `okf shadow --replay <answers> --base main --strict`
- THEN код выхода 1

#### Scenario: Без strict
- GIVEN вопросы не прошли
- WHEN запускается `okf shadow --replay <answers>`
- THEN код выхода 0
