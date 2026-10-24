---
type: Architecture
title: Агент выдаёт себя за человека
tags: [auth]
status: stable
generated: { by: wheelo-docs-agent/1.4, at: 2026-10-20T09:00:00Z }
verified:
  - { by: process:okf-ci, at: 2026-10-20T09:05:00Z }
stale_after: 2027-04-20T00:00:00Z
sources:
  - resource: /src/auth.py
---

# Агент выдаёт себя за человека

Ошибка `--strict`: документ написал ИИ-агент, проверял его только CI-процесс,
а статус уже `stable`. Нужно либо подтверждение человеком (`human:<id>` в `verified`),
либо `status: draft`. В OKF v0.2 это допустимо: уровень доверия просто machine-confirmed.
