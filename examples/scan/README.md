# Проба `okf scan`

Сюда кладётся список репозиториев для пробы и итоговая сводка для питча:

- `repos.sample.txt` — список (`okf scan --find 50 > examples/scan/repos.sample.txt`, нужен `gh auth login`,
  или вручную: `owner/repo` на строку);
- `summary.md` — копия `report/summary.md` после `okf scan --repos examples/scan/repos.sample.txt --out report`.

Разметку `report/label.csv` делает человек: колонка `correct` — да / нет / неясно, затем
`okf scan --score report/label.csv`.
