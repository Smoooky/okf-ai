# Atlassian fixtures (written by hand)

These JSON files are **not real Atlassian data**. They were written by hand in the shape of
Confluence Cloud REST v2 and Jira Cloud REST v3 answers, for the Wheelo demo and the tests.
No Atlassian account was used. The pages and issues do not exist.

With `OKF_SOURCES_FIXTURES=<this directory>` the Confluence and Jira connectors read these files
instead of the network: a request for `/wiki/api/v2/pages/131074?version=2` reads
`wiki/api/v2/pages/131074@version=2.json`, and without that query `131074.json`.

What is here:

- Confluence space `WHL` (id 98305) with two pages: 131073 «Метрики продукта» (v7, 2026-08-28)
  and 131074 «Тарифы и биллинг» (v3, 2026-10-03; v2 is the older text with 8 ₽ a minute).
- Jira epic `WHL-42` «Определение сессии для метрики конверсии», moved to Done on 2026-10-14,
  and task `WHL-57` «Ночной тариф», still in progress.

```bash
export OKF_SOURCES_FIXTURES=examples/atlassian-fixtures
export OKF_CONFLUENCE_URL=https://wheelo.atlassian.net/wiki OKF_JIRA_URL=https://wheelo.atlassian.net
okf sources examples/demo
```
