---
type: Table
title: Таблица rides
description: Одна строка на поездку; цена, длительность и GPS-точки.
tags: [database, rides]
status: stable
generated: { by: process:schema-docgen, at: 2026-09-20T08:00:00Z }
verified:
  - { by: human:data_oleg, at: 2026-09-20T11:00:00Z }
  - { by: process:schema-check, at: 2026-10-20T02:00:00Z }
stale_after: 2027-03-20T00:00:00Z
sources:
  - id: schema
    resource: ../src/schema.sql
    title: Схема БД
---

# Таблица rides

Одна строка — одна [поездка](/ride_glossary.md). PostgreSQL.

| Колонка | Тип | Описание |
|---|---|---|
| `id` | UUID | идентификатор поездки |
| `user_id` | UUID | кто едет |
| `scooter_id` | TEXT | на каком самокате |
| `status` | TEXT | `active`, `finished` или `cancelled` |
| `started_at` / `finished_at` | TIMESTAMPTZ | начало и конец |
| `minutes` | INTEGER | длительность, по ней считает [биллинг](/billing_service.md) |
| `price_rub` | INTEGER | итоговая цена |
| `start_point` / `end_point` | POINT | GPS-точки, персональные данные |

Индекс `rides_user_started_idx (user_id, started_at DESC)` — для истории поездок в приложении.
GPS-точки обнуляются через 180 дней, см. [политику хранения данных](/data_retention_policy.md).
