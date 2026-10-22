"""Pages for people: `okf trust --html report.html` and `okf view <repo> --out site/`.

One design for both: the okf-ai mark, the same trust bar and level badges (color, icon and word, so
levels never depend on color alone), light and dark themes with a remembered toggle, and phone widths.
Every page is a plain file with its CSS and JS inline: no CDN, fonts or libraries, works offline.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from okf import __version__, schema
from okf.bundle import Bundle, Document, load_document
from okf.git import head_info
from okf.markdown import esc, markdown_html
from okf.trust import TrustMap, Unit
from okf.values import parse_instant

__all__ = ["build_site", "find_bundles", "markdown_html", "trust_html"]

KINDS = ("broken", "recheck", "verified", "unverified")
WORDS = {"broken": "сломано", "recheck": "перепроверить", "verified": "подтверждено", "unverified": "не подтверждено"}
ICONS = {"broken": "✕", "recheck": "!", "verified": "✓", "unverified": "○"}
OKF_SPEC = "https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md"
TAGLINE = "каким знаниям агентов можно верить сейчас"
_MONTHS = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")


def kind(level: str) -> str:
    return "verified" if level in ("human-verified", "process-verified") else level


def _asset(name: str) -> str:
    return resources.files("okf").joinpath(f"templates/{name}").read_text(encoding="utf-8")


# --- Words and dates ---------------------------------------------------------------------


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """forms for 1, 2-4 and 5+: ("раздел", "раздела", "разделов")."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def date_ru(moment: datetime | None, with_year: bool = True) -> str:
    if moment is None:
        return ""
    moment = moment.astimezone(timezone.utc)
    return f"{moment.day} {_MONTHS[moment.month - 1]}" + (f" {moment.year}" if with_year else "")


def days_between(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() // 86400)


def freshness(doc: Document, now: datetime) -> tuple[str, str]:
    """("через 23 дня", css class) from stale_after."""
    expires = schema.stale_after(doc)
    if expires is None:
        return "без срока", ""
    days = days_between(now, expires)
    if expires <= now:
        return f"просрочен с {date_ru(expires)}", "fresh-late"
    text = f"через {days} {plural(days, ('день', 'дня', 'дней'))}" if days >= 1 else "сегодня"
    return text, "fresh-soon" if days <= 30 else ""


# --- Shared pieces -------------------------------------------------------------------------


LOGO = ('<svg width="{s}" height="{s}" viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
        '<path d="M16 2.6 4.6 6.9v8.3c0 7.1 4.9 12.5 11.4 14.2 6.5-1.7 11.4-7.1 11.4-14.2V6.9z" fill="var(--accent)"/>'
        '<path d="m10.6 16.1 3.8 3.8 7.2-7.9" fill="none" stroke="var(--surface)" stroke-width="2.8" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>')
SEARCH_ICON = ('<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="11" '
               'cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m20 20-3.5-3.5" '
               'stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>')
THEME_BUTTON = ('<button class="icon-btn" id="theme" type="button" aria-label="Переключить тему">'
                '<svg class="theme-light-icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">'
                '<path d="M21 14.5A8.5 8.5 0 0 1 9.5 3a8.5 8.5 0 1 0 11.5 11.5z" fill="currentColor"/></svg>'
                '<svg class="theme-dark-icon" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">'
                '<circle cx="12" cy="12" r="4.5" fill="currentColor"/><g stroke="currentColor" stroke-width="2" '
                'stroke-linecap="round"><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 '
                '1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></g></svg></button>')
THEME_EARLY = ("try{var t=localStorage.getItem('okf-theme');if(t==='light'||t==='dark')"
               "document.documentElement.setAttribute('data-theme',t)}catch(e){}")


def _page(title: str, body: str, scripts: tuple[str, ...] = ("view.js",)) -> str:
    js = "".join(f"<script>{_asset(name)}</script>" for name in scripts)
    return ('<!doctype html>\n<html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="color-scheme" content="light dark"><title>{esc(title)}</title>'
            f"<script>{THEME_EARLY}</script><style>{_asset('view.css')}</style></head>"
            f"<body>{body}{js}</body></html>\n")


def brand(href: str | None = None, size: int = 30) -> str:
    inner = (LOGO.format(s=size) + '<span class="brand-text"><span class="brand-name">okf-ai</span>'
             f'<span class="brand-tag">{TAGLINE}</span></span>')
    return f'<a class="brand" href="{esc(href)}">{inner}</a>' if href else f'<span class="brand">{inner}</span>'


def badge(level_kind: str, word: str | None = None) -> str:
    return (f'<span class="lvl lvl-{level_kind}"><span class="ico" aria-hidden="true">{ICONS[level_kind]}</span>'
            f"{esc(word or WORDS[level_kind])}</span>")


def summary(counts: dict[str, int], noun: tuple[str, str]) -> str:
    """The trust bar and the four tiles (they filter the list below). noun: ("разделов и документов", "из …")."""
    total = sum(counts.values()) or 1
    label = ", ".join(f"{WORDS[k]}: {counts[k]}" for k in KINDS)
    segments = "".join(
        f'<span class="seg-{k}" style="flex:{counts[k]} 1 0" title="{WORDS[k]}: {counts[k]}">'
        f'{counts[k] if counts[k] / total >= 0.08 else ""}</span>' for k in ("verified", "recheck", "broken", "unverified")
        if counts[k])
    tiles = "".join(
        f'<button class="tile t-{k}" type="button" data-filter="{k}" data-solo aria-pressed="true" '
        f'aria-label="Показать только: {WORDS[k]} ({counts[k]})">{badge(k)}<span class="n">{counts[k]}</span>'
        f'<span class="share">{round(100 * counts[k] / total)}% {esc(noun[0])}</span></button>' for k in KINDS)
    return f'<div class="bar" role="img" aria-label="{esc(label)}">{segments}</div><div class="tiles">{tiles}</div>'


def toolbar(counts: dict[str, int], placeholder: str) -> str:
    chips = "".join(
        f'<button class="chip c-{k}" type="button" data-filter="{k}" aria-pressed="true" '
        f'aria-label="Фильтр: {WORDS[k]}"><span class="ico" aria-hidden="true">{ICONS[k]}</span>{WORDS[k]} '
        f'<span class="count">{counts[k]}</span></button>' for k in KINDS)
    return (f'<div class="toolbar" role="search"><label class="search"><span class="sr-only">{esc(placeholder)}</span>'
            f'{SEARCH_ICON}<input id="q" type="search" placeholder="{esc(placeholder)}" autocomplete="off">'
            f'<kbd aria-hidden="true">/</kbd></label>{chips}</div>')


def _rel(path: Path, base: Path) -> str:
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:
        return Path(path).as_posix()


# --- Reasons in plain words ---------------------------------------------------------------


def _newest_change(unit: Unit) -> tuple[datetime, str, str] | None:
    """(when, what, kind) of the latest change that matters: a file, a page, a closed task."""
    found = [(at, label, "code") for label, at in unit.changed]
    found += [(r.signal.at, r.signal.subject, r.signal.reason) for r in unit.remote if r.signal]
    return max(found, key=lambda item: item[0]) if found else None


def _verified(unit: Unit) -> tuple[datetime, str] | None:
    return max(unit.verifications) if unit.verifications else None


def reason_html(unit: Unit) -> str:
    r = unit.reason
    if unit.level == "broken":
        more = len(unit.broken) - 1
        return (f"Ссылается на то, чего нет: <code>{esc(unit.broken[0])}</code>"
                + (f" и ещё {more}" if more > 0 else ""))
    if r == "recheck:moved":
        old, new, when = unit.moved[0]
        return (f"Упомянутый файл переехал: <code>{esc(old)}</code> → <code>{esc(new)}</code>"
                + (f", {date_ru(when)}" if when else ""))
    if r == "recheck:in-change":
        return "Этот набор изменений меняет " + ", ".join(f"<code>{esc(p)}</code>" for p in unit.in_change) + \
            " — а раздел не правили"
    if r == "recheck:edited":
        return "Раздел правили после подтверждения — правку ещё никто не проверил"
    if r == "recheck:regenerated":
        return f"Текст перегенерирован {date_ru(unit.generated_at)}, после подтверждения"
    if r == "recheck:stale-after":
        return f"Истёк срок свежести: <span class=\"num\">{date_ru(unit.stale_after)}</span>"
    newest = _newest_change(unit)
    after = "после подтверждения" if unit.verifications else "после последней правки"
    if newest and r in ("recheck:code-changed", "recheck:source-changed"):
        at, label, how = newest
        what = f"<code>{esc(label)}</code>" if how == "code" else esc(label)
        verb = "Код изменился" if how == "code" else "Источник обновился"
        return f"{verb} {after}: {what}, {date_ru(at)}"
    if newest and r == "recheck:closed":
        return f"Задача закрыта {after} документа: {esc(newest[1])}, {date_ru(newest[0])}"
    if r == "recheck:unpinned":
        return "Сообщение Slack, на которое ссылается документ, больше не закреплено"
    if r == "recheck:source-gone":
        return "Сообщение Slack, на которое ссылается документ, удалено"
    if r == "unverified:generated":
        return f"Текст написал <code>{esc(unit.generated_by)}</code> {date_ru(unit.generated_at)} — человек ещё не подтвердил"
    if r == "unverified:no-sources":
        return "Никто не подтверждал; ссылок на код нет"
    if r == "unverified":
        return "Никто не подтверждал; код с тех пор не менялся"
    if r == "verified":
        at, by = _verified(unit)
        tail = "код с тех пор не менялся" if unit.sources else "ссылок на код нет"
        return f"Подтверждено {date_ru(at)} — <code>{esc(by)}</code>; {tail}"
    return esc(unit.message)


def timeline(unit: Unit) -> str:
    """Two points on a line: when it was last checked (or written), and the later change."""
    if kind(unit.level) not in ("recheck", "broken"):
        return ""
    verified = _verified(unit)
    if verified:
        left = (verified[0], "проверено", verified[1])
    elif unit.generated_at and unit.generated_by:
        left = (unit.generated_at, "написано", unit.generated_by)
    elif unit.last_edited:
        left = (unit.last_edited, "правили", "раздел" if unit.kind == "instruction" else "файл")
    else:
        return ""
    newest = _newest_change(unit)
    if unit.reason == "recheck:moved" and unit.moved[0][2]:
        right = (unit.moved[0][2], "файл переехал", unit.moved[0][1])
    elif unit.reason == "recheck:stale-after" and unit.stale_after:
        right = (unit.stale_after, "истёк срок", "stale_after")
    elif unit.reason == "recheck:closed" and newest:
        right = (newest[0], "задача закрыта", newest[1])
    elif newest:
        right = (newest[0], "код изменился" if newest[2] == "code" else "источник изменился", newest[1])
    else:
        return ""
    if right[0] <= left[0]:
        return ""  # the change is not newer than the check: the reason says what is wrong
    gap = days_between(left[0], right[0])
    gap_text = f'<span class="gap">+{gap} {plural(gap, ("день", "дня", "дней"))}</span>' if gap > 0 else ""

    def point(item, side=""):
        at, what, who = item
        return (f'<div class="pt {side}"><b>{esc(what)} {date_ru(at)}</b><span>{esc(who)}</span></div>')

    return (f'<div class="timeline" aria-label="{esc(left[1])} {date_ru(left[0])}, {esc(right[1])} '
            f'{date_ru(right[0])}">{point(left)}<div class="axis">{gap_text}</div>{point(right, "right")}</div>')


def command(unit: Unit) -> str | None:
    k = kind(unit.level)
    if k == "broken":
        return "okf fix"
    if unit.reason == "recheck:moved":
        return "okf fix --apply"
    if k in ("recheck", "unverified"):
        return f'okf verify "{unit.name}"'
    return None


def _command_html(text: str | None) -> str:
    if not text:
        return ""
    return (f'<div class="cmd"><code>{esc(text)}</code><button class="copy" type="button" data-copy="{esc(text)}" '
            f'aria-label="Скопировать команду {esc(text)}">Скопировать</button></div>')


# --- okf trust --html -----------------------------------------------------------------------


def trust_html(trust_map: TrustMap, root: Path, now: datetime, shown: list[Unit] | None = None,
               web: str | None = None, git_root: Path | None = None, since: str | None = None) -> str:
    """The trust map as one self-contained page. `web`: https://github.com/<repo>/blob/<commit> for line links."""
    units = trust_map.units if shown is None else shown
    counts = {k: sum(kind(u.level) == k for u in trust_map.units) for k in KINDS}
    total = len(trust_map.units)
    branch, sha = head_info(git_root)
    meta = [f"<span>репозиторий <b>{esc(root.name)}</b></span>"]
    if branch or sha:
        meta.append(f"<span>ветка <code>{esc(branch or 'detached')}</code>"
                    + (f" · <code>{esc(sha)}</code>" if sha else "") + "</span>")
    meta.append(f"<span class=\"num\">{date_ru(now)}, {now.astimezone(timezone.utc):%H:%M} UTC</span>")
    lead = (f"Можно доверять <b>{counts['verified']} из {total}</b> "
            f"{plural(total, ('раздела и документа', 'разделов и документов', 'разделов и документов'))}. "
            f"Сломано — <b>{counts['broken']}</b>, перепроверить — <b>{counts['recheck']}</b>, "
            f"не подтверждено — <b>{counts['unverified']}</b>.")
    parts = [f'<header class="topbar"><div class="topbar-in">{brand()}<span class="spacer"></span>{THEME_BUTTON}'
             '</div></header><main class="page" id="top">',
             f'<section class="hero"><h1>Карта доверия</h1><div class="meta-line">{"".join(meta)}</div>'
             f'<p class="lead">{lead}</p>{summary(counts, ("от всех", ""))}</section>']
    if since:
        touched = len(units)
        parts.append(f'<div class="banner b-recheck" role="note"><span class="ico" aria-hidden="true">!</span>'
                     f'<div><b>Изменение относительно <code>{esc(since)}</code>:</b> задето {touched} '
                     f'{plural(touched, ("раздел", "раздела", "разделов"))}. Ниже — только они.</div></div>')
    if trust_map.shallow:
        parts.append('<div class="banner b-recheck" role="note"><span class="ico" aria-hidden="true">!</span><div>'
                     "Неполная история git: даты неизвестны. В Actions нужен <code>fetch-depth: 0</code>.</div></div>")
    shown_counts = {k: sum(kind(u.level) == k for u in units) for k in KINDS}
    parts.append(toolbar(shown_counts, "Поиск по разделам, файлам и причинам"))
    first = [u for u in units if u.level == "broken"] + [u for u in units if u.level == "recheck"]
    if first:
        parts.append('<section class="section" data-group="start"><div class="section-head"><h2>С чего начать</h2>'
                     '<span class="muted">сначала сломанное, потом то, что перепроверить</span></div><div class="cards">')
        parts.extend(_card(u, root, web, git_root) for u in first)
        parts.append("</div></section>")
    rest = [u for u in units if u.level not in ("broken", "recheck")]
    sectioned = {u.path for u in trust_map.units if u.section}
    if rest:
        parts.append('<section class="section" data-group="rest"><div class="section-head"><h2>Остальные разделы</h2>'
                     '<span class="muted">по файлам инструкций и базе знаний</span></div>')
        for title, kind_label, members in _groups(rest, root):
            group_counts = {k: sum(kind(u.level) == k for u in members) for k in KINDS}
            pills = "".join(f'<span class="lvl lvl-{k}"><span class="ico" aria-hidden="true">{ICONS[k]}</span>'
                            f'<span class="num">{group_counts[k]}</span><span class="sr-only">{WORDS[k]}</span></span>'
                            for k in KINDS if group_counts[k])
            parts.append(f'<details class="group" open data-group="{esc(title)}"><summary><span class="group-title">'
                         f'{esc(title)}</span><span class="group-kind">{esc(kind_label)}</span>'
                         f'<span class="counts">{pills}</span></summary><div class="rows">')
            parts.extend(_row(u, root, sectioned) for u in members)
            parts.append("</div></details>")
        parts.append("</section>")
    if trust_map.notes:
        parts.append('<section class="section"><div class="section-head"><h2>Проверены в другом месте</h2></div>'
                     '<div class="panel" style="padding:12px 18px"><ul>' + "".join(
                         f"<li><code>{esc(_rel(p, root))}</code>: {esc(n)}</li>" for p, n in trust_map.notes)
                     + "</ul></div></section>")
    parts.append('<p class="empty" id="empty" hidden>Ничего не найдено. Измените поиск или включите фильтры.</p></main>')
    parts.append(f'<footer class="footer"><span>Сгенерировано <code>okf trust</code> · okf-ai {__version__}</span>'
                 f'<span>Знания в формате <a href="{OKF_SPEC}">OKF v0.2</a></span>'
                 '<span>Уровень показан цветом, значком и словом: ✓ подтверждено, ! перепроверить, ✕ сломано, '
                 "○ не подтверждено</span></footer>")
    return _page(f"Карта доверия · {root.name}", "".join(parts))


def _where(unit: Unit, root: Path, web: str | None, git_root: Path | None) -> str:
    text = f"{_rel(unit.path, root)}:{unit.line}"
    if web and git_root:
        return f'<a href="{esc(web)}/{esc(_rel(unit.path, git_root))}#L{unit.line}">{esc(text)}</a>'
    return f"<code>{esc(text)}</code>"


def _search_text(unit: Unit, root: Path) -> str:
    return " ".join([unit.name, _rel(unit.path, root), unit.message, re.sub(r"<[^>]+>", "", reason_html(unit))]).lower()


def _card(unit: Unit, root: Path, web: str | None, git_root: Path | None) -> str:
    k = kind(unit.level)
    sources = [_rel(s, root) for s in unit.sources] + [r.message for r in unit.remote if r.connector and r.status == "ok"]
    chips = "".join(f"<code>{esc(s)}</code>" for s in sources[:8])
    if len(sources) > 8:
        chips += f'<span class="muted">и ещё {len(sources) - 8}</span>'
    return (f'<article class="card k-{k}" data-level="{k}" data-search="{esc(_search_text(unit, root))}">'
            f'<div class="card-head">{badge(k)}<h3>{esc(unit.name)}</h3></div>'
            f'<p class="where">{_where(unit, root, web, git_root)}</p>'
            f'<p class="why" title="{esc(unit.message)}">{reason_html(unit)}</p>{timeline(unit)}'
            + (f'<div class="chips" aria-label="Источники">{chips}</div>' if chips else "")
            + f'<div class="actions">{_command_html(command(unit))}</div></article>')


def _row(unit: Unit, root: Path, sectioned: set[Path]) -> str:
    k = kind(unit.level)
    title = unit.section or (unit.path.name if unit.kind == "knowledge" else
                             "Вступление (до первого раздела)" if unit.path in sectioned else "Весь файл")
    return (f'<div class="row" data-level="{k}" data-search="{esc(_search_text(unit, root))}">'
            f'<span class="row-title">{esc(title)}</span><span class="row-side">{badge(k)}</span>'
            f'<span class="row-why">{reason_html(unit)}</span>{_command_html(command(unit))}</div>')


def _groups(units: list[Unit], root: Path) -> list[tuple[str, str, list[Unit]]]:
    groups: dict[str, tuple[int, str, list[Unit]]] = {}
    for unit in units:
        rel = _rel(unit.path, root)
        if unit.kind == "knowledge":
            key, order, label = (os.path.dirname(rel) or ".") + "/", 4, "база знаний OKF"
        else:
            key = rel
            name = unit.path.name
            order, label = ((0, "инструкции для агентов") if name == "AGENTS.md" else
                            (1, "инструкции для Claude") if name == "CLAUDE.md" else
                            (2, "правила Cursor") if name.endswith(".mdc") or name == ".cursorrules" else
                            (3, "инструкции для агентов"))
        groups.setdefault(key, (order, label, []))[2].append(unit)
    return [(key, label, members) for key, (order, label, members) in sorted(groups.items(), key=lambda i: (i[1][0], i[0]))]


# --- okf view: a static site of the knowledge base ------------------------------------------


def find_bundles(path: Path) -> list[Path]:
    """`path` itself if it is a bundle (a root index.md), else every bundle under it."""
    path = Path(path).resolve()
    if _is_root_index(path / "index.md"):
        return [path]
    found = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "venv"))
        if "index.md" in filenames and _is_root_index(Path(dirpath) / "index.md"):
            found.append(Path(dirpath))
            dirnames[:] = []
    return found


def _is_root_index(path: Path) -> bool:
    """An index.md whose front matter has okf_version: the root of a bundle."""
    if not path.is_file():
        return False
    meta = load_document(path, path.parent).meta
    return isinstance(meta, dict) and "okf_version" in meta


class _Site:
    def __init__(self, bundle: Bundle, out: Path, units: dict[Path, Unit], now: datetime):
        self.bundle, self.out, self.units, self.now = bundle, out, units, now
        self.docs = bundle.concepts()
        self.index = next((d for d in bundle.documents if d.rel == "index.md"), None)
        heading = next(self.index.headings(level=1), None) if self.index else None
        self.title = heading[0] if heading else f"База знаний {bundle.root.name}"
        self.nav = self._nav()

    def page_name(self, doc: Document) -> str:
        return Path(doc.rel).with_suffix(".html").as_posix()

    def href(self, target_page: str, from_page: str) -> str:
        return os.path.relpath(self.out / target_page, (self.out / from_page).parent).replace(os.sep, "/")

    def level(self, doc: Document) -> str:
        unit = self.units.get(doc.path)
        return kind(unit.level) if unit else "unverified"

    def _nav(self) -> list[tuple[str, list[Document]]]:
        """Sections of index.md: a heading and the documents its list links to."""
        groups: list[tuple[str, list[Document]]] = []
        placed: set[Path] = set()
        by_path = {d.path: d for d in self.docs}
        if self.index:
            current = None
            for line in self.index.body.split("\n"):
                heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
                if heading:
                    if heading.group(1) != self.title:
                        current = (heading.group(1), [])
                        groups.append(current)
                    continue
                for target in re.findall(r"\]\(\s*<?([^)\s>]+)", line):
                    doc = by_path.get(self.bundle.resolve_link(self.index, target))
                    if doc and doc.path not in placed:
                        if current is None:
                            current = ("Документы", [])
                            groups.append(current)
                        current[1].append(doc)
                        placed.add(doc.path)
        rest = [d for d in self.docs if d.path not in placed]
        if rest:
            groups.append(("Другие документы" if placed else "Документы", sorted(rest, key=lambda d: d.title.lower())))
        return [g for g in groups if g[1]]

    def section_of(self, doc: Document) -> str | None:
        return next((title for title, docs in self.nav if doc in docs), None)

    # --- Layout ---

    def layout(self, page: str, title: str, body: str, crumbs: str = "", scripts=("view.js",)) -> str:
        home = self.href("index.html", page)
        groups = []
        for name, docs in self.nav:
            items = "".join(
                f'<li><a href="{esc(self.href(self.page_name(d), page))}"'
                + (' aria-current="page"' if self.page_name(d) == page else "")
                + f'><span class="dot d-{self.level(d)}" aria-hidden="true"></span>{esc(d.title)}'
                f'<span class="sr-only"> ({WORDS[self.level(d)]})</span></a></li>' for d in docs)
            groups.append(f'<div class="nav-group"><h4>{esc(name)}</h4><ul>{items}</ul></div>')
        service = [("index.html", "Главная"), ("graph.html", "Граф связей")]
        if any(d.rel == "log.md" for d in self.bundle.documents):
            service.append(("log.html", "Журнал изменений"))
        if any(d.rel == "AGENTS.md" for d in self.bundle.documents):
            service.append(("AGENTS.html", "Роутер для агентов"))
        service_items = "".join(f'<li><a href="{esc(self.href(target, page))}"'
                                + (' aria-current="page"' if target == page else "") + f">{esc(label)}</a></li>"
                                for target, label in service)
        sidebar = (f'<aside class="sidebar" id="nav" aria-label="Навигация по базе знаний">{brand(home, 28)}'
                   f'<label class="search"><span class="sr-only">Поиск по документам</span>{SEARCH_ICON}'
                   '<input id="nav-q" type="search" placeholder="Поиск по документам" autocomplete="off"></label>'
                   f'<nav><div class="nav-group"><ul>{service_items}</ul></div>{"".join(groups)}</nav></aside>')
        menu = ('<button class="icon-btn menu-btn" id="menu" type="button" aria-controls="nav" aria-expanded="false" '
                'aria-label="Открыть навигацию"><svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">'
                '<path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
                "</svg></button>")
        top = (f'<header class="topbar"><div class="topbar-in">{menu}<nav class="crumbs" aria-label="Путь">{crumbs}</nav>'
               f'<span class="spacer"></span>{THEME_BUTTON}</div></header>')
        footer = (f'<footer class="footer"><span>Сгенерировано <code>okf view</code> · okf-ai {__version__} · '
                  f'{date_ru(self.now)}</span><span>Формат <a href="{OKF_SPEC}">OKF v0.2</a></span></footer>')
        return _page(f"{title} · {self.title}", f'<div class="site">{sidebar}<div class="scrim"></div>'
                     f'<div class="main">{top}<main class="page">{body}</main>{footer}</div></div>', scripts)

    # --- Pages ---

    def home(self) -> str:
        page = "index.html"
        counts = {k: sum(self.level(d) == k for d in self.docs) for k in KINDS}
        intro = ""
        if self.index and self.index.body.strip():
            text = re.sub(r"^\s*#\s+.*\n", "", self.index.body, count=1)
            first = re.split(r"\n#{1,6}\s", "\n" + text.lstrip("\n"), maxsplit=1)[0]
            intro = markdown_html(first, lambda t: self._link(self.index, t, page))
        rows = []
        order = {k: i for i, k in enumerate(KINDS)}
        for doc in sorted(self.docs, key=lambda d: (order[self.level(d)], d.title.lower())):
            k = self.level(doc)
            fresh, css = freshness(doc, self.now)
            tags = _tags(doc)
            status = schema.status(doc)
            note = f' <span class="badge">{esc(status)}</span>' if status != schema.DEFAULT_STATUS else ""
            rows.append(
                f'<tr data-level="{k}" data-tags="{esc(" ".join(tags))}" '
                f'data-search="{esc((doc.title + " " + doc.rel + " " + str((doc.meta or {}).get("description", ""))).lower())}">'
                f'<td><a href="{esc(self.page_name(doc))}">{esc(doc.title)}</a>{note}'
                f'<span class="desc">{esc((doc.meta or {}).get("description", ""))}</span></td>'
                f'<td class="hide-sm">{esc((doc.meta or {}).get("type", ""))}</td>'
                f'<td class="num {css}" title="stale_after: {esc((doc.meta or {}).get("stale_after", "—"))}">{esc(fresh)}</td>'
                f"<td>{badge(k)}</td></tr>")
        tag_counts: dict[str, int] = {}
        for doc in self.docs:
            for tag in _tags(doc):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        tags = "".join(f'<button class="tag" type="button" data-tag="{esc(t)}" aria-pressed="false" '
                       f'aria-label="Фильтр по тегу {esc(t)}">#{esc(t)} <span class="muted num">{n}</span></button>'
                       for t, n in sorted(tag_counts.items()))
        n = len(self.docs)
        lead = (f"Можно доверять <b>{counts['verified']} из {n}</b> "
                f"{plural(n, ('документа', 'документов', 'документов'))}. Сломано — <b>{counts['broken']}</b>, "
                f"перепроверить — <b>{counts['recheck']}</b>, не подтверждено — <b>{counts['unverified']}</b>.")
        body = (f'<section class="hero"><h1>{esc(self.title)}</h1><div class="meta-line"><span>{n} '
                f'{plural(n, ("документ", "документа", "документов"))} OKF</span><span><a href="graph.html">Граф связей →</a>'
                f'</span></div>' + (f'<div class="panel intro prose">{intro}</div>' if intro else "")
                + f'<p class="lead" style="margin-top:22px">{lead}</p>{summary(counts, ("от всех", ""))}</section>'
                + toolbar(counts, "Поиск по документам")
                + (f'<div class="tagchips" style="margin-top:12px" aria-label="Теги">{tags}</div>' if tags else "")
                + '<section class="section" data-group="docs"><div class="table-wrap"><table><thead><tr><th>Документ</th>'
                '<th class="hide-sm">Тип</th><th>Свежесть</th><th>Доверие</th></tr></thead><tbody>'
                + "".join(rows) + '</tbody></table></div></section>'
                '<p class="empty" id="empty" hidden>Ничего не найдено. Измените поиск, тег или фильтры.</p>')
        return self.layout(page, "Главная", body, f"<span>{esc(self.title)}</span>")

    def _link(self, doc: Document, target: str, page: str) -> str:
        path = self.bundle.resolve_link(doc, target)
        if path is None or path.suffix.lower() != ".md":
            return target
        anchor = "#" + target.split("#", 1)[1] if "#" in target else ""
        try:
            rel = path.relative_to(self.bundle.root)
        except ValueError:
            return target
        name = "index.html" if rel.as_posix() == "index.md" else rel.with_suffix(".html").as_posix()
        return self.href(name, page) + anchor

    def document(self, doc: Document) -> str:
        page = self.page_name(doc)
        home = self.href("index.html", page)
        if not doc.is_concept:
            body = markdown_html(doc.body, lambda t: self._link(doc, t, page))
            return self.layout(page, doc.rel, f'<article class="panel prose">{body}</article>',
                               f'<a href="{esc(home)}">{esc(self.title)}</a><span aria-hidden="true">›</span>'
                               f"<span>{esc(doc.rel)}</span>")
        unit = self.units.get(doc.path)
        k = self.level(doc)
        meta = doc.meta or {}
        section = self.section_of(doc)
        crumbs = (f'<a href="{esc(home)}">{esc(self.title)}</a><span aria-hidden="true">›</span>'
                  + (f"<span>{esc(section)}</span><span aria-hidden=\"true\">›</span>" if section else "")
                  + f'<span aria-current="page">{esc(doc.title)}</span>')
        badges = (f'<span class="badge">{esc(meta.get("type", ""))}</span>'
                  f'<span class="badge">{esc(schema.status(doc))}</span>{badge(k)}')
        banner = ""
        if k in ("recheck", "broken") and unit:
            word = "Документ сломан" if k == "broken" else "Документ надо перепроверить"
            banner = (f'<div class="banner b-{k}" role="note"><span class="ico" aria-hidden="true">{ICONS[k]}</span>'
                      f"<div><b>{word}.</b> {reason_html(unit)}</div></div>")
        else:
            expires = schema.stale_after(doc)
            if expires and expires <= self.now:
                banner = (f'<div class="banner b-recheck" role="note"><span class="ico" aria-hidden="true">!</span>'
                          f"<div><b>Срок свежести истёк {date_ru(expires)}.</b> Сверьте документ с источниками.</div></div>")
        text = re.sub(rf"^\s*#\s+{re.escape(doc.title)}\s*\n", "", doc.body, count=1)
        sources = [e for e in meta.get("sources") or [] if isinstance(e, dict)]

        def footnote(note: str) -> str | None:
            """A footnote [^id] cites the source with the same id: link to it."""
            entry = next((e for e in sources if str(e.get("id", "")) == note), None)
            return _source_html(entry, with_title=False) if entry and entry.get("resource") else None

        body = markdown_html(text, lambda t: self._link(doc, t, page), footnote)
        body = (f'<h1 class="doc-title">{esc(doc.title)}</h1><div class="badges">{badges}</div>'
                + (f'<p class="lead-doc">{esc(meta.get("description", ""))}</p>' if meta.get("description") else "")
                + banner + f'<div class="doc-grid"><article class="panel prose">{body}</article>'
                f"{self._passport(doc, unit, k, sources)}</div>")
        return self.layout(page, doc.title, body, crumbs)

    def _passport(self, doc: Document, unit: Unit | None, k: str, sources: list[dict]) -> str:
        rows = [("Доверие", badge(k) + (f'<div class="muted" style="margin-top:6px">{reason_html(unit)}</div>'
                                        if unit else ""))]
        if sources:
            items = []
            for entry in sources:
                when = _instant(entry.get("last_modified"))
                items.append(f"<li>{_source_html(entry)}" + (f' <span class="muted">· {date_ru(when)}</span>' if when else "")
                             + "</li>")
            rows.append(("Источники", f"<ul>{''.join(items)}</ul>"))
        generated = doc.get("generated", None)
        if isinstance(generated, dict) and generated.get("by"):
            at = _instant(generated.get("at"))
            rows.append(("Сгенерировано", f"<code>{esc(generated['by'])}</code>" + (f", {date_ru(at)}" if at else "")))
        verified = schema.verifications(doc)
        if verified:
            rows.append(("Подтверждено", "<ul>" + "".join(
                f"<li><code>{esc(v.get('by'))}</code>, {date_ru(_instant(v.get('at'))) or esc(v.get('at'))}</li>"
                for v in verified) + "</ul>"))
        else:
            rows.append(("Подтверждено", '<span class="muted">никем</span>'))
        fresh, css = freshness(doc, self.now)
        expires = schema.stale_after(doc)
        rows.append(("Свежесть", f'<span class="{css}">{esc(fresh)}</span>'
                     + (f' <span class="muted">· до {date_ru(expires)}</span>' if expires else "")))
        tags = _tags(doc)
        if tags:
            rows.append(("Теги", " ".join(f'<span class="badge">#{esc(t)}</span>' for t in tags)))
        items = "".join(f"<div><dt>{name}</dt><dd>{value}</dd></div>" for name, value in rows)
        return f'<aside class="panel passport" aria-label="Паспорт знания"><h2>Паспорт знания</h2><dl>{items}</dl></aside>'

    def graph(self) -> str:
        page = "graph.html"
        docs = self.docs
        index = {d.path: i for i, d in enumerate(docs)}
        edges = set()
        for i, doc in enumerate(docs):
            for target, _ in doc.links():
                j = index.get(self.bundle.resolve_link(doc, target))
                if j is not None and j != i:
                    edges.add((min(i, j), max(i, j)))
        edges = sorted(edges)
        n = len(docs)
        nodes = []
        for i, doc in enumerate(docs):
            angle = 2 * math.pi * i / max(n, 1) - math.pi / 2
            nodes.append({"x": round(500 + 260 * math.cos(angle), 1), "y": round(350 + 260 * math.sin(angle), 1)})
        lines = "".join(f'<line class="edge" data-a="{a}" data-b="{b}" x1="{nodes[a]["x"]}" y1="{nodes[a]["y"]}" '
                        f'x2="{nodes[b]["x"]}" y2="{nodes[b]["y"]}"/>' for a, b in edges)
        groups = []
        for i, doc in enumerate(docs):
            k = self.level(doc)
            label = doc.title if len(doc.title) <= 26 else doc.title[:25] + "…"
            groups.append(f'<a class="node n-{k}" data-i="{i}" href="{esc(self.page_name(doc))}" '
                          f'transform="translate({nodes[i]["x"]},{nodes[i]["y"]})" '
                          f'aria-label="{esc(doc.title)}: {WORDS[k]}"><title>{esc(doc.title)} — {WORDS[k]}</title>'
                          f'<g class="mark"><circle r="11"/><text class="glyph" text-anchor="middle" dy="3.5">'
                          f'{ICONS[k]}</text><text x="16" dy="4">{esc(label)}</text></g></a>')
        data = json.dumps({"nodes": nodes, "edges": [list(e) for e in edges]})
        legend = "".join(badge(k) for k in KINDS)
        tools = ('<div class="graph-tools"><button class="icon-btn" id="zoom-in" type="button" aria-label="Приблизить">+'
                 '</button><button class="icon-btn" id="zoom-out" type="button" aria-label="Отдалить">−</button>'
                 '<button class="icon-btn" id="zoom-fit" type="button" aria-label="Показать всё">⤢</button></div>')
        body = (f'<section class="hero"><h1>Граф связей</h1><p class="lead">{n} '
                f'{plural(n, ("документ", "документа", "документов"))} и {len(edges)} '
                f'{plural(len(edges), ("ссылка", "ссылки", "ссылок"))} между ними. Наведите на документ — подсветятся '
                "соседи; колесо мыши — масштаб, перетаскивание фона — сдвиг, клик — открыть.</p></section>"
                f'<div class="panel graph-box">{tools}<svg id="graph" viewBox="0 0 1000 700" preserveAspectRatio="xMidYMid meet" role="img" '
                f'aria-label="Граф ссылок между документами">{lines}{"".join(groups)}</svg></div>'
                f'<div class="legend" aria-label="Легенда">{legend}</div>'
                f'<script type="application/json" id="graph-data">{data}</script>')
        return self.layout(page, "Граф связей", body,
                           f'<a href="index.html">{esc(self.title)}</a><span aria-hidden="true">›</span>'
                           "<span>Граф связей</span>", ("view.js", "graph.js"))


def build_site(bundle: Bundle, out: Path, units: dict[Path, Unit], now: datetime) -> list[Path]:
    """index.html, graph.html and a page per document (log.md and the AGENTS.md router included)."""
    out.mkdir(parents=True, exist_ok=True)
    site = _Site(bundle, out, units, now)
    written = []
    index = out / "index.html"
    index.write_text(site.home(), encoding="utf-8", newline="\n")
    graph = out / "graph.html"
    graph.write_text(site.graph(), encoding="utf-8", newline="\n")
    for doc in bundle.documents:
        if doc.rel == "index.md" or doc.text is None:
            continue
        if not doc.is_concept and doc.rel not in ("log.md", "AGENTS.md"):
            continue
        target = out / site.page_name(doc)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(site.document(doc), encoding="utf-8", newline="\n")
        written.append(target)
    return [index, graph, *written]


def _tags(doc: Document) -> list[str]:
    value = (doc.meta or {}).get("tags")
    if isinstance(value, str):
        value = [t.strip() for t in value.split(",")]
    return [str(t) for t in value or [] if str(t).strip()] if isinstance(value, list) else []


def _instant(value) -> datetime | None:
    return parse_instant(value)


def _source_html(entry: dict, with_title: bool = True) -> str:
    """A web source as a link, a path as code, with its title."""
    resource, title = str(entry.get("resource", "")), str(entry.get("title") or "")
    if re.match(r"^https?://", resource):
        return f'<a href="{esc(resource)}">{esc(title if with_title and title else resource)}</a>'
    return f"<code>{esc(resource)}</code>" + (f" — {esc(title)}" if title and with_title else "")
