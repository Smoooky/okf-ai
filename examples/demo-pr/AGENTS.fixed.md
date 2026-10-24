# AGENTS.md — Wheelo backend

Инструкции для ИИ-агентов, которые пишут код в этом репозитории.
Перед задачей открой оглавление базы знаний [knowledge/AGENTS.md](knowledge/AGENTS.md)
и читай только нужные документы.

## Команды

```bash
npm install
npm run dev               # локальный сервер на :8000
npm test                  # все тесты
make migrate              # применить схему БД
./scripts/seed.sh         # тестовые данные
```

## Auth

- Вход по SMS и JWT-токены — `src/auth.py`.
- Секрет подписи — `WHEELO_JWT_SECRET`, его читает `src/settings.py`.
- Refresh-токен живёт 30 дней; после 5 неверных кодов номер блокируется на 15 минут.

## Billing

- Тарифы, холд и списания — `src/billing.py`: 50 ₽ за разблокировку и 8 ₽ в минуту.
- Тарифы меняй только вместе с `tests/test_billing.py`.
- Старт поездки — `src/rides.py`, схема БД — [src/schema.sql](src/schema.sql).

## Правила

- Перед коммитом запускай `npm run lint` и `npm test`.
- Секреты не коммить: только переменные окружения.
