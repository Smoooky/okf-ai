---
type: Glossary Term
title: Поездка
description: Отрезок аренды от успешного POST /rides до завершения.
tags: [glossary, rides]
status: stable
generated: { by: human:pm_anna, at: 2026-08-15T11:00:00Z }
verified: { by: human:pm_anna, at: 2026-08-15T11:00:00Z }
stale_after: 2027-08-15T00:00:00Z
sources:
  - id: glossary
    resource: https://wiki.wheelo.example/glossary
    title: Глоссарий продукта
---

# Поездка

**Поездка** — отрезок времени от успешного [POST /rides](/api_start_ride.md) до завершения
аренды самоката пользователем или поддержкой.

- Поездка в статусе `active` держит холд на карте.
- Отменённая поездка (`cancelled`) не тарифицируется.
- Каждая поездка — строка в таблице [rides](/rides_table.md).

Не путать с **сессией** — открытием приложения, см. [конверсию в поездку](/ride_conversion_metric.md).
