---
type: "Metric"
tags: "product"
provenance:
  sources:
    - "jira://WHL-42"
trust:
  generated: "human"
  confidence: "high"
lifecycle:
  status: "draft"
  freshness:
    last_reviewed: "19.10.2026"
    stale_after: "2027-10-19"
---

# Много ошибок сразу

Ошибки:

- `tags` — строка, а не список строк;
- `trust.confidence` — не число;
- нет `trust.verified_by`;
- `freshness` спрятан внутрь `lifecycle`, а должен быть на верхнем уровне
  (и дата `19.10.2026` не в формате `YYYY-MM-DD`).
