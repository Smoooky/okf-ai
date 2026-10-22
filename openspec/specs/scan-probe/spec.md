# Scan Probe Specification

## Purpose
`okf scan` — проба на публичных репозиториях до разработки: прогоняет карту доверия `okf trust` по списку репозиториев GitHub, чтобы проверить две ставки продукта — инструкции агентов действительно отстают от кода, и связи «раздел → код» находятся верно. Команда пишет отчёт, выборку связей для ручной разметки и считает точность по разметке.

## Requirements

### Requirement: Режимы команды
Команда `okf scan` SHALL требовать ровно один режим: `--repos FILE` (прогон), `--score LABELS` (точность разметки) или `--find N` (поиск репозиториев).

#### Scenario: Режим не указан
- GIVEN не указан ни один из `--repos`, `--score`, `--find`
- WHEN запускается `okf scan`
- THEN команда завершается ошибкой использования с кодом выхода 2

#### Scenario: Два режима сразу
- GIVEN указаны `--repos repos.txt` и `--score label.csv`
- WHEN запускается `okf scan`
- THEN команда завершается ошибкой использования с кодом выхода 2

### Requirement: Список репозиториев
Команда SHALL читать из файла `--repos` по одному репозиторию на строку в виде `owner/repo`, `owner/repo@commit`, `https://github.com/owner/repo(.git)` или `git@github.com:owner/repo.git`, пропуская пустые строки и комментарии после `#` и убирая повторы без учёта регистра.

#### Scenario: Разные записи
- GIVEN строки `acme/app`, `https://github.com/acme/lib.git`, `ACME/app # повтор`, `acme/tool@3f2c1ab`
- WHEN запускается `okf scan --repos repos.txt`
- THEN сканируются `acme/app`, `acme/lib` и `acme/tool` на коммите `3f2c1ab`

#### Scenario: Строка не репозиторий GitHub
- GIVEN строка `not a repo`
- WHEN запускается `okf scan --repos repos.txt`
- THEN код выхода 2 и в stderr `okf: error: not a GitHub repository: not a repo`

#### Scenario: Нет файла
- GIVEN файла `repos.txt` нет
- WHEN запускается `okf scan --repos repos.txt`
- THEN код выхода 2 и сообщение об ошибке в stderr

### Requirement: Безопасный клон
Каждый репозиторий SHALL клонироваться частичным клоном с полной историей и без содержимого файлов заранее (`--filter=blob:none`) в отдельную временную папку (`--work`, по умолчанию системная временная папка), без запросов учётных данных, и удаляться после обработки, если не указан `--keep`; в репозиторий ничего не пишется, и код из него не запускается.

#### Scenario: Клон удаляется
- GIVEN репозиторий успешно обработан
- WHEN прогон завершён без `--keep`
- THEN временной папки клона больше нет

#### Scenario: Закреплённый коммит
- GIVEN запись `acme/tool@3f2c1ab`
- WHEN репозиторий клонируется
- THEN карта строится на коммите `3f2c1ab`
- AND если коммит не найден, репозиторий пропускается с причиной `cannot check out 3f2c1ab`

### Requirement: Сбой одного репозитория не останавливает прогон
Ошибка клонирования, приватный, удалённый или заблокированный репозиторий, лимит GitHub, таймаут (`--timeout`, по умолчанию 300 секунд) или исключение при разборе SHALL пропускать только этот репозиторий с причиной в отчёте.

#### Scenario: Приватный или удалённый
- GIVEN git сообщает `not found` или требует авторизацию
- WHEN репозиторий клонируется
- THEN строка репозитория — `status: skipped`, `reason: not found, private or renamed`

#### Scenario: Лимит GitHub
- GIVEN git сообщает `429` или `rate limit`
- WHEN репозиторий клонируется
- THEN причина — `rate limited by GitHub, retry later`

#### Scenario: Таймаут
- GIVEN клон идёт дольше `--timeout 60`
- WHEN срабатывает таймаут
- THEN причина — `timeout: clone took longer than 60 s`

#### Scenario: Исключение при разборе
- GIVEN построение карты одного репозитория падает с исключением
- WHEN идёт прогон
- THEN этот репозиторий пропущен с причиной `error: <тип>: <сообщение>`, остальные обработаны

### Requirement: Параллельность и порядок
Команда SHALL обрабатывать до `--jobs` (по умолчанию 4) репозиториев одновременно и сохранять в отчёте порядок из списка.

#### Scenario: Порядок строк
- GIVEN список `a/x`, `b/y`, `c/z` и `--jobs 3`
- WHEN прогон завершён
- THEN строки в `repos.csv` идут в порядке `a/x`, `b/y`, `c/z`

### Requirement: Файлы отчёта
Прогон SHALL писать в папку `--out` (по умолчанию `report`) файлы `summary.md`, `repos.csv` (строка на репозиторий: статус, причина, время, коммит, неполная история, счётчики файлов инструкций, единиц, уровней и статусов связей, главная причина пометок), `raw/<owner>__<repo>.json` (`okf trust --json` каждого обработанного), `repos.pinned.txt` (список с коммитами) и `label.csv`.

#### Scenario: Состав отчёта
- GIVEN два репозитория, один обработан, один пропущен
- WHEN запускается `okf scan --repos repos.txt --out report`
- THEN есть `report/summary.md`, `report/repos.csv` с двумя строками, `report/raw/` с одним JSON, `report/repos.pinned.txt` и `report/label.csv`
- AND в stderr последняя строка — `okf scan: 1 scanned, 1 skipped; see report/summary.md`, код выхода 0

#### Scenario: Воспроизводимость
- GIVEN `repos.pinned.txt` из прошлого прогона и строка `To reproduce` из `summary.md` с `--now` и `--seed`
- WHEN прогон повторяется этой командой
- THEN каждый репозиторий сканируется на тех же коммитах и на тот же момент времени

### Requirement: Сводка пробы
Файл `summary.md` SHALL содержать число обработанных и пропущенных репозиториев; доли репозиториев с ≥1 «перепроверить», с ≥1 «сломано», с любой находкой (в том числе среди репозиториев с инструкциями), без инструкций, с `AGENTS.md` и `CLAUDE.md` сразу и с неполной историей; распределение числа разделов; таблицу причин пометок; статистику связей по типам и статусам; таблицу пропущенных с причинами; команду для повтора.

#### Scenario: Доля находок
- GIVEN обработано 49 репозиториев, у 29 есть хотя бы одна находка
- WHEN пишется `summary.md`
- THEN строка «with ≥1 finding of any kind» содержит `29 of 49 (59%)`

#### Scenario: Ничего не обработано
- GIVEN все репозитории пропущены
- WHEN пишется `summary.md`
- THEN доли записаны как `0 of 0`, файл создаётся без ошибки

### Requirement: Выборка для разметки
Файл `label.csv` SHALL содержать случайную воспроизводимую выборку из `--sample` (по умолчанию 100) связей «раздел → код» с зерном `--seed` (по умолчанию 42), отсортированную по репозиторию, файлу и строке, с колонками `repo, file, line, section, source, type, extracted_from, status, correct, comment, url`, в UTF-8 с BOM.

#### Scenario: Та же выборка
- GIVEN два прогона с одинаковыми результатами и `--seed 42`
- WHEN пишется `label.csv`
- THEN выборки совпадают

#### Scenario: Связей меньше выборки
- GIVEN найдено 30 связей и `--sample 100`
- WHEN пишется `label.csv`
- THEN в файле 30 строк

#### Scenario: Ссылка на строку
- GIVEN связь из строки 14 `AGENTS.md` репозитория `acme/app` на коммите `abc123`
- WHEN пишется `label.csv`
- THEN `url` — `https://github.com/acme/app/blob/abc123/AGENTS.md#L14`

### Requirement: Точность по разметке
Команда `okf scan --score LABELS` SHALL печатать в stdout таблицу по всем связям и по каждому типу: сколько размечено, «да», «нет», «неясно», точность как доля «да» среди размеченных и доля «да» без учёта «неясно», принимая ответы `да/yes/y/+/1/true/верно`, `нет/no/n/-/0/false/неверно` и `неясно/unclear/?`.

#### Scenario: Подсчёт точности
- GIVEN в `label.csv` 4 строки типа `path`: `да`, `yes`, `нет`, `неясно`
- WHEN запускается `okf scan --score label.csv`
- THEN для `path` размечено 4, точность `50.0%`, без учёта «неясно» — `66.7%`

#### Scenario: Неизвестный ответ
- GIVEN в колонке `correct` есть значение `может быть`
- WHEN запускается `okf scan --score label.csv`
- THEN в конце вывода указано, сколько строк имеют значение не из да/нет/неясно

#### Scenario: Нет колонки correct
- GIVEN CSV без колонки `correct`
- WHEN запускается `okf scan --score file.csv`
- THEN код выхода 2 и сообщение ``okf: error: file.csv has no `correct` column``

### Requirement: Поиск репозиториев
Команда `okf scan --find N` SHALL печатать в stdout до N публичных репозиториев (не форков и не архивных) с `AGENTS.md` или `CLAUDE.md`, в которые был push за последние `--months` (по умолчанию 3) месяцев, используя авторизованный GitHub CLI.

#### Scenario: Найти репозитории
- GIVEN `gh` установлен и выполнен `gh auth login`
- WHEN запускается `okf scan --find 50 > repos.txt`
- THEN в `repos.txt` до 50 строк `owner/repo`, прогресс выводится в stderr

#### Scenario: Нет GitHub CLI
- GIVEN `gh` не установлен или не авторизован
- WHEN запускается `okf scan --find 50`
- THEN код выхода 2 и сообщение `finding repositories needs the GitHub CLI signed in (gh auth login); or write repos.txt by hand, one owner/repo per line`
