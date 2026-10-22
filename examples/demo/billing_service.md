---
type: "Service"
tags: [billing, payments]
provenance:
  sources:
    - "git://examples/demo/src/billing.py"
trust:
  generated: "human"
  verified_by: "maria_backend"
  confidence: 0.9
lifecycle:
  status: "stable"
freshness:
  last_reviewed: "2026-10-05"
  stale_after: "2027-04-05"
timestamp: "2026-10-05T12:30:00Z"
---

# Сервис биллинга

Считает стоимость поездки и списывает деньги с привязанной карты.

## Тарифы

- Разблокировка самоката — 50 ₽.
- Минута поездки — 8 ₽, минимум одна минута.

## Как проходит оплата

1. При [старте поездки](api_start_ride.md) на карте холдируется 300 ₽.
2. По окончании поездки списывается `50 + 8 × минуты` ₽.
3. Если списание не прошло, сервис повторяет его до 3 раз, затем снимает холд
   и помечает платёж `failed`. Что делать дальше — в [ранбуке](payment_failures_runbook.md).

Поездки и суммы хранятся в таблице [rides](rides_table.md).
