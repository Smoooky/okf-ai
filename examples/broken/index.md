---
okf_version: "0.2"
title: "Ошибка: в index.md допустим только okf_version"
---

# Сломанный бандл

Каждый файл нарушает одно или несколько правил. Запуск:
`okf validate examples/broken` (OKF v0.2) и `okf validate examples/broken --strict` (правила okf-ai).

# Ошибки OKF v0.2

* [Нет шапки](/no_front_matter.md) - файл не начинается с `---`
* [Шапка-список](/yaml_list.md) - YAML-список вместо словаря
* [Нет type](/missing_type.md) - единственное обязательное поле
* [Много ошибок сразу](/bad_fields.md) - sources, generated, verified, status, stale_after

# Ошибки профиля --strict

* [Агент выдаёт себя за человека](/agent_unreviewed_stable.md) - stable без проверки человеком
* [Протух раньше проверки](/stale_before_review.md) - stale_after раньше verified.at
* [Нет источников](/no_sources.md) - пустой sources
* [Старый формат командной спеки](/legacy_team_format.md) - provenance, trust, freshness
* [Тип не из словаря](/wrong_type.md) - предупреждение

# Предупреждения

* [Битая ссылка](/broken_link.md) - в обоих режимах

Файл `orphan.md` специально ни откуда не связан: в `--strict` это предупреждение.
