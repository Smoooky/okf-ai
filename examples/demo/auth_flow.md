---
type: "Architecture"
tags: [auth, security]
provenance:
  sources:
    - "git://examples/demo/src/auth.py"
trust:
  generated: "human"
  verified_by: "teamlead_ivan"
  confidence: 0.95
lifecycle:
  status: "stable"
freshness:
  last_reviewed: "2026-10-19"
  stale_after: "2027-04-19"
timestamp: "2026-10-19T10:00:00Z"
---

# Поток аутентификации

Как пользователь Wheelo входит в приложение и как живут его токены.

## Вход по SMS

1. Клиент отправляет номер телефона, сервис шлёт 4-значный код через SMS-шлюз.
   Код живёт 5 минут.
2. Клиент отправляет код. При совпадении сервис выдаёт пару JWT-токенов (HS256).
3. После 5 неверных кодов за 15 минут номер блокируется на 15 минут.

## Токены

| Токен | Время жизни | Зачем |
|---|---|---|
| access | 15 минут | доступ к API, например [старт поездки](api_start_ride.md) |
| refresh | 30 дней | получить новую пару без повторного SMS |

Refresh-токен помечен claim `typ: refresh`; access-токен им не обновить.
Секрет подписи берётся из `WHEELO_JWT_SECRET`, см. [локальный запуск](local_setup_guide.md).

## Связанное

- [Сервис биллинга](billing_service.md) — привязка карты проверяется уже после входа.
