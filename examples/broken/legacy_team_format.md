---
type: Service
title: Старый формат командной спеки
tags: [billing]
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
---

# Старый формат командной спеки

Шапка в формате первой версии `cli-validator.md`. Для OKF v0.2 это просто лишние ключи,
поэтому без `--strict` ошибок нет. `--strict` требует официальные `sources`, `verified`
и `stale_after` и подсказывает, на что заменить старые поля.
