# Конкурентный анализ: OKF, инструкции для ИИ-агентов и актуальность документации

Обновлено 22.10.2026 по веб-проверке (звёзды — GitHub API на эту дату). Заменяет первую версию файла: восемь инструментов из неё (OpenKB, kompend, vault2okf, okbase, llm-wiki, okf-cli, oknoll, okf-schema) не нашлись ни в поиске GitHub, ни в четырёх каталогах awesome-okf, поэтому таблицы с ними убраны. Подробный разбор с источниками — в [маркет-рисёрче](research/market-research/2026-10-22_17-16_okf-ai-market-research-result.md) и [ценностном предложении](research/craft-value-proposition/2026-10-22_17-41_okf-ai-craft-value-proposition-result.md).

**Легенда:** ✅ есть · ⚠️ частично · ❌ нет · ❓ не проверено.

## 1. Формат OKF и инструменты вокруг него

[OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md) — настоящий формат Google Cloud: v0.1 вышла в июне 2026, у репозитория около 1,1 тыс. звёзд и 6 коммитов. Поля источников, доверия и свежести (`sources`, `generated`, `verified`, `status`, `stale_after`) уже есть в самой спеке — это не наше отличие.

| Инструмент | Что делает | Валидатор | Свежесть по коду | Правка документов | Примечание |
|---|---|---|---|---|---|
| [W4G1/okf](https://github.com/W4G1/okf) | CLI на Rust для v0.2 | ✅ | ❌ | ❌ | |
| [openknowledge-sh/openknowledge](https://github.com/openknowledge-sh/openknowledge) | CLI `okn`: setup, check, search, publish | ✅ | ❌ | ❌ | |
| [scaccogatto/okf-skills](https://github.com/scaccogatto/okf-skills) | Навыки для агентов (Claude Code, Cursor, Codex и др.) + GitHub Action | ✅ | ⚠️ по дате `stale_after`, не по коду | ⚠️ навыки «maintain» | 423★, ближайший к нам |
| okft, myokf-cli, binder, convert-to-okf, официальный Python SDK | Линтеры, MCP-сервер, конвертеры markdown → OKF | ✅ | ❌ | ❌ | из каталогов [awesome-okf](https://github.com/Albertchamberlain/Awesome-OKF) |
| Конвертеры из Feishu, Obsidian, Notion | Импорт в OKF | ❌ | ❌ | ❌ | [yzfly/awesome-okf](https://github.com/yzfly/awesome-okf) |
| **okf-ai** | Валидатор + строгий профиль, карта доверия, страж в PR, правки | ✅ | ✅ по истории git | ✅ без ИИ и черновиком через ИИ | |

Вывод: валидаторов и CLI за 4 месяца появилось больше десяти — этот слой занят и бесплатен.

## 2. Инструкции для ИИ-агентов (AGENTS.md, CLAUDE.md, правила Cursor)

| Инструмент | Что делает | ★ / цена | Битые ссылки | По изменениям в PR | Один источник для агентов | Кто проверил и когда устарело |
|---|---|---|---|---|---|---|
| [Ruler](https://github.com/intellectronica/ruler) | Раскладывает `.ruler/` в файлы всех агентов | 2 950★, MIT | ❌ | ❌ | ✅ | ❌ |
| [rulesync](https://github.com/dyoshikawa/rulesync) | Синхронизирует правила между агентами | 1 544★, MIT | ❓ | ❌ | ✅ | ❌ |
| [agnix](https://github.com/agent-sh/agnix) | Линтер и LSP для CLAUDE.md, AGENTS.md, SKILL.md | 457★ | ⚠️ | ❌ | ❌ | ❌ |
| [agent-config-lint](https://github.com/duke5am/agent-config-lint) | Мёртвые пути, противоречия, дубли | ❓ | ✅ | ⚠️ коды выхода CI | ⚠️ | ❌ |
| [agentdrift](https://github.com/LoicRU/agentdrift) | Мёртвые скрипты и пути, не тот пакетный менеджер | новый | ✅ | ❓ | ❌ | ❌ |
| [cclint](https://github.com/felixgeelhaar/cclint) | Линтер только для Claude Code | 12★ | ⚠️ | ⚠️ | ❌ | ❌ |
| Claude Code (`/init`, auto memory) | Создаёт CLAUDE.md, ведёт свою память | в подписке | ❌ | ❌ | ⚠️ читает AGENTS.md | ❌ |
| **okf-ai** | `agents-check`, `trust`, `fix` | открытый код | ✅ | ✅ | ⚠️ совместим с Ruler | ✅ |

Вывод: синхронизация закрыта, линтеров 6+. Свободно — связка «что задел этот PR + кто проверил + когда устарело».

## 3. Обновление документации вслед за кодом

| Решение | Что делает | Цена | Слабые места |
|---|---|---|---|
| [Mintlify](https://mintlify.com) + агент | Хостинг docs-as-code, агент обновлений | Pro ~$450/мес, обновление ≈ 250 кредитов | Цена и лимиты кредитов; публичная документация |
| Promptless | PR в документацию по коду и тредам Slack | ~$200–500/мес | Лимит страниц; публичная документация |
| [Swimm](https://swimm.io) | Документы, привязанные к коду | по запросу | Шум в PR (единичный отзыв) |
| [GitBook](https://www.gitbook.com) Agent | Git sync, ИИ в верхнем тарифе | от ~$4,4 тыс./год | ИИ только в Ultimate; пишет про OKF |
| DeepWiki / Devin Wiki | Автовики по репозиторию | для публичных бесплатно | Нет PR и ревью человеком |
| [docdecay](https://pypi.org/project/docdecay/) | Находит устаревшее, рассылает владельцам | бесплатно | Ничего не правит |
| Confluence, Notion, Яндекс Вики, Teamly | Вики для людей | по местам | Живут вне процесса разработки |

Вывод: автообновление документации — паритет, без него продукт слабее всех. Отличие okf-ai — открытый формат, свои ключи LLM без лимита кредитов, видно кто и когда проверил, инструкции агентов внутри той же базы.

## 4. Где мы выигрываем (гипотеза)

Доверие на уровне раздела, обновляемое по изменениям кода (не по дате), + пометки и правки только для того, что задел PR, + поверх существующих файлов без переезда. Ни один клиент это пока не подтвердил — проверка в [PRD](research/product-requirements/2026-10-22_18-04_okf-ai-product-requirements-result.md) (R7–R9).
