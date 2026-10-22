---
type: Metric
title: Много ошибок сразу
tags: product, rides
status: published
generated: { at: 2026-10-01T09:00:00Z }
verified:
  - { by: teamlead_ivan }
stale_after: "2027-10-19"
sources:
  - "git://src/rides.py"
  - { title: Дашборд без ссылки }
---

# Много ошибок сразу

- `tags` — строка через запятую, а не YAML-список (в OKF — предупреждение, в `--strict` — ошибка);
- `status` — не из `draft | stable | deprecated`;
- в `generated` нет `by`;
- в `verified` актор без префикса (`human:<id>`, `process:<id>` или `<agent>/<version>`) и нет `at`;
- `stale_after` — дата без времени и UTC-смещения;
- первый источник — строка, а не `{resource: ...}`, у второго нет `resource`.
