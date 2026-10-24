---
type: Runbook
title: "Ранбук: платежи не проходят"
description: Что делать дежурному, когда растёт доля неуспешных списаний.
tags: [billing, incident, oncall]
status: stable
generated: { by: wheelo-docs-agent/1.4, at: 2026-10-15T18:20:00Z }
verified:
  - { by: human:sre_pavel, at: 2026-10-16T10:00:00Z }
stale_after: 2027-01-15T00:00:00Z
sources:
  - id: billing-code
    resource: ../src/billing.py
    title: Модуль биллинга
  - id: oncall-wiki
    resource: https://wiki.wheelo.example/oncall/payments
    title: Вики дежурных
---

# Ранбук: платежи не проходят

Черновик написал ИИ-агент по коду биллинга и вики дежурных, SRE проверил и подтвердил.
Поэтому документ `stable`: в `verified` есть человек.

## Симптомы

- Растёт доля платежей `failed` в [биллинге](/billing_service.md).
- Пользователи жалуются, что поездка закончилась, а холд 300 ₽ не снялся.

## Что делать

1. Проверить статус платёжного провайдера (`WHEELO_PAYMENTS_URL`).
2. Если провайдер лежит — биллинг сам сделает 3 попытки и снимет холд; вручную ничего не списывать.[^billing-code]
3. Найти зависшие поездки:
   ```sql
   SELECT id, user_id, price_rub FROM rides WHERE status = 'finished' AND price_rub IS NULL;
   ```
4. После восстановления провайдера перезапустить списание для найденных поездок.[^oncall-wiki]

Колонки таблицы — в описании [rides](/rides_table.md).

[^billing-code]: Модуль биллинга
[^oncall-wiki]: Вики дежурных
