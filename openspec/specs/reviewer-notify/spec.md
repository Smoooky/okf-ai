# Reviewer Notify Specification

## Purpose
`okf notify [repo]` напоминает тем, кто подтверждал разделы инструкций и документы знаний, что их пора перепроверить: одно сообщение на человека в Slack или Microsoft Teams со списком, причинами, ссылками на строки и одной командой `okf verify`, которая подтверждает всё после прочтения. `--dry-run` показывает сообщения, ничего не отправляя.

## Requirements

### Requirement: Что попадает в напоминание
Команда `okf notify` SHALL строить карту доверия репозитория так же, как `okf trust`, и включать в напоминания только единицы уровня «перепроверить».

#### Scenario: Сломанное и неподтверждённое не напоминаются
- GIVEN в карте есть единицы «сломано», «перепроверить», «подтверждено» и «не подтверждено»
- WHEN запускается `okf notify --dry-run`
- THEN в сообщениях только единицы «перепроверить»

#### Scenario: Нечего перепроверять
- GIVEN в карте нет единиц «перепроверить»
- WHEN запускается `okf notify --dry-run`
- THEN в stderr `okf notify: nothing to recheck, no messages`, код выхода 0

### Requirement: Группировка по последнему подтвердившему
Команда SHALL группировать единицы по актору их последнего подтверждения (`verified[].by` документа OKF или записи `.okf/trust.yml`), отправлять по одному сообщению на группу в порядке имён акторов, а единицы, которые никто не подтверждал, — одним последним сообщением для канала.

#### Scenario: Три группы
- GIVEN `AGENTS.md#Auth` последним подтвердил `human:ivan`, `AGENTS.md#Billing` — `human:maria`, а `AGENTS.md#Seed` не подтверждал никто, и у всех код изменился
- WHEN строятся напоминания
- THEN три сообщения: для `human:ivan` (`AGENTS.md#Auth`), для `human:maria` (`AGENTS.md#Billing`) и общее (`AGENTS.md#Seed`)

### Requirement: Сообщение Slack
Для Slack команда SHALL отправлять `{"text": …}`, где первая строка — `:mag: okf-ai: <кто>, <N> section(s) you confirmed need a recheck` (для неподтверждённых — `<N> never confirmed section(s) need(s) a recheck`), затем строка `• <единица>: <сообщение карты>` на каждую единицу и последняя строка `` After reading, confirm in one command: `okf verify "<unit>" …` ``; актор упоминается как `<@<member id>>`, если он есть в `.okf/people.yml` (`human:ivan: {slack: U0123ABC}`, путь меняет `--people`), иначе жирным `*human:ivan*`.

#### Scenario: Упоминание человека
- GIVEN в `.okf/people.yml` `human:ivan: {slack: U0IVAN}`, у `AGENTS.md#Auth` изменился `src/auth.py` 2026-10-20
- WHEN строится сообщение Slack для `human:ivan`
- THEN оно начинается с `:mag: okf-ai: <@U0IVAN>, 1 section you confirmed need a recheck`, содержит `AGENTS.md#Auth>: src/auth.py changed 2026-10-20` и заканчивается на `` confirm in one command: `okf verify "AGENTS.md#Auth"` ``

#### Scenario: Никто не подтверждал
- GIVEN группа единиц без подтверждений
- WHEN строится сообщение Slack
- THEN в первой строке `never confirmed section needs a recheck` или `never confirmed sections need a recheck`

### Requirement: Сообщение Teams
Для Microsoft Teams команда SHALL отправлять `{"type": "message", "attachments": [...]}` с одной Adaptive Card версии 1.4: заголовок `okf-ai: <кто>: <N> section(s) you confirmed need a recheck` (для неподтверждённых — `okf-ai: <N> never confirmed sections need a recheck`), строка `- <единица>: <сообщение>` на каждую единицу, строка `After reading, confirm in one command:` и команда `okf verify …` моноширинным шрифтом.

#### Scenario: Карточка
- GIVEN напоминание для `human:ivan` про `AGENTS.md#Auth`
- WHEN строится сообщение Teams
- THEN вложение имеет `contentType` `application/vnd.microsoft.card.adaptive`, а последний блок карточки — `okf verify "AGENTS.md#Auth"`

### Requirement: Ссылки на строки
Если репозиторий на GitHub, имя каждой единицы в сообщении SHALL быть ссылкой `https://github.com/<owner>/<repo>/blob/<commit>/<path>#L<line>` (в Slack — `<url|name>`, в Teams — `[name](url)`), а иначе — именем без ссылки (в Slack — кодом).

#### Scenario: Ссылка на раздел
- GIVEN `web` — `https://github.com/acme/app/blob/abc`, раздел `AGENTS.md#Auth` на строке 5
- WHEN строится сообщение Slack
- THEN в нём `• <https://github.com/acme/app/blob/abc/AGENTS.md#L5|AGENTS.md#Auth>: …`

### Requirement: Куда отправлять
Команда SHALL брать адреса вебхуков из `--slack-webhook` (по умолчанию `$OKF_SLACK_WEBHOOK`) и `--teams-webhook` (по умолчанию `$OKF_TEAMS_WEBHOOK`) и отправлять каждое напоминание в каждый заданный канал, а без обоих адресов и без `--dry-run` завершаться с кодом выхода 2 и сообщением `okf: error: set --slack-webhook (or OKF_SLACK_WEBHOOK) or --teams-webhook (or OKF_TEAMS_WEBHOOK); --dry-run prints the messages`.

#### Scenario: Slack и Teams
- GIVEN три группы напоминаний, заданы оба вебхука
- WHEN запускается `okf notify --slack-webhook <url> --teams-webhook <url>`
- THEN в каждый вебхук ушло по три сообщения, в stderr `okf notify: 3 units to recheck, 3 people or groups; sent 6 messages`, код выхода 0

#### Scenario: Нет адресов
- GIVEN не заданы ни вебхуки, ни `--dry-run`
- WHEN запускается `okf notify`
- THEN код выхода 2, ничего не отправлено

### Requirement: Пробный запуск
С `--dry-run` команда MUST NOT отправлять сообщения: она печатает в stdout каждое сообщение под строкой `--- <slack|teams>, for <кто> ---` (без вебхуков — в формате Slack), а сводка говорит `would send <N> messages`.

#### Scenario: Без вебхуков
- GIVEN вебхуки не заданы, три группы напоминаний
- WHEN запускается `okf notify --dry-run`
- THEN в stdout есть `--- slack, for human:maria ---`, в stderr `would send 3 messages`, код выхода 0

### Requirement: Повторы и ошибки отправки
Отправка SHALL повторяться до трёх раз на ответы 429, 502, 503 и 504 с паузой `Retry-After` (секунды или HTTP-дата; отрицательное значение — 0, больше 30 — 30, нечисловое — как без заголовка) или 1, 2 и 4 секунды — та же реализация повторов, что у коннекторов, а неудачная отправка — печататься в stderr как `okf notify: <slack|teams>, for <кто>: the webhook answered HTTP <код>` (или `cannot reach the webhook: …`), не прерывая остальные, с кодом выхода 1, если не ушло хотя бы одно сообщение.

#### Scenario: Лимит, затем успех
- GIVEN вебхук отвечает 429 с `Retry-After: 1`, затем 200
- WHEN отправляется сообщение
- THEN после паузы в 1 секунду сообщение доставлено со второй попытки

#### Scenario: Вебхук отвечает ошибкой
- GIVEN вебхук Slack отвечает 500
- WHEN запускается `okf notify --slack-webhook <url>`
- THEN в stderr `the webhook answered HTTP 500`, код выхода 1

### Requirement: Адрес вебхука — секрет
Адрес вебхука MUST NOT появляться в stdout, stderr и сообщениях об ошибках: ошибка называет только HTTP-статус или тип сетевой ошибки.

#### Scenario: Ошибка 404
- GIVEN вебхук `…/hooks/secret-token-123` отвечает 404
- WHEN отправка не удалась
- THEN сообщение — `the webhook answered HTTP 404`, без `secret-token-123`

### Requirement: Сводка и каталог
Команда SHALL печатать в stderr строку `okf notify: sent to <канал> for <кто> (<N> units)` на каждое отправленное сообщение и сводку `okf notify: <U> units to recheck, <P> people or groups; sent|would send <M> messages`, а для несуществующего каталога — завершаться с кодом выхода 2 и `okf: error: directory not found: <repo>`.

#### Scenario: Нет каталога
- GIVEN каталога нет
- WHEN запускается `okf notify missing --dry-run`
- THEN код выхода 2 и в stderr `okf: error: directory not found: missing`
