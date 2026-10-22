---
type: "Metric"
tags: [product, rides, analytics]
provenance:
  sources:
    - "https://metabase.wheelo.example/dashboard/12"
    - "jira://WHL-42"
trust:
  generated: "human"
  verified_by: "pm_anna"
  confidence: 0.9
lifecycle:
  status: "draft"
freshness:
  last_reviewed: "2026-09-01"
  stale_after: "2026-12-15"
timestamp: "2026-09-01T15:00:00Z"
---

# Конверсия в поездку

Доля сессий в приложении, которые закончились стартом поездки.

```
конверсия = сессии с POST /rides → 201 / все сессии с открытой картой
```

- Источник событий — [POST /rides](api_start_ride.md) и таблица [rides](rides_table.md).
- Цель на Q4 2026 — 18%, сейчас 14%.
- Главные потери: `low_battery` и `no_payment_method` (см. коды ответов эндпоинта).

Метрика в статусе черновика: определение сессии ещё обсуждается в WHL-42.
