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
./scripts/seed_db.sh      # тестовые данные
```

## Где что лежит

- `src/auth.py` — вход по SMS и JWT-токены.
- `src/billing.py` — тарифы, холд и списания.
- `src/rides.py` — обработчик `POST /rides`.
- `src/config.py` — настройки из переменных окружения.
- Схема БД — [src/schema.sql](src/schema.sql).

## Правила

- Перед коммитом запускай `npm run lint` и `npm test`.
- Тарифы в `src/billing.py` меняй только вместе с `tests/test_billing.py`.
