# Source Connectors Specification

## Purpose
Подключаемые источники правды для документов OKF: единый интерфейс и реестр коннекторов, где git — первый коннектор, а Confluence, Jira, Notion и закреплённые сообщения Slack — следующие. Коннектор по `sources[].resource` сообщает, когда источник менялся и что в нём поменялось, а `okf import confluence` и `okf import notion` заводят страницы в базу знаний OKF в git.

## Requirements

### Requirement: Реестр коннекторов
Система SHALL выбирать коннектор для каждого `sources[].resource` из единого реестра: ресурс получает первый коннектор, который его распознал (Confluence, Jira, Notion, Slack), затем git для путей и ссылок GitHub, так что новый коннектор подключается одним классом и одной строкой регистрации без изменений в командах `okf trust`, `okf stale` и `okf fix`.

#### Scenario: Ресурс распознан
- GIVEN в реестре зарегистрированы коннекторы
- WHEN документ ссылается на `confluence://131073`, `jira://WHL-1` и `../src/auth.py`
- THEN их обрабатывают коннекторы Confluence, Jira и git соответственно

#### Scenario: URL, который не распознал ни один коннектор
- GIVEN `resource: https://metabase.wheelo.example/dashboard/12`
- WHEN строится карта доверия
- THEN ресурс не считается источником, не влияет на уровень документа и не даёт заметки о причине

#### Scenario: Описание области
- GIVEN `resource: все сервисы биллинга`
- WHEN строится карта доверия
- THEN ресурс с пробелами пропускается и ни одному коннектору не передаётся

#### Scenario: Новый коннектор
- GIVEN разработчик добавил класс коннектора для `wiki://<id>` с настройкой `OKF_MYWIKI_URL` и зарегистрировал его
- WHEN документ, подтверждённый 2026-09-01 `human:a`, ссылается на `wiki://7`, изменённую 2026-10-10
- THEN `okf trust` выводит `wiki page 7 changed 2026-10-10, last verified 2026-09-01 by human:a`
- AND без `OKF_MYWIKI_URL` статус ресурса — `connector not configured: set OKF_MYWIKI_URL`

### Requirement: Git — первый коннектор
Коннектор git SHALL обрабатывать пути от файла и от корня бандла и ссылки `https://github.com/<owner>/<repo>/blob|tree/<ref>/<path>` на файлы этого репозитория, а датой и диффом источника считать историю git.

#### Scenario: Ссылка GitHub
- GIVEN `resource: https://github.com/acme/app/blob/main/src/auth.py`
- WHEN реестр выбирает коннектор
- THEN ресурс обрабатывает коннектор git как путь `src/auth.py`

#### Scenario: Демо без настроек коннекторов
- GIVEN демо-история `wheelo-demo` на `main` и ни одной переменной `OKF_*` коннекторов
- WHEN запускается `okf trust`
- THEN в stderr `okf trust: 16 units: 9 verified and current, 3 to recheck, 1 broken, 3 not verified`

### Requirement: Ресурсы Confluence
Коннектор Confluence SHALL распознавать страницы Cloud `https://<site>.atlassian.net/wiki/spaces/<KEY>/pages/<id>[/<title>]` (в том числе `pages/edit-v2/<id>`), Server/Data Center `<base>/pages/viewpage.action?pageId=<id>` с числовым `pageId` и короткие формы `confluence://<id>` и `confluence:<id>`, извлекая из них идентификатор страницы.

#### Scenario: Страница Cloud
- GIVEN `resource: https://wheelo.atlassian.net/wiki/spaces/WHL/pages/131073/Metriki+produkta`
- WHEN коннектор разбирает ресурс
- THEN это страница `131073` на `wheelo.atlassian.net`

#### Scenario: Страница Server/Data Center
- GIVEN `resource: https://wiki.corp/confluence/pages/viewpage.action?spaceKey=X&pageId=77`
- WHEN коннектор разбирает ресурс
- THEN это страница `77` на `wiki.corp`

#### Scenario: Короткая форма
- GIVEN `resource: confluence://131073`
- WHEN коннектор разбирает ресурс
- THEN это страница `131073` на сервере из `OKF_CONFLUENCE_URL`

#### Scenario: Ссылка на пространство, а не страницу
- GIVEN `resource: https://wheelo.atlassian.net/wiki/spaces/WHL/overview` или `viewpage.action?pageId=abc`
- WHEN реестр выбирает коннектор
- THEN коннектор Confluence ресурс не распознаёт, и ресурс не считается источником документа

### Requirement: Учётные данные только своему серверу
Коннекторы Confluence и Jira MUST NOT отправлять запрос по ссылке на хост, отличный от хоста из `OKF_CONFLUENCE_URL` или `OKF_JIRA_URL`; такой ресурс получает статус «неизвестно» с причиной `OKF_CONFLUENCE_URL is <настроенный хост>, not <хост ссылки>` (для Jira — `OKF_JIRA_URL is …`).

#### Scenario: Страница на другом сайте
- GIVEN `OKF_CONFLUENCE_URL=https://acme.atlassian.net/wiki`, `resource` — страница на `wheelo.atlassian.net`
- WHEN проверяется источник
- THEN статус `unknown` с причиной `OKF_CONFLUENCE_URL is acme.atlassian.net, not wheelo.atlassian.net`
- AND ни одного сетевого запроса не сделано

### Requirement: Дата и версия страницы Confluence
Коннектор Confluence SHALL сообщать для страницы дату-время последнего изменения (время текущей версии) и описывать её как `Confluence page "<title>" (v<N>)`, а изменение страницы после последнего подтверждения документа становится сигналом к перепроверке с глаголом `changed`.

#### Scenario: Страница прочитана
- GIVEN страница `131073` «Метрики продукта» в версии 7, созданной 2026-08-28T12:00:00Z
- WHEN коннектор проверяет ресурс
- THEN статус `ok`, сообщение `Confluence page "Метрики продукта" (v7)`, дата изменения 2026-08-28T12:00:00Z

### Requirement: Что поменялось на странице Confluence
Коннектор Confluence SHALL отдавать для `okf fix --draft` unified diff текста страницы (в Markdown) между версией, актуальной на заданный момент, и текущей версией, с заголовками `<title> v<N> (<дата>)`, а если страница не менялась после этого момента — ничего.

#### Scenario: Изменения с даты подтверждения
- GIVEN страница «Тарифы и биллинг» в версии 3 от 2026-10-03, на дату подтверждения была версия 2 от 2026-08-20
- WHEN запрашиваются изменения с даты подтверждения
- THEN дифф начинается со ссылки на страницу и содержит `--- Тарифы и биллинг v2 (2026-08-20)` и `+++ Тарифы и биллинг v3 (2026-10-03)` с изменёнными строками текста

#### Scenario: Страница не менялась
- GIVEN последняя версия страницы старше заданного момента
- WHEN запрашиваются изменения
- THEN изменений нет

#### Scenario: Страницы на ту дату не было
- GIVEN страница создана после заданного момента
- WHEN запрашиваются изменения
- THEN дифф сравнивает текущий текст с пустым, слева `nothing (created later)`

### Requirement: Текст страницы Confluence в Markdown
Коннектор Confluence SHALL переводить storage-формат страницы в Markdown: заголовки, абзацы, вложенные списки и чек-листы, жирный и курсив, код (`<pre>` и макросы `code` и `noformat` с языком), ссылки, таблицы и ключ задачи из макроса `jira`, а остальное — простым текстом.

#### Scenario: Макрос кода и таблица
- GIVEN страница с макросом `code` с `language=sql` и таблицей из двух столбцов
- WHEN текст переводится в Markdown
- THEN в тексте блок ```` ```sql ```` и таблица `| … | … |` со строкой-разделителем `|---|---|`

### Requirement: Импорт из Confluence
Команда `okf import confluence --space KEY [--page ID]... --out <bundle>` SHALL записывать в `<bundle>` по файлу OKF на каждую страницу пространства `KEY` (не больше `--limit`, по умолчанию 200), а с `--page` (id или ссылка, можно повторять) — только на указанные страницы, и печатать в stderr строку на страницу и сводку `okf import: <N> pages from <where>, <W> written to <bundle>[; they stay not verified until okf verify]`.

#### Scenario: Всё пространство
- GIVEN пространство `WHL` с двумя страницами «Метрики продукта» и «Тарифы и биллинг», коннектор настроен
- WHEN запускается `okf import confluence --space WHL --out kb`
- THEN в `kb` записаны `metriki_produkta.md` и `tarify_i_billing.md`
- AND в stderr `2 pages from space WHL, 2 written`, код выхода 0

#### Scenario: Одна страница
- GIVEN пространство `WHL` и страница `131073`
- WHEN запускается `okf import confluence --page 131073 --out kb`
- THEN записан только файл страницы `131073`

#### Scenario: Не названо, что импортировать
- GIVEN не указаны ни `--space`, ни `--page`
- WHEN запускается `okf import confluence --out kb`
- THEN код выхода 2 и в stderr `okf: error: name a space (--space KEY) or pages (--page ID)`

#### Scenario: Коннектор не настроен
- GIVEN не задан `OKF_CONFLUENCE_URL`
- WHEN запускается `okf import confluence --space WHL --out kb`
- THEN код выхода 2, в stderr `okf import: connector not configured: set OKF_CONFLUENCE_URL`, файлы не записаны и сетевых запросов нет

#### Scenario: Сервер ответил ошибкой
- GIVEN Confluence отвечает, что пространства нет, или запрос не удался
- WHEN запускается импорт
- THEN код выхода 1 и в stderr `okf import: confluence: <причина>`

### Requirement: Импортированные файлы — валидный OKF
Каждый файл, записанный `okf import`, MUST проходить `okf validate` в профиле `okf` без ошибок и содержать `type` (из `--type`, иначе уже записанный в файле, иначе `Guide`), `title` страницы, `description` (если его не было — `Imported from <система> (<страница>).`), `status` (если его не было — `draft`), `generated: {by: process:okf-import, at: <время импорта>}`, первую запись `sources` с `id`, `resource` — ссылкой на страницу, `title` и `last_modified` — временем её версии, тело `# <title>` и текст страницы в Markdown, и ни одной новой записи `verified`.

#### Scenario: Проверка импорта
- GIVEN импорт пространства завершён
- WHEN запускается `okf validate <bundle>`
- THEN ошибок нет
- AND в шапке `generated: { by: process:okf-import, at: 2026-10-22T12:00:00Z }` и `last_modified: 2026-08-28T12:00:00Z`, а слова `verified` нет

#### Scenario: Импорт не подтверждён
- GIVEN импортированный документ
- WHEN запускается `okf trust`
- THEN документ «не подтверждено» с сообщением `edited by process:okf-import on 2026-10-22; not verified`, пока человек не выполнит `okf verify`

### Requirement: Имена файлов импорта
Импорт SHALL называть новый файл по названию страницы в ASCII (кириллица транслитерируется, прочие символы — `_`, не длиннее 60 символов), а если имя занято, совпадает с `index.md`, `log.md` или `agents.md` или название пустое, — добавлять первые восемь символов id страницы.

#### Scenario: Русское название
- GIVEN страница «Тарифы и биллинг»
- WHEN она импортируется впервые
- THEN файл называется `tarify_i_billing.md`

#### Scenario: Имя занято документом человека
- GIVEN в бандле уже есть `metriki_produkta.md`, написанный человеком
- WHEN импортируется страница `131073` «Метрики продукта»
- THEN новый файл — `metriki_produkta_131073.md`

### Requirement: Повторный импорт
Повторный импорт SHALL обновлять только файлы, которые написал `okf import` (их находит id страницы в `sources`), сохраняя их `type` и прочие поля шапки, не трогать страницы, чья версия и текст не изменились (действие `unchanged`), никогда не перезаписывать документ, написанный человеком, и дописывать ссылки на новые файлы в `index.md` бандла (создавая корневой `index.md` с `okf_version: "0.2"`, если его нет).

#### Scenario: Страница не менялась
- GIVEN страница уже импортирована и с тех пор не менялась
- WHEN импорт запускается снова
- THEN файл тот же, действие `unchanged`, файл не переписан

#### Scenario: Документ человека
- GIVEN `metriki_produkta.md` с `type: Metric` написан человеком
- WHEN импортируется одноимённая страница
- THEN файл человека не изменился, а страница записана в отдельный файл

#### Scenario: Ссылки в index.md
- GIVEN в `--out` нет `index.md`
- WHEN импорт записал два новых файла
- THEN создан `index.md` с `okf_version: "0.2"` и ссылками на оба файла

### Requirement: Ресурсы Jira
Коннектор Jira SHALL распознавать задачи `<base>/browse/<KEY-123>` и короткие формы `jira://<KEY-123>` и `jira:<KEY-123>`, где ключ — заглавные буквы, цифры и `_`, дефис и номер.

#### Scenario: Ссылка на задачу
- GIVEN `resource: https://jira.wheelo.ru/browse/PAY_2-7/`
- WHEN коннектор разбирает ресурс
- THEN это задача `PAY_2-7` на `jira.wheelo.ru`

#### Scenario: Короткая форма
- GIVEN `resource: jira://WHL-42`
- WHEN коннектор разбирает ресурс
- THEN это задача `WHL-42` на сервере из `OKF_JIRA_URL`

#### Scenario: Не задача
- GIVEN `resource: https://wheelo.atlassian.net/browse/whl-42` или ссылка на доску `/jira/software/projects/WHL/boards/1`
- WHEN реестр выбирает коннектор
- THEN коннектор Jira ресурс не распознаёт

### Requirement: Закрытая задача Jira — сигнал к перепроверке
Коннектор Jira SHALL описывать задачу как `Jira <тип> <KEY> "<summary>" (<статус>)` и давать сигнал к перепроверке только для задачи в категории статуса Done — с моментом последнего перехода статуса из changelog и глаголом `closed`, а для открытой задачи — никакого сигнала, сколько бы её ни обновляли.

#### Scenario: Эпик закрыт
- GIVEN эпик `WHL-42` перешёл в Done 2026-10-14
- WHEN коннектор проверяет задачу
- THEN сообщение `Jira epic WHL-42 "Определение сессии для метрики конверсии" (Done)`, сигнал `epic WHL-42 closed` с датой 2026-10-14

#### Scenario: Задача в работе
- GIVEN задача в статусе In Progress, недавно прокомментированная
- WHEN коннектор проверяет задачу
- THEN статус `ok`, сигнала нет

### Requirement: Что поменялось в задаче Jira
Коннектор Jira SHALL отдавать для `okf fix --draft` записи changelog после заданного момента строками `- <дата> <автор>: <поле>: <было> -> <стало>` под заголовком `Jira <тип> <KEY> "<summary>", now <статус>; changes since <дата>:`, а без записей после момента — ничего.

#### Scenario: Переход в Done
- GIVEN документ подтверждён до того, как Анна (PM) перевела эпик из In Progress в Done 2026-10-14
- WHEN запрашиваются изменения с даты подтверждения
- THEN в тексте строка `- 2026-10-14 Анна (PM): status: In Progress -> Done`, а более ранние переходы не показаны

### Requirement: Ресурсы Notion
Коннектор Notion SHALL распознавать страницы `https://www.notion.so/<slug>-<id>`, `https://notion.so/<workspace>/<slug>-<id>`, `https://<workspace>.notion.site/<slug>-<id>` и `notion://<id>`, где `<id>` — 32 шестнадцатеричные цифры с дефисами или без, приводя id к виду UUID с дефисами.

#### Scenario: Ссылка на страницу
- GIVEN `resource: https://www.notion.so/Onboarding-<32 hex>`
- WHEN коннектор разбирает ресурс
- THEN это страница с этим id в виде UUID с дефисами

#### Scenario: Чужой сайт
- GIVEN ссылка на другой домен с тем же хвостом из 32 цифр
- WHEN реестр выбирает коннектор
- THEN коннектор Notion ресурс не распознаёт

### Requirement: Дата правки страницы Notion
Коннектор Notion SHALL считать датой изменения страницы её `last_edited_time`, описывать её как `Notion page "<title>"`, давать сигнал `changed` и считать страницу в корзине источником со статусом «неизвестно» с причиной `Notion page <id> is in the trash`.

#### Scenario: Страница правилась после подтверждения
- GIVEN документ подтверждён `human:anna` 2026-09-05, страница «Онбординг» правилась 2026-10-10
- WHEN запускается `okf trust`
- THEN документ «перепроверить» с сообщением `Notion page "Онбординг" changed 2026-10-10, last verified 2026-09-05 by human:anna`

#### Scenario: Страница в корзине
- GIVEN Notion отвечает, что страница в корзине
- WHEN проверяется источник
- THEN статус `unknown`, документ не «сломано»

### Requirement: Что поменялось на странице Notion
Коннектор Notion SHALL отдавать для `okf fix --draft` unified diff между снимком `.okf/snapshots/notion/<id>.md`, сохранённым `okf import notion`, и текущим текстом страницы с её дочерними блоками (все страницы пагинации), а без снимка — строку, что страница правилась `<дата>` после `<даты>` и снимка для сравнения нет.

#### Scenario: Снимка нет
- GIVEN страница правилась после подтверждения, снимка нет
- WHEN запрашиваются изменения
- THEN текст содержит `there is no saved snapshot to compare with (okf import notion saves one)`

#### Scenario: Снимок есть
- GIVEN в снимке строка `Ставим окружение вручную.`, на странице теперь `Ставим окружение по гайду.`
- WHEN запрашиваются изменения
- THEN в диффе `-Ставим окружение вручную.` и `+Ставим окружение по гайду.`

#### Scenario: Страница не правилась
- GIVEN `last_edited_time` раньше заданного момента
- WHEN запрашиваются изменения
- THEN изменений нет

### Requirement: Темп запросов к Notion
Коннектор Notion SHALL разносить свои запросы не меньше чем на 0,34 секунды (около трёх в секунду), а на ответ 429 ждать `Retry-After` перед повтором.

#### Scenario: Несколько запросов подряд
- GIVEN страница с блоками на нескольких страницах пагинации
- WHEN коннектор читает её текст
- THEN перед запросом, ушедшим раньше чем через 0,34 секунды после предыдущего, коннектор ждёт остаток интервала, и запросы идут не чаще примерно трёх в секунду

#### Scenario: Лимит запросов
- GIVEN Notion отвечает 429 с `Retry-After: 1`, затем 200
- WHEN коннектор читает страницу
- THEN он ждёт 1 секунду и получает страницу

### Requirement: Импорт из Notion
Команда `okf import notion --page ID [--page ID]... [--recursive] --out <bundle>` SHALL записывать указанные страницы (id или ссылка), а с `--recursive` — и их дочерние страницы, файлами OKF по тем же правилам, что импорт Confluence, и сохранять текст каждой страницы снимком `.okf/snapshots/notion/<id>.md` в корне репозитория.

#### Scenario: Страница с дочерней
- GIVEN страница «Онбординг» с дочерней страницей «Доступы», `OKF_NOTION_TOKEN` задан
- WHEN запускается `okf import notion --page <id> --recursive --out kb`
- THEN записаны `onbording.md` и `dostupy.md`, оба проходят `okf validate` без ошибок
- AND в шапке `resource: https://www.notion.so/…` и `last_modified: 2026-10-10T09:30:00Z`, а снимок начинается с текста страницы

#### Scenario: Без страниц
- GIVEN указан только `--space X`
- WHEN запускается `okf import notion --space X --out kb`
- THEN код выхода 2 и в stderr `okf: error: name pages (--page ID)`

#### Scenario: Нет токена
- GIVEN не задан `OKF_NOTION_TOKEN`
- WHEN запускается `okf import notion --page <id> --out kb`
- THEN код выхода 2 и в stderr `okf import: connector not configured: set OKF_NOTION_TOKEN`

### Requirement: Ресурсы Slack
Коннектор Slack SHALL распознавать сообщения `slack://<channel>/<ts>` (например `slack://C0123ABCD/1729500000.123456`) и permalink `https://<workspace>.slack.com/archives/<channel>/p<ts без точки>`, извлекая канал и `ts` сообщения.

#### Scenario: Permalink
- GIVEN `resource: https://acme.slack.com/archives/C0WHL01/p1729500000123456`
- WHEN коннектор разбирает ресурс
- THEN это сообщение `1729500000.123456` в канале `C0WHL01`

### Requirement: Закреплённое сообщение Slack — сигнал к перепроверке
Коннектор Slack SHALL описывать сообщение как `Slack message <ts> in <channel>` и давать сигнал к перепроверке, если сообщение отредактировано (`was edited <дата правки>`), больше не закреплено (`is no longer pinned, seen <сегодня>`) или удалено (`is gone, seen <сегодня>`), а закреплённое и неизменённое сообщение сигнала не даёт.

#### Scenario: Отредактировано после подтверждения
- GIVEN документ подтверждён 2024-10-01 `human:anna`, сообщение отредактировано 2024-10-15
- WHEN запускается `okf trust`
- THEN документ «перепроверить»: `Slack message <ts> in C0WHL01 was edited 2024-10-15, last verified 2024-10-01 by human:anna`

#### Scenario: Подтверждено после правки
- GIVEN сообщение отредактировано 2024-10-15, документ подтверждён 2024-10-20
- WHEN запускается `okf trust`
- THEN документ «подтверждено»

#### Scenario: Откреплено
- GIVEN сообщение больше не в списке закреплённых канала
- WHEN запускается `okf trust` 2026-10-22
- THEN документ «перепроверить» с сообщением, начинающимся с `Slack message <ts> in C0WHL01 is no longer pinned, seen 2026-10-22`, и так при каждом запуске, пока документ ссылается на это сообщение

#### Scenario: Удалено
- GIVEN сообщения в канале больше нет
- WHEN запускается `okf trust`
- THEN документ «перепроверить» с причиной `recheck:source-gone`

### Requirement: Что поменялось в сообщении Slack
Коннектор Slack SHALL отдавать для `okf fix --draft` текущий текст сообщения с пометками, что оно откреплено и/или отредактировано `<дата>` (`Slack keeps no earlier text`), для удалённого — что сравнивать не с чем, а для закреплённого и не правленного после момента — ничего.

#### Scenario: Отредактировано
- GIVEN сообщение отредактировано 2024-10-15 после подтверждения
- WHEN запрашиваются изменения
- THEN текст содержит `was edited 2024-10-15 (Slack keeps no earlier text)` и текущий текст сообщения

### Requirement: Ошибки Slack API
Ответ Slack с `ok: false` SHALL давать источнику статус «неизвестно» с причиной `Slack: <error>` и подсказкой: `invite the bot to the channel` для `not_in_channel`, `check OKF_SLACK_TOKEN` для `invalid_auth` и `not_authed`, нужные права для `missing_scope`.

#### Scenario: Бот не в канале
- GIVEN Slack отвечает `{"ok": false, "error": "not_in_channel"}`
- WHEN проверяется источник
- THEN статус `unknown`, сообщение `Slack message <ts> in C0WHL01: Slack: not_in_channel: invite the bot to the channel`, значения токена в нём нет

### Requirement: Настройка только через окружение
Коннекторы SHALL настраиваться только переменными окружения: `OKF_CONFLUENCE_URL` и `OKF_JIRA_URL` — адреса серверов, `OKF_ATLASSIAN_EMAIL` + `OKF_ATLASSIAN_TOKEN` — учётные данные Cloud (Basic), `OKF_ATLASSIAN_PAT` — персональный токен Server/Data Center (Bearer, приоритет), `OKF_NOTION_TOKEN` — секрет интеграции Notion, `OKF_SLACK_TOKEN` — бот-токен Slack, `OKF_SOURCES_TIMEOUT` — таймаут запроса в секундах (по умолчанию 10).

#### Scenario: Server/Data Center с персональным токеном
- GIVEN `OKF_CONFLUENCE_URL` — адрес Server/DC и `OKF_ATLASSIAN_PAT=pat-123`
- WHEN проверяется `confluence://4456`
- THEN запрос `/rest/api/content/4456?expand=version,body.storage` уходит с заголовком `Authorization: Bearer pat-123`

#### Scenario: Cloud
- GIVEN `OKF_JIRA_URL=https://wheelo.atlassian.net`, `OKF_ATLASSIAN_EMAIL` и `OKF_ATLASSIAN_TOKEN`
- WHEN проверяется задача Jira
- THEN коннектор читает её через REST API v3 с заголовком `Authorization: Basic …`

#### Scenario: Адрес без учётных данных
- GIVEN задан `OKF_CONFLUENCE_URL`, но нет ни пары email + token, ни PAT, а сервер требует вход
- WHEN проверяется страница
- THEN запрос уходит без учётных данных, и источник получает статус «неизвестно» с причиной `authentication failed (HTTP 401): check OKF_ATLASSIAN_EMAIL and OKF_ATLASSIAN_TOKEN (Cloud) or OKF_ATLASSIAN_PAT (Server/DC)`

### Requirement: Без настройки нет сети
Без настроенного коннектора команды okf MUST NOT выполнять ни одного сетевого запроса к Confluence, Jira, Notion или Slack.

#### Scenario: Переменные не заданы
- GIVEN ни одна переменная коннекторов не задана, документы ссылаются на Confluence, Jira, Notion и Slack
- WHEN запускаются `okf trust`, `okf stale`, `okf fix` и `okf sources`
- THEN ни одного запроса к этим системам не сделано

### Requirement: Ресурс без настроенного коннектора
Ресурс, который распознаёт коннектор, но настройка этого коннектора не задана, SHALL получать статус «неизвестно» с причиной `connector not configured: set <переменная>` (`OKF_CONFLUENCE_URL`, `OKF_JIRA_URL`, `OKF_NOTION_TOKEN` или `OKF_SLACK_TOKEN`) и не делать документ «сломано».

#### Scenario: Jira не настроена
- GIVEN `resource: jira://WHL-42`, `OKF_JIRA_URL` не задан
- WHEN проверяется источник
- THEN статус `unknown`, причина `connector not configured: set OKF_JIRA_URL`, документ не «сломано»

### Requirement: Токены не печатаются
Значения `OKF_ATLASSIAN_TOKEN`, `OKF_ATLASSIAN_PAT`, `OKF_NOTION_TOKEN` и `OKF_SLACK_TOKEN` MUST NOT появляться в stdout, stderr, выводе `--json` и сообщениях об ошибках: токены передаются только в заголовках запросов, а ошибки называют HTTP-статус и путь.

#### Scenario: Ошибка авторизации
- GIVEN `OKF_ATLASSIAN_PAT=very-secret-token`, сервер отвечает 401
- WHEN проверяется страница
- THEN сообщение об ошибке не содержит `very-secret-token`

### Requirement: Ошибки API не роняют команду
Ответы 401, 403, 404, 429 после исчерпанных повторов и другие ошибки HTTP, ответ не в JSON и недоступность сервера SHALL давать источнику статус «неизвестно» с причиной после описания ресурса (`authentication failed (HTTP 401): check …`, `no access (HTTP 403)`, `not found or no access (HTTP 404)`, `rate limited (HTTP 429), gave up after <N> tries`, `GET <path>: HTTP <код>`, `GET <path>: the answer is not JSON`, `<host> cannot connect` или `<host> timed out`), не прерывая команду, без трассировки стека и не меняя её код выхода.

#### Scenario: Нет доступа
- GIVEN Confluence отвечает 403 на страницу `4456`
- WHEN проверяется источник
- THEN статус `unknown`, сообщение `Confluence page 4456: no access (HTTP 403)`

#### Scenario: Страница удалена
- GIVEN Confluence отвечает 404
- WHEN запускается `okf trust`
- THEN источник `Confluence page 4456: not found or no access (HTTP 404)`, остальные единицы карты посчитаны, код выхода как без этого источника

#### Scenario: Сервер недоступен
- GIVEN сервер из `OKF_CONFLUENCE_URL` не отвечает
- WHEN проверяются две страницы этого сервера
- THEN обе `unknown` с причиной `<host> cannot connect` или `<host> timed out`, без трассировки стека

### Requirement: Повторы запросов
Коннекторы SHALL повторять запрос, получивший 429, 502, 503 или 504, до трёх раз с паузой `Retry-After` (не больше 30 секунд) или 1, 2 и 4 секунды, а хост, который не ответил, в том же запуске больше не спрашивать.

#### Scenario: Лимит снят после повтора
- GIVEN сервер отвечает 429 с `Retry-After: 2`, затем 429 без заголовка, затем 200
- WHEN проверяется страница
- THEN паузы 2 и 2 секунды, статус `ok`

#### Scenario: Лимит не снят
- GIVEN сервер всё время отвечает 429 без `Retry-After`
- WHEN проверяется страница
- THEN паузы 1, 2 и 4 секунды и причина `rate limited (HTTP 429), gave up after 4 tries`

#### Scenario: Недоступный хост спрашивается один раз
- GIVEN хост из `OKF_CONFLUENCE_URL` не отвечает
- WHEN в одном запуске проверяются `confluence://1` и `confluence://2`
- THEN к хосту ушла одна попытка соединения, вторая страница получает ту же причину без нового соединения

### Requirement: Ответы из фикстур
С `OKF_SOURCES_FIXTURES=<dir>` коннекторы SHALL брать ответы из файлов `<dir>/<путь запроса>.json` (файл с совпадающими параметрами запроса в имени после `@` предпочитается), а фикстура `{"_status": <код>}` отвечает этим HTTP-статусом, без обращения к сети.

#### Scenario: Статус из фикстуры
- GIVEN фикстура страницы `1` — `{"_status": 403}`
- WHEN проверяется `confluence://1`
- THEN сообщение `Confluence page 1: no access (HTTP 403)`

#### Scenario: Фикстуры нет
- GIVEN для страницы `2` файла нет
- WHEN проверяется `confluence://2`
- THEN статус `unknown`, причина содержит `no fixture for GET /wiki/api/v2/pages/2`

### Requirement: Удалённые источники в okf stale
Команда `okf stale` SHALL выводить `[WARNING] <file>: sources: Source <resource>: <что> <глагол> <дата>, after it was last verified|after its recorded last_modified; document may be outdated[, ask <reviewer> to review it]`, если сигнал удалённого источника новее последнего `verified` или записанного `sources[].last_modified`, и `[INFO] … Source <resource>: unknown, <причина>` для источника, который нельзя прочитать.

#### Scenario: Эпик закрыт после подтверждения
- GIVEN документ подтверждён `human:pm_anna`, эпик `WHL-42` закрыт 2026-10-14 после этого
- WHEN запускается `okf stale`
- THEN выводится `Source <ссылка>: epic WHL-42 closed 2026-10-14, after it was last verified; document may be outdated, ask human:pm_anna to review it`

#### Scenario: Без настроек
- GIVEN коннекторы не настроены
- WHEN запускается `okf stale`
- THEN по удалённым источникам только строки `[INFO]`, код выхода не меняется

### Requirement: Команда okf sources
Команда `okf sources [repo] [--bundle DIR]` SHALL печатать в stderr состояние каждого коннектора (`okf sources: <name>: configured (<адрес>)` или `connector not configured: set …`), в stdout — строку `[OK|INFO] <file>: <connector>: <resource>: <status>, <message>[; <сигнал> <дата>]` на каждый удалённый источник документов OKF, у которого есть коннектор, и сводку `okf sources: <N> remote sources with a connector`.

#### Scenario: Настроенная Jira
- GIVEN `OKF_JIRA_URL=https://wheelo.atlassian.net` и ответы из фикстур, документ демо ссылается на закрытый эпик
- WHEN запускается `okf sources examples/demo`
- THEN в stderr `okf sources: jira: configured (https://wheelo.atlassian.net)`
- AND в stdout `[OK] examples/demo/knowledge/ride_conversion_metric.md: jira: <ссылка>: ok, Jira epic WHL-42 …; epic WHL-42 closed 2026-10-14`, код выхода 0
