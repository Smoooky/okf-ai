---
type: Policy
title: Политика хранения персональных данных
description: GPS-точки поездок храним не дольше 180 дней.
tags: [legal, privacy, database]
status: stable
generated: { by: human:legal_elena, at: 2026-07-01T10:00:00Z }
verified: { by: human:legal_elena, at: 2026-07-01T10:00:00Z }
stale_after: 2027-07-01T00:00:00Z
sources:
  - id: legal-wiki
    resource: https://wiki.wheelo.example/legal/personal-data
    title: Требования юристов
  - id: schema
    resource: ../src/schema.sql
    title: Схема БД
---

# Политика хранения персональных данных

GPS-точки поездок — персональные данные. Wheelo хранит их не дольше 180 дней
после окончания поездки.[^legal-wiki]

- Колонки `start_point` и `end_point` в [rides](/rides_table.md) обнуляются ночным заданием.[^schema]
- Сумма и длительность поездки хранятся 5 лет для бухгалтерии.
- Выгрузки с GPS-точками для аналитики — только с одобрения юриста.

[^legal-wiki]: Требования юристов
[^schema]: Схема БД
