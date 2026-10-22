---
type: Guide
title: Локальный запуск Wheelo
description: База, переменные окружения и SMS-шлюз для разработки.
tags: [onboarding, dev]
status: stable
generated: { by: human:teamlead_ivan, at: 2026-10-01T09:30:00Z }
verified: { by: human:teamlead_ivan, at: 2026-10-01T09:30:00Z }
stale_after: 2027-01-01T00:00:00Z
sources:
  - id: config
    resource: ../src/config.py
    title: Настройки сервиса
---

# Локальный запуск Wheelo

1. Поднять PostgreSQL на `localhost:5432` с базой `wheelo`.
2. Задать переменные окружения (значения по умолчанию подходят для разработки):

   | Переменная | По умолчанию |
   |---|---|
   | `WHEELO_DATABASE_URL` | `postgresql://localhost:5432/wheelo` |
   | `WHEELO_JWT_SECRET` | `dev-secret-change-me` |
   | `WHEELO_PAYMENTS_URL` | `https://sandbox.payments.example` |
   | `WHEELO_SMS_URL` | `http://localhost:8025` |

3. SMS-коды при локальном запуске видны в тестовом шлюзе на порту 8025,
   см. [поток аутентификации](/auth_flow.md).
