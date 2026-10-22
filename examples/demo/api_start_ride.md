---
type: "API Endpoint"
tags: [api, rides]
provenance:
  sources:
    - "git://examples/demo/src/rides.py"
trust:
  generated: "script"
  verified_by: "maria_backend"
  confidence: 0.8
lifecycle:
  status: "stable"
freshness:
  last_reviewed: "2026-08-10"
  stale_after: "2026-11-10"
timestamp: "2026-08-10T09:00:00Z"
---

# POST /rides — старт поездки

Описание сгенерировано скриптом из кода обработчика и проверено бэкендером.

Требует access-токен, см. [поток аутентификации](auth_flow.md).

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

При успехе [биллинг](billing_service.md) холдирует 300 ₽, а в [rides](rides_table.md)
появляется строка со статусом `active`.
