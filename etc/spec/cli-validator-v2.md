> Актуальная спецификация теперь в OpenSpec: [openspec/specs/okf-validation/spec.md](../../openspec/specs/okf-validation/spec.md).
# Main Spec v2: CLI-валидатор OKF v0.2 и строгий профиль okf-ai

> Заменяет [cli-validator.md](cli-validator.md) для кода в `src/okf/`. Первая версия описывала собственную
> схему полей (`provenance.sources`, `trust.confidence`, `freshness.*`), которая расходится с официальной
> OKF v0.2. Команда выбрала вариант «официальная OKF как основа + правила команды отдельным профилем».
> Источник истины формата — [SPEC.md](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
> (номера параграфов ниже — оттуда).

## Purpose

`okf validate <bundle>` проверяет, что бандл соответствует OKF v0.2. `okf validate <bundle> --strict`
дополнительно применяет правила команды okf-ai: каждое знание с источником, проверкой и сроком свежести,
и ИИ не может выдавать непроверенный документ за готовый.

Уровни: **ERROR** — код выхода 1; **WARNING** — код выхода 0.

---

## Профиль `okf` (по умолчанию): соответствие OKF v0.2

### Requirement: Шапка документа (§4, §11)

Документом-концептом считается каждый `.md`, кроме `index.md` и `log.md` на любом уровне
и `AGENTS.md` в корне бандла. Корневой `AGENTS.md` пропускается всегда — и тот, что сгенерировал
`okf agents`, и написанный вручную; его ссылки не считаются. Вложенный `AGENTS.md` (`sub/AGENTS.md`)
проверяется как обычный концепт: без шапки с `type` — ERROR.

#### Сценарий: Нет шапки
- **WHEN** документ не начинается с `---` или шапка не закрыта.
- **THEN** ERROR `frontmatter`.

#### Сценарий: Шапка не парсится или не словарь
- **WHEN** YAML с синтаксической ошибкой, пустой, список или скаляр.
- **THEN** ERROR `frontmatter`.

#### Сценарий: Нет type
- **WHEN** `type` отсутствует, пустой или не строка.
- **THEN** ERROR `type`.
- Незнакомые значения `type` и любые лишние ключи — **не** ошибка (§4.1, §11).

### Requirement: Поля семейств, если они есть (§5, §7)

Все семейства необязательны; если поле есть, оно должно быть в формате спеки.

#### Сценарий: tags
- **WHEN** `tags` есть, но не YAML-список строк (например, строка `a, b`).
- **THEN** WARNING `tags`: официальные примеры так делают, спека считает это мягким правилом.

#### Сценарий: sources
- **WHEN** `sources` не список, или запись не словарь, или у записи нет непустого строкового `resource`.
- **THEN** ERROR `sources` / `sources[i]` / `sources[i].resource`.
- `resource` — URL, путь от корня бандла `/…`, относительный путь или описание области; не проверяется на существование.

#### Сценарий: generated
- **WHEN** `generated` не словарь, или в нём нет `by`.
- **THEN** ERROR `generated` / `generated.by`.

#### Сценарий: verified
- **WHEN** `verified` не словарь и не список, или у записи нет `by` или `at`.
- **THEN** ERROR `verified` / `verified[i].by` / `verified[i].at`. Одиночный словарь — список из одной записи (§5.2).

#### Сценарий: Акторы
- **WHEN** `generated.by` или `verified[].by` не в формате `human:<id>`, `process:<id>` или `<producer>/<version>`.
- **THEN** ERROR на это поле.

#### Сценарий: status
- **WHEN** `status` не из `draft | stable | deprecated`.
- **THEN** ERROR `status`. Нет поля — значит `stable`.

#### Сценарий: Время
- **WHEN** `stale_after`, `generated.at`, `verified[].at`, `sources[].last_modified` или `usage_window.from/to`
  не ISO 8601 datetime с явным UTC-смещением (`2026-06-30T14:00:00Z`). Дата без времени тоже ошибка.
- **THEN** ERROR на это поле.

#### Сценарий: Attested Computation
- **WHEN** `type: Attested Computation` без `runtime` (§10.2).
- **THEN** ERROR `runtime`.

### Requirement: Служебные файлы (§3.1, §8, §9)

#### Сценарий: Шапка в index.md
- **WHEN** у `index.md` есть шапка, кроме корневого `index.md` с единственным ключом `okf_version`.
- **THEN** ERROR `frontmatter`. Если `okf_version` не `0.2` — WARNING `okf_version`.

#### Сценарий: Даты в log.md
- **WHEN** заголовок второго уровня в `log.md` — не дата `YYYY-MM-DD`.
- **THEN** WARNING `log`. Шапку в `log.md` OKF не запрещает, в профиле `okf` это не ошибка.

### Requirement: Ссылки (§6.1)

#### Сценарий: Битые ссылки
- **WHEN** markdown-ссылка (`/…` от корня бандла или относительная) ведёт на несуществующий файл.
- **THEN** WARNING `link`. Внешние ссылки, якоря, сноски `[^id]` и код не проверяются.

---

## Профиль `strict` (`--strict`): правила okf-ai

Всё из профиля `okf`, плюс:

#### Сценарий: Нет источников
- **WHEN** `sources` нет или это пустой список.
- **THEN** ERROR `sources`.

#### Сценарий: Нет проверки
- **WHEN** `verified` нет или это пустой список. Аналог «нет `trust.verified_by`» из v1.
- **THEN** ERROR `verified`.

#### Сценарий: Нет срока свежести
- **WHEN** `stale_after` нет.
- **THEN** ERROR `stale_after`.

#### Сценарий: Документ протух раньше проверки
- **WHEN** `stale_after` раньше самой поздней `verified[].at`.
- **THEN** ERROR `stale_after`.

#### Сценарий: ИИ выдаёт себя за человека
- **WHEN** `generated.by` — не `human:` (агент или процесс), в `verified` нет ни одной записи `human:`,
  а `status` равен `stable` (или не указан).
- **THEN** ERROR `verified`: нужна проверка человеком или `status: draft`.
  В OKF у такого документа просто уровень доверия machine-confirmed; команда требует, чтобы
  непроверенное человеком знание не было `stable`. Хранимого `confidence` в OKF нет и не вводим.

#### Сценарий: Неверный формат tags
- **WHEN** `tags` не YAML-список строк.
- **THEN** ERROR `tags` (в профиле `okf` — WARNING).

#### Сценарий: Тип не из словаря
- **WHEN** `type` не из словаря (Приложение 2).
- **THEN** WARNING `type` с подсказкой ближайшего значения. Не ERROR: OKF требует терпеть незнакомые типы.

#### Сценарий: Шапка в log.md
- **WHEN** у `log.md` есть шапка.
- **THEN** ERROR `frontmatter`.

#### Сценарий: Недостижимые файлы (Orphan Concepts)
- **WHEN** на документ не ссылается ни один другой файл бандла (ссылки из `AGENTS.md` не считаются).
- **THEN** WARNING `link`.

#### Подсказки миграции с v1
Если вместо `sources`, `verified`, `stale_after` в шапке есть старые `provenance`, `trust`, `freshness`,
ошибка подсказывает, на что их заменить.

---

## Приложение 1: Эталонная шапка (проходит `--strict`)

```yaml
---
type: Architecture
title: Поток аутентификации
description: Вход по SMS-коду и жизненный цикл JWT-токенов.
tags: [auth, security]
status: stable
generated: { by: human:teamlead_ivan, at: 2026-10-19T10:00:00Z }
verified:
  - { by: human:teamlead_ivan, at: 2026-10-19T10:00:00Z }
stale_after: 2027-04-19T00:00:00Z
sources:
  - id: auth-code
    resource: /src/auth.py
    title: Модуль авторизации
---
```

## Приложение 2: Словарь type для `--strict`

`Concept`, `Architecture`, `Table`, `Dataset`, `Metric`, `API Endpoint`, `Runbook`, `Playbook`, `Guide`,
`Reference`, `Policy`, `Service`, `Repository`, `Glossary Term` — из v1, плюс `Attested Computation`,
который определяет сама OKF (§10).

## Приложение 3: Поля v1 → OKF v0.2

| v1 (командная спека) | OKF v0.2 |
|---|---|
| `provenance.sources: ["git://src/auth.py"]` | `sources: [{resource: /src/auth.py}]` — путь от корня бандла, относительный путь или `https://github.com/<owner>/<repo>/blob/<ref>/<path>` |
| `trust.generated: human \| script \| agent` | `generated.by: human:<id> \| process:<id> \| <agent>/<version>` |
| `trust.verified_by: ivan` | `verified: [{by: human:ivan, at: <datetime>}]` |
| `trust.confidence: 0.9` | нет: уровень доверия выводится из `verified` (unverified / machine-confirmed / human-reviewed) |
| «агент + `confidence: 1.0`» | «не-human `generated.by` + `status: stable` без human в `verified`» |
| `lifecycle.status` | `status` |
| `freshness.last_reviewed` | последняя `verified[].at` |
| `freshness.stale_after: 2027-04-19` | `stale_after: 2027-04-19T00:00:00Z` |
| `timestamp` | `generated.at` |

## Приложение 4: Формат вывода

```
[LEVEL] file_path: field_name: error_message
```

```
[ERROR] docs/auth.md: verified: Document generated by "docs-agent/1.4" is status: stable without human review; add a human:<id> entry to verified or set status: draft
[ERROR] docs/api.md: stale_after: Value "2027-10-19" must be an ISO 8601 datetime with a UTC offset, e.g. 2026-06-30T14:00:00Z
[WARNING] docs/api.md: type: Value "Endpoint" is not in the okf-ai type dictionary (did you mean "API Endpoint"?)
[WARNING] docs/user.md: link: Broken link to /concepts/missing_file.md
```
