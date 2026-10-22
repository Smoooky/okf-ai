---
type: "Table"
tags: [database, rides]
provenance:
  sources:
    - "git://examples/demo/src/schema.sql"
trust:
  generated: "script"
  verified_by: "data_oleg"
  confidence: 0.85
lifecycle:
  status: "stable"
freshness:
  last_reviewed: "2026-09-20"
  stale_after: "2027-03-20"
timestamp: "2026-09-20T08:00:00Z"
---

# Таблица rides

Одна строка — одна [поездка](ride_glossary.md). PostgreSQL.

| Колонка | Тип | Описание |
|---|---|---|
| `id` | UUID | идентификатор поездки |
| `user_id` | UUID | кто едет |
| `scooter_id` | TEXT | на каком самокате |
| `status` | TEXT | `active`, `finished` или `cancelled` |
| `started_at` / `finished_at` | TIMESTAMPTZ | начало и конец |
| `minutes` | INTEGER | длительность, по ней считает [биллинг](billing_service.md) |
| `price_rub` | INTEGER | итоговая цена |
| `start_point` / `end_point` | POINT | GPS-точки, персональные данные |

Индекс `rides_user_started_idx (user_id, started_at DESC)` — для истории поездок в приложении.
GPS-точки обнуляются через 180 дней, см. [политику хранения данных](data_retention_policy.md).
