---
type: Metric
title: Конверсия в поездку
description: Доля сессий с открытой картой, которые закончились стартом поездки.
tags: [product, rides, analytics]
status: draft
generated: { by: human:pm_anna, at: 2026-09-01T15:00:00Z }
verified: { by: human:pm_anna, at: 2026-09-01T15:00:00Z }
stale_after: 2026-12-15T00:00:00Z
sources:
  - id: dashboard
    resource: https://metabase.wheelo.example/dashboard/12
    title: Дашборд конверсии
    author: human:pm_anna
    usage_count: 340
  - id: definition
    resource: https://tracker.wheelo.example/browse/WHL-42
    title: Обсуждение определения сессии
usage_window: { from: 2026-08-01T00:00:00Z, to: 2026-08-31T00:00:00Z }
---

# Конверсия в поездку

Доля сессий в приложении, которые закончились стартом поездки.[^dashboard]

```
конверсия = сессии с POST /rides → 201 / все сессии с открытой картой
```

- Источник событий — [POST /rides](/api_start_ride.md) и таблица [rides](/rides_table.md).
- Цель на Q4 2026 — 18%, сейчас 14%.
- Главные потери: `low_battery` и `no_payment_method` (см. коды ответов эндпоинта).

Метрика в статусе черновика: определение сессии ещё обсуждается.[^definition]

[^dashboard]: Дашборд конверсии
[^definition]: Обсуждение определения сессии
