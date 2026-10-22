---
type: "Glossary Term"
tags: [glossary, rides]
provenance:
  sources:
    - "https://wiki.wheelo.example/glossary"
trust:
  generated: "human"
  verified_by: "pm_anna"
  confidence: 1.0
lifecycle:
  status: "stable"
freshness:
  last_reviewed: "2026-08-15"
  stale_after: "2027-08-15"
timestamp: "2026-08-15T11:00:00Z"
---

# Поездка

**Поездка** — отрезок времени от успешного [POST /rides](api_start_ride.md) до завершения
аренды самоката пользователем или поддержкой.

- Поездка в статусе `active` держит холд на карте.
- Отменённая поездка (`cancelled`) не тарифицируется.
- Каждая поездка — строка в таблице [rides](rides_table.md).

Не путать с **сессией** — открытием приложения, см. [конверсию в поездку](ride_conversion_metric.md).
