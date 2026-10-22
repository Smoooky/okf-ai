---
type: "Policy"
tags: [legal, privacy, database]
provenance:
  sources:
    - "https://wiki.wheelo.example/legal/personal-data"
    - "git://examples/demo/src/schema.sql"
trust:
  generated: "human"
  verified_by: "legal_elena"
  confidence: 1.0
lifecycle:
  status: "stable"
freshness:
  last_reviewed: "2026-07-01"
  stale_after: "2027-07-01"
timestamp: "2026-07-01T10:00:00Z"
---

# Политика хранения персональных данных

GPS-точки поездок — персональные данные. Wheelo хранит их не дольше 180 дней
после окончания поездки.

- Колонки `start_point` и `end_point` в [rides](rides_table.md) обнуляются ночным заданием.
- Сумма и длительность поездки хранятся 5 лет для бухгалтерии.
- Выгрузки с GPS-точками для аналитики — только с одобрения юриста.
