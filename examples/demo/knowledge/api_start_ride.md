---
type: API Endpoint
title: POST /rides — старт поездки
description: Проверяет самокат и карту, ставит холд и создаёт поездку.
tags: [api, rides]
status: stable
generated: { by: process:openapi-export, at: 2026-08-10T09:00:00Z }
verified:
  - { by: human:maria_backend, at: 2026-08-10T15:00:00Z }
stale_after: 2026-11-10T00:00:00Z
sources:
  - id: rides-code
    resource: ../src/rides.py
    title: Обработчик POST /rides
---

# POST /rides — старт поездки

Описание сгенерировано скриптом из кода обработчика и проверено бэкендером.

Требует access-токен, см. [поток аутентификации](/auth_flow.md).

```http
POST /rides
Authorization: Bearer <access_token>

{"scooter_id": "WH-1042"}
```

## Ответы

| Код | Тело | Когда |
|---|---|---|
| 201 | `{"ride_id": "…", "ride_status": "active"}` | поездка началась |
| 402 | `{"error": "no_payment_method"}` | у пользователя нет карты |
| 404 | `{"error": "scooter_not_found"}` | нет такого самоката |
| 409 | `{"error": "scooter_busy"}` | самокат занят |
| 409 | `{"error": "low_battery"}` | заряд ниже 15% |

При успехе [биллинг](/billing_service.md) холдирует 300 ₽, а в [rides](/rides_table.md)
появляется строка со статусом `active`.
