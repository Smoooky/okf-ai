---
okf_version: "0.2"
---

# База знаний Wheelo

Wheelo — выдуманный сервис аренды электросамокатов. Этот бандл — демо формата
[OKF v0.2](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md):
у каждого документа YAML-шапка с типом, источниками, доверием и сроком свежести.
Для ИИ-агентов есть отдельное оглавление — [AGENTS.md](/AGENTS.md).

# Архитектура и сервисы

* [Поток аутентификации](/auth_flow.md) - вход по SMS и JWT-токены
* [Сервис биллинга](/billing_service.md) - холд, поминутное списание, повторы
* [POST /rides — старт поездки](/api_start_ride.md) - проверки и коды ответов

# Данные и метрики

* [Таблица rides](/rides_table.md) - одна строка на поездку
* [Конверсия в поездку](/ride_conversion_metric.md) - черновик метрики
* [Поездка](/ride_glossary.md) - термин из глоссария

# Эксплуатация и правила

* [Ранбук: платежи не проходят](/payment_failures_runbook.md) - для дежурных
* [Политика хранения персональных данных](/data_retention_policy.md) - 180 дней для GPS
* [Локальный запуск](/local_setup_guide.md) - для новичков

История изменений — в [log.md](/log.md).
