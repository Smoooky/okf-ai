---
type: "Runbook"
tags: [billing, incident, oncall]
provenance:
  sources:
    - "git://examples/demo/src/billing.py"
    - "https://wiki.wheelo.example/oncall/payments"
trust:
  generated: "agent"
  verified_by: "sre_pavel"
  confidence: 0.7
lifecycle:
  status: "stable"
freshness:
  last_reviewed: "2026-10-15"
  stale_after: "2027-01-15"
timestamp: "2026-10-15T18:20:00Z"
---

# Ранбук: платежи не проходят

Черновик написан ИИ-агентом по коду биллинга и вики дежурных, проверен SRE.
Поэтому `confidence` ниже 1.0.

## Симптомы

- Растёт доля платежей `failed` в [биллинге](billing_service.md).
- Пользователи жалуются, что поездка закончилась, а холд 300 ₽ не снялся.

## Что делать

1. Проверить статус платёжного провайдера (`WHEELO_PAYMENTS_URL`).
2. Если провайдер лежит — биллинг сам сделает 3 попытки и снимет холд; вручную ничего не списывать.
3. Найти зависшие поездки:
   ```sql
   SELECT id, user_id, price_rub FROM rides WHERE status = 'finished' AND price_rub IS NULL;
   ```
4. После восстановления провайдера перезапустить списание для найденных поездок.

Колонки таблицы — в описании [rides](rides_table.md).
