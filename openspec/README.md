# OpenSpec в okf-ai

[OpenSpec](https://github.com/Fission-AI/OpenSpec) — лёгкий формат спецификаций для разработки вместе с ИИ-ассистентами: сначала договариваемся, *что* должна делать система, потом пишем код. Спека — набор требований (`### Requirement:` с ключевым словом SHALL или MUST) и сценариев (`#### Scenario:` в виде GIVEN / WHEN / THEN). Здесь описано поведение, которое код `okf` уже имеет; источник истины — `openspec/specs/`.

## Что где лежит

```text
openspec/
  config.yaml                 контекст проекта и правила для артефактов (язык — русский)
  specs/                      действующие спецификации, по папке на возможность
    okf-validation/           okf validate и профиль --strict
    agents-router/            okf agents
    agent-instructions-check/ okf agents-check
    stale-docs/               okf stale
    trust-map/                okf trust и okf verify
    doc-fixes/                okf fix и --draft
    scan-probe/               okf scan
    ci-action/                GitHub Action .github/workflows/okf.yml
  changes/                    предложенные изменения, которые ещё не вошли в specs/
    add-confluence-jira-connectors/
      .openspec.yaml          схема и дата создания
      proposal.md             зачем и что меняется
      tasks.md                чек-лист работ
      specs/<capability>/spec.md  дельта-спеки: ADDED / MODIFIED / REMOVED Requirements
```

## Как предложить изменение

1. С ассистентом: `/opsx:propose <что хотим>` — он создаст папку изменения с proposal, tasks и дельта-спеками.
2. Вручную: создайте `openspec/changes/<id>/` (id в kebab-case, например `add-notion-import`) с файлами:
   - `.openspec.yaml` — `schema: spec-driven` и `created: <дата>`;
   - `proposal.md` — разделы `## Why`, `## What Changes`, `## Capabilities` (`### New Capabilities` / `### Modified Capabilities`), `## Impact` и при необходимости `## Non-Goals`;
   - `tasks.md` — пронумерованный чек-лист `- [ ] 1.1 …`;
   - `specs/<capability>/spec.md` — только то, что меняется: `## ADDED Requirements`, `## MODIFIED Requirements` (требование копируется целиком, с тем же заголовком, и правится), `## REMOVED Requirements`.
3. Обсуждаем изменение в PR, реализуем по `tasks.md`, отмечаем пункты `- [x]`.
4. После слияния изменение архивируется (`openspec archive <id>` или `/opsx:archive`): ADDED, MODIFIED и REMOVED переносятся в `openspec/specs/`, а папка изменения уходит в `changes/archive/`.

Правила оформления: в каждом требовании одно поведение и одно ключевое слово SHALL или MUST, у каждого требования хотя бы один сценарий, сценарии покрывают и ошибки, а не только успешный путь; в спеке — поведение, без деталей реализации. Текст — по-русски, заголовки OpenSpec и SHALL/MUST — по-английски.

## Старые спеки

`etc/spec/cli-validator.md` (v1) и `etc/spec/cli-validator-v2.md` сохранены как история решений команды. Актуальное поведение валидатора — в [specs/okf-validation/spec.md](specs/okf-validation/spec.md).
