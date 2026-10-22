# CLAUDE.md

Инструкции для Claude Code в репозитории Wheelo.

- Запуск: `npm run dev`.
- Тесты: `npm run test:unit`, один файл — `pytest tests/test_billing.py`.
- Тестовые данные: `make seed`.
- Настройки сервиса — `src/config.py`; секреты только через переменные окружения.
- База знаний лежит в `knowledge/`, оглавление для агентов: @knowledge/AGENTS.md
