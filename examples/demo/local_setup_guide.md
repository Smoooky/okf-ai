---
type: "Guide"
tags: [onboarding, dev]
provenance:
  sources:
    - "git://examples/demo/src/config.py"
trust:
  generated: "human"
  verified_by: "teamlead_ivan"
  confidence: 0.9
lifecycle:
  status: "stable"
freshness:
  last_reviewed: "2026-10-01"
  stale_after: "2027-01-01"
timestamp: "2026-10-01T09:30:00Z"
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

3. SMS-коды при локальном запуске видны в MailHog-подобном шлюзе на порту 8025,
   см. [поток аутентификации](auth_flow.md).
