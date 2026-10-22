## Purpose
Подключаемые источники правды для документов OKF: единый интерфейс и реестр коннекторов, где git — первый коннектор, а Confluence и Jira — следующие. Коннектор по `sources[].resource` сообщает, когда источник менялся и что в нём поменялось, а `okf import confluence` заводит страницы Confluence в базу знаний OKF.

## ADDED Requirements

### Requirement: Реестр коннекторов
Система SHALL выбирать коннектор для каждого `sources[].resource` из единого реестра по виду ресурса, так что новый коннектор подключается одним файлом и регистрацией без изменений в командах `okf trust` и `okf stale`.

#### Scenario: Ресурс распознан
- GIVEN в реестре зарегистрированы коннекторы git, Confluence и Jira
- WHEN документ ссылается на `confluence://123456`
- THEN ресурс обрабатывает коннектор Confluence

#### Scenario: Ресурс не распознан ни одним коннектором
- GIVEN `resource: https://wiki.example.com/page` или описание области `все сервисы биллинга`
- WHEN строится карта доверия
- THEN ресурс не считается источником и не влияет на уровень документа, как сейчас

#### Scenario: Новый коннектор
- GIVEN разработчик добавил файл коннектора и зарегистрировал его в реестре
- WHEN документ ссылается на ресурс этого вида
- THEN `okf trust` учитывает его без правок в коде команд

### Requirement: Git — первый коннектор
Коннектор git SHALL обрабатывать пути от файла и от корня бандла и ссылки `https://github.com/<owner>/<repo>/blob|tree/<ref>/<path>` на файлы этого репозитория с тем же результатом, что до появления реестра.

#### Scenario: Поведение не изменилось
- GIVEN демо-история `wheelo-demo` и ни одной переменной `OKF_*` коннекторов
- WHEN запускается `okf trust`
- THEN сводка и строки вывода совпадают с выводом до этого изменения

### Requirement: Ресурсы Confluence
Коннектор Confluence SHALL распознавать страницы Cloud `https://<site>.atlassian.net/wiki/spaces/<KEY>/pages/<id>/<title>`, Server/Data Center `<base>/pages/viewpage.action?pageId=<id>` и короткую форму `confluence://<id>`, извлекая из них идентификатор страницы.

#### Scenario: Страница Cloud
- GIVEN `resource: https://acme.atlassian.net/wiki/spaces/BILL/pages/123456/Tariffs`
- WHEN коннектор разбирает ресурс
- THEN это страница `123456`

#### Scenario: Страница Server/Data Center
- GIVEN `resource: https://wiki.acme.local/pages/viewpage.action?pageId=987`
- WHEN коннектор разбирает ресурс
- THEN это страница `987`

#### Scenario: Короткая форма
- GIVEN `resource: confluence://123456`
- WHEN коннектор разбирает ресурс
- THEN это страница `123456` на сервере из `OKF_CONFLUENCE_URL`

#### Scenario: Ссылка на пространство, а не страницу
- GIVEN `resource: https://acme.atlassian.net/wiki/spaces/BILL/overview`
- WHEN коннектор разбирает ресурс
- THEN это не страница, и источник получает статус «неизвестно» с причиной

### Requirement: Дата изменения страницы
Коннектор Confluence SHALL сообщать для страницы дату-время последнего изменения с явным смещением UTC и номер текущей версии.

#### Scenario: Страница изменена
- GIVEN страница `123456` в версии 14, изменённой 2026-10-20T09:15:00Z
- WHEN коннектор запрашивает страницу
- THEN источник датирован 2026-10-20T09:15:00Z, версия 14

### Requirement: Что поменялось на странице
Коннектор Confluence SHALL отдавать текстовый дифф страницы между версией, актуальной на заданную дату, и текущей версией, чтобы `okf fix --draft` мог передать его модели так же, как `git diff` кода.

#### Scenario: Изменения с даты подтверждения
- GIVEN документ подтверждён 2026-09-05, с тех пор у страницы версии 12 → 14
- WHEN запрашивается дифф с 2026-09-05
- THEN дифф показывает текстовые изменения между версией 12 и версией 14

#### Scenario: Страница не менялась
- GIVEN последняя версия страницы старше заданной даты
- WHEN запрашивается дифф
- THEN дифф пустой

### Requirement: Импорт пространства Confluence
Команда `okf import confluence --space KEY [--page ID] --out <bundle>` SHALL записывать в `<bundle>` по файлу OKF на каждую страницу пространства `KEY`, а с `--page ID` — только на указанную страницу.

#### Scenario: Всё пространство
- GIVEN пространство `BILL` с тремя страницами и настроенный коннектор
- WHEN запускается `okf import confluence --space BILL --out knowledge/billing`
- THEN в `knowledge/billing` три файла `.md`, по одному на страницу

#### Scenario: Одна страница
- GIVEN пространство `BILL` и страница `123456`
- WHEN запускается `okf import confluence --space BILL --page 123456 --out knowledge/billing`
- THEN записан только файл страницы `123456`

#### Scenario: Коннектор не настроен
- GIVEN не задан `OKF_CONFLUENCE_URL`
- WHEN запускается `okf import confluence --space BILL --out kb`
- THEN код выхода 2, сообщение называет переменные, которые нужно задать, файлы не записаны и сетевых запросов нет

### Requirement: Импортированные файлы — валидный OKF
Каждый файл, записанный `okf import confluence`, MUST проходить `okf validate` в профиле `okf` без ошибок и содержать непустой `type`, `title` страницы, `sources` с записью, чей `resource` — ссылка на страницу, и `generated: {by: process:okf-import, at: <время импорта>}` без записей `verified`.

#### Scenario: Проверка импорта
- GIVEN импорт пространства завершён
- WHEN запускается `okf validate <bundle>`
- THEN ошибок нет и код выхода 0

#### Scenario: Импорт не подтверждён
- GIVEN импортированный документ
- WHEN запускается `okf trust`
- THEN документ не «подтверждено», пока человек не выполнит `okf verify`

### Requirement: Ресурсы Jira
Коннектор Jira SHALL распознавать задачи `<base>/browse/KEY-123` и короткую форму `jira://KEY-123`, извлекая ключ задачи.

#### Scenario: Ссылка на задачу
- GIVEN `resource: https://acme.atlassian.net/browse/BILL-42`
- WHEN коннектор разбирает ресурс
- THEN это задача `BILL-42`

#### Scenario: Короткая форма
- GIVEN `resource: jira://BILL-42`
- WHEN коннектор разбирает ресурс
- THEN это задача `BILL-42` на сервере из `OKF_JIRA_URL`

### Requirement: Статус задачи Jira
Коннектор Jira SHALL сообщать для задачи или эпика текущую категорию статуса и дату-время перехода в категорию Done, если задача в ней.

#### Scenario: Эпик закрыт
- GIVEN эпик `BILL-42` перешёл в Done 2026-10-18T12:00:00Z
- WHEN коннектор запрашивает задачу
- THEN источник сообщает статус Done и дату 2026-10-18T12:00:00Z

#### Scenario: Задача в работе
- GIVEN задача `BILL-43` в статусе In Progress
- WHEN коннектор запрашивает задачу
- THEN дата перехода в Done отсутствует

### Requirement: Настройка только через окружение
Коннекторы Confluence и Jira SHALL настраиваться только переменными окружения: `OKF_CONFLUENCE_URL` и `OKF_JIRA_URL` — адреса серверов, `OKF_ATLASSIAN_EMAIL` + `OKF_ATLASSIAN_TOKEN` — учётные данные Cloud, `OKF_ATLASSIAN_PAT` — персональный токен Server/Data Center.

#### Scenario: Cloud
- GIVEN заданы `OKF_CONFLUENCE_URL=https://acme.atlassian.net/wiki`, `OKF_ATLASSIAN_EMAIL` и `OKF_ATLASSIAN_TOKEN`
- WHEN `okf trust` встречает страницу Confluence
- THEN коннектор обращается к `acme.atlassian.net` с этими учётными данными

#### Scenario: Server/Data Center
- GIVEN заданы `OKF_JIRA_URL=https://jira.acme.local` и `OKF_ATLASSIAN_PAT`
- WHEN `okf trust` встречает задачу Jira
- THEN коннектор обращается к `jira.acme.local` с персональным токеном

#### Scenario: Адрес без учётных данных
- GIVEN задан `OKF_CONFLUENCE_URL`, но нет ни пары email + token, ни PAT
- WHEN `okf trust` встречает страницу Confluence
- THEN источник получает статус «неизвестно» с причиной о недостающих учётных данных, сетевых запросов нет

### Requirement: Без настройки нет сети
Без настроенного коннектора команды okf MUST NOT выполнять ни одного сетевого запроса к Confluence, Jira или другим внешним системам.

#### Scenario: Переменные не заданы
- GIVEN ни одна переменная `OKF_CONFLUENCE_URL`, `OKF_JIRA_URL` не задана, документы ссылаются на Confluence и Jira
- WHEN запускаются `okf trust`, `okf stale` и `okf validate`
- THEN ни одного сетевого соединения не открывается

### Requirement: Токены не печатаются
Значения `OKF_ATLASSIAN_TOKEN` и `OKF_ATLASSIAN_PAT` MUST NOT появляться в stdout, stderr, выводе `--json`, отчётах `okf scan` и сообщениях об ошибках.

#### Scenario: Ошибка авторизации
- GIVEN неверный `OKF_ATLASSIAN_TOKEN`
- WHEN коннектор получает ответ 401
- THEN сообщение об ошибке не содержит значения токена

#### Scenario: Отладочный вывод
- GIVEN `okf trust --json` с настроенными коннекторами
- WHEN JSON печатается
- THEN в нём нет значений токенов

### Requirement: Ошибки API не роняют команду
Ответы 401, 403, 404 и 429 и недоступность сервера SHALL давать источнику статус «неизвестно» с причиной (`unauthorized`, `forbidden`, `not found`, `rate limited`, `unreachable`), не прерывая команду и не меняя её код выхода.

#### Scenario: Страница удалена
- GIVEN Confluence отвечает 404 на страницу `123456`
- WHEN запускается `okf trust`
- THEN источник `unknown: not found`, остальные единицы карты посчитаны, код выхода как без этого источника

#### Scenario: Лимит запросов
- GIVEN Jira отвечает 429
- WHEN запускается `okf trust`
- THEN источник `unknown: rate limited`, команда завершается штатно

#### Scenario: Нет доступа
- GIVEN Confluence отвечает 403
- WHEN запускается `okf trust`
- THEN источник `unknown: forbidden`

#### Scenario: Сервер недоступен
- GIVEN сервер из `OKF_JIRA_URL` не отвечает
- WHEN запускается `okf trust`
- THEN источник `unknown: unreachable`, без трассировки стека в выводе

### Requirement: Ресурс без настроенного коннектора
Ресурс, который распознаёт коннектор Confluence или Jira, но адрес этого коннектора не задан, SHALL получать статус `unknown: connector not configured`.

#### Scenario: Jira не настроена
- GIVEN `resource: jira://BILL-42`, `OKF_JIRA_URL` не задан
- WHEN запускается `okf trust`
- THEN источник `unknown: connector not configured`, документ не «сломано»
