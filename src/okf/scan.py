"""`okf scan`: the trust map over a list of public repositories, for a probe before building more.

    okf scan --repos repos.txt --out report/     # clone each (history, no file contents up front), map, delete
    okf scan --score report/label.csv            # precision of the hand-labelled links
    okf scan --find 50 > repos.txt               # public repos with AGENTS.md / CLAUDE.md, via `gh api`

Nothing is written to the scanned repositories and no code from them is run: okf only reads
files and asks git for history. Every clone goes to its own temporary directory, removed after.
"""

from __future__ import annotations

import csv
import json
import os
import random
import re
import shutil
import stat
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from okf.git import History
from okf.instructions import discover
from okf.trust import build_map, unit_json

LABEL_COLUMNS = ["repo", "file", "line", "section", "source", "type", "extracted_from", "status", "correct",
                 "comment", "url"]
REPO_COLUMNS = ["repo", "status", "reason", "seconds", "commit", "shallow", "instruction_files", "agents_md",
                "claude_md", "cursor_rules", "copilot", "ruler", "units", "instruction_units", "knowledge_units",
                "verified", "recheck", "broken", "unverified", "links", "broken_links", "moved_links",
                "unclear_links", "unknown_links", "top_reason"]
YES = {"да", "yes", "y", "д", "+", "1", "true", "верно"}
NO = {"нет", "no", "n", "н", "-", "0", "false", "неверно"}
UNCLEAR = {"неясно", "unclear", "?", "не ясно", "непонятно"}
_GITHUB_RE = re.compile(r"^(?:https?://github\.com/|git@github\.com:)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?(?:@(\S+))?$")


class ScanError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepoSpec:
    name: str  # owner/repo
    ref: str | None = None  # a commit to check out, for a reproducible run

    @property
    def url(self) -> str:
        return f"https://github.com/{self.name}.git"


def parse_repos(text: str) -> list[RepoSpec]:
    """`owner/repo`, `owner/repo@commit` or a GitHub URL per line; `#` starts a comment."""
    specs, seen = [], set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = _GITHUB_RE.match(line)
        if not match:
            raise ScanError(f"not a GitHub repository: {line}")
        name = f"{match.group(1)}/{match.group(2)}"
        if name.lower() not in seen:
            seen.add(name.lower())
            specs.append(RepoSpec(name, match.group(3)))
    return specs


# --- Running the probe ------------------------------------------------------------


def scan(specs: list[RepoSpec], out: Path, jobs: int = 4, sample: int = 100, seed: int = 42,
         now: datetime | None = None, timeout: int = 300, work: Path | None = None, keep: bool = False,
         clone: Callable | None = None, log: Callable[[str], None] = lambda _: None) -> list[dict]:
    """Scan every repository and write the report. `clone(spec, directory, timeout)` is replaceable for tests."""
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw").mkdir(exist_ok=True)
    started = time.monotonic()

    def one(spec: RepoSpec) -> dict:
        result = scan_one(spec, now, timeout, work, keep, clone or _clone)
        log(f"okf scan: {spec.name}: {result['row']['status']} {result['row']['reason']} "
            f"({result['row']['seconds']} s)".rstrip())
        return result

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        results = list(pool.map(one, specs))  # keeps the order of the list
    for result in results:
        if result["map"] is not None:
            raw = out / "raw" / (result["row"]["repo"].replace("/", "__") + ".json")
            raw.write_text(json.dumps(result["map"], ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [r["row"] for r in results]
    _write_csv(out / "repos.csv", REPO_COLUMNS, rows)
    pinned = [f"{r['repo']}@{r['commit']}" if r["commit"] else r["repo"] for r in rows]
    (out / "repos.pinned.txt").write_text("\n".join(pinned) + "\n", encoding="utf-8")
    labels = sample_links(results, sample, seed)
    _write_csv(out / "label.csv", LABEL_COLUMNS, labels)
    elapsed = time.monotonic() - started
    (out / "summary.md").write_text(summary(results, now, seed, elapsed, len(labels)), encoding="utf-8")
    return rows


def scan_one(spec: RepoSpec, now: datetime, timeout: int, work: Path | None, keep: bool, clone: Callable) -> dict:
    started = time.monotonic()
    row = {column: "" for column in REPO_COLUMNS}
    row.update(repo=spec.name, status="skipped")
    # resolve(): on Windows the temp directory may come as a short 8.3 name
    directory = Path(tempfile.mkdtemp(prefix="okf-scan-", dir=work)).resolve()
    trust = None
    try:
        reason = clone(spec, directory, timeout)
        if reason:
            row["reason"] = reason
        else:
            trust = _map_repository(spec, directory, now)
            row.update(trust["row"])
            row["status"] = "ok"
    except Exception as exc:  # one bad repository must not stop the probe
        row["reason"] = f"error: {type(exc).__name__}: {exc}"[:200]
    finally:
        if not keep:
            _remove(directory)
    row["seconds"] = round(time.monotonic() - started, 1)
    return {"row": row, "map": trust["map"] if trust else None, "links": trust["links"] if trust else []}


def _map_repository(spec: RepoSpec, root: Path, now: datetime) -> dict:
    root = root.resolve()
    history = History(root, now)
    trust_map = build_map(root, history, now=now)
    commit = _git(root, "rev-parse", "HEAD")
    files = discover(root)
    real = [f for f in files if not f.alias_of and not f.generated_from]
    names = [f.path.name for f in files]
    levels = Counter(u.level for u in trust_map.units)
    reasons = Counter(u.reason for u in trust_map.units if u.level in ("broken", "recheck"))
    links = []
    for unit in trust_map.units:
        if unit.kind != "instruction":
            continue
        for link in unit.links:
            links.append({"repo": spec.name, "file": Path(unit.path).relative_to(root).as_posix(), "line": link["line"],
                          "section": unit.section or "", "source": link["source"], "type": link["type"],
                          "extracted_from": link["text"], "status": link["status"], "correct": "", "comment": "",
                          "url": f"https://github.com/{spec.name}/blob/{commit}/"
                                 f"{Path(unit.path).relative_to(root).as_posix()}#L{link['line']}"})
    statuses = Counter(link["status"].split(":")[0] for link in links)
    row = {
        "commit": commit,
        "shallow": "yes" if history.shallow else "no",
        "instruction_files": len(real),
        "agents_md": names.count("AGENTS.md"),
        "claude_md": names.count("CLAUDE.md"),
        "cursor_rules": sum(1 for f in files if f.path.suffix == ".mdc" or f.path.name == ".cursorrules"),
        "copilot": sum(1 for f in files if f.path.name == "copilot-instructions.md"),
        "ruler": sum(1 for f in files if f.generated_from),
        "units": len(trust_map.units),
        "instruction_units": sum(u.kind == "instruction" for u in trust_map.units),
        "knowledge_units": sum(u.kind == "knowledge" for u in trust_map.units),
        "verified": levels["human-verified"] + levels["process-verified"],
        "recheck": levels["recheck"],
        "broken": levels["broken"],
        "unverified": levels["unverified"],
        "links": len(links),
        "broken_links": statuses["broken"],
        "moved_links": statuses["moved"],
        "unclear_links": statuses["unclear"],
        "unknown_links": statuses["unknown"],
        "top_reason": reasons.most_common(1)[0][0] if reasons else "",
    }
    data = {"repo": spec.name, "commit": commit, "scanned_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary": trust_map.summary(), "units": [unit_json(u, root) for u in trust_map.units],
            "notes": [{"file": Path(p).relative_to(root).as_posix(), "note": n} for p, n in trust_map.notes]}
    return {"row": row, "map": data, "links": links}


def _clone(spec: RepoSpec, directory: Path, timeout: int) -> str | None:
    """Partial clone with full history but file contents on demand. Returns why it failed, or None."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": "", "GCM_INTERACTIVE": "never"}
    command = ["git", "-c", "credential.helper=", "clone", "--filter=blob:none", "--no-tags", "--quiet",
               spec.url, str(directory)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return f"timeout: clone took longer than {timeout} s"
    if result.returncode != 0:
        return _clone_failure(result.stderr)
    if spec.ref:
        checkout = subprocess.run(["git", "checkout", "-q", spec.ref], cwd=directory, capture_output=True, text=True,
                                  env=env, timeout=timeout)
        if checkout.returncode != 0:
            return f"cannot check out {spec.ref}"
    return None


def _clone_failure(stderr: str) -> str:
    text = stderr.lower()
    if "not found" in text or "could not read username" in text or "authentication" in text:
        return "not found, private or renamed"
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return "rate limited by GitHub, retry later"
    if "dmca" in text or "access blocked" in text or "disabled" in text:
        return "repository disabled"
    first = next((line.strip() for line in stderr.splitlines() if line.strip()), "unknown error")
    return f"clone failed: {first}"[:200]


# --- The report --------------------------------------------------------------------


def summary(results: list[dict], now: datetime, seed: int, seconds: float, labels: int) -> str:
    rows = [r["row"] for r in results]
    done = [r for r in rows if r["status"] == "ok"]
    skipped = [r for r in rows if r["status"] != "ok"]
    with_instructions = [r for r in done if int(r["instruction_files"] or 0) > 0]

    def share(items, total=None) -> str:
        total = len(done) if total is None else total
        return f"{len(items)} of {total} ({100 * len(items) / total:.0f}%)" if total else "0 of 0"

    recheck = [r for r in done if int(r["recheck"]) > 0]
    broken = [r for r in done if int(r["broken"]) > 0]
    any_finding = [r for r in done if int(r["recheck"]) + int(r["broken"]) > 0]
    both = [r for r in done if int(r["agents_md"]) > 0 and int(r["claude_md"]) > 0]
    shallow = [r for r in done if r["shallow"] == "yes"]
    sections = [int(r["instruction_units"]) for r in done]

    lines = [
        f"# okf scan: {len(rows)} repositories",
        "",
        f"Scanned {now.strftime('%Y-%m-%d %H:%M UTC')} in {seconds / 60:.1f} min; label sample seed {seed}.",
        "Each repository was cloned with full history (`git clone --filter=blob:none`), mapped with `okf trust`, "
        "then deleted. Nothing was written to the repositories.",
        "",
        "## Results",
        "",
        "| | Repositories |",
        "|---|---|",
        f"| processed | {len(done)} |",
        f"| skipped | {len(skipped)} |",
        f"| with ≥1 section to recheck | {share(recheck)} |",
        f"| with ≥1 broken reference | {share(broken)} |",
        f"| with ≥1 finding of any kind (the \"wow\" moment) | {share(any_finding)} |",
        f"| … of those with agent instructions | {share([r for r in any_finding if r in with_instructions], len(with_instructions))} |",
        f"| without agent instructions | {share([r for r in done if r not in with_instructions])} |",
        f"| with both AGENTS.md and CLAUDE.md | {share(both)} |",
        f"| shallow history (dates unknown) | {share(shallow)} |",
        "",
        "## Sections per repository",
        "",
    ]
    if sections:
        lines.append(f"Median {statistics.median(sections):g}, mean {statistics.mean(sections):.1f}, "
                     f"max {max(sections)}.")
        lines += ["", "| Sections | Repositories |", "|---|---|"]
        for label, low, high in (("0", 0, 0), ("1–5", 1, 5), ("6–10", 6, 10), ("11–20", 11, 20), ("21–50", 21, 50),
                                 ("more than 50", 51, 10**9)):
            lines.append(f"| {label} | {sum(low <= n <= high for n in sections)} |")
    reasons: Counter = Counter()
    repos_by_reason: dict[str, set] = {}
    for result in results:
        for unit in (result["map"] or {}).get("units", []):
            if unit["level"] in ("broken", "recheck"):
                reasons[unit["reason"]] += 1
                repos_by_reason.setdefault(unit["reason"], set()).add(result["row"]["repo"])
    lines += ["", "## Why sections were flagged", "", "| Reason | Sections | Repositories |", "|---|---|---|"]
    for reason, count in reasons.most_common():
        lines.append(f"| {REASONS.get(reason, reason)} | {count} | {len(repos_by_reason[reason])} |")
    links = [link for result in results for link in result["links"]]
    by_status = Counter(link["status"].split(":")[0] for link in links)
    by_type = Counter(link["type"] for link in links)
    lines += ["", "## Links section → code", "",
              f"{len(links)} links found; by type: " + ", ".join(f"{t} {n}" for t, n in by_type.most_common()) + ".",
              "By status: " + ", ".join(f"{s} {n}" for s, n in by_status.most_common()) + ".",
              f"`label.csv` holds a random sample of {labels} for hand labelling; score it with "
              "`okf scan --score label.csv`."]
    if skipped:
        lines += ["", "## Skipped", "", "| Repository | Reason |", "|---|---|"]
        lines += [f"| {r['repo']} | {r['reason']} |" for r in skipped]
    lines += ["", "To reproduce: `okf scan --repos repos.pinned.txt --now "
              f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')} --seed {seed}`.", ""]
    return "\n".join(lines)


REASONS = {
    "broken:path": "broken: a path that does not exist",
    "broken:script": "broken: a script or test file a command runs does not exist",
    "broken:npm-script": "broken: no such script in package.json",
    "broken:make": "broken: no such make target",
    "broken:just": "broken: no such just recipe",
    "broken:glob": "broken: a glob matches no files",
    "broken:source": "broken: an OKF source does not exist",
    "recheck:moved": "recheck: a mentioned file moved",
    "recheck:code-changed": "recheck: code changed after the section was verified or last edited",
    "recheck:edited": "recheck: section edited after it was verified",
    "recheck:regenerated": "recheck: OKF content regenerated after verification",
    "recheck:stale-after": "recheck: OKF stale_after has passed",
    "recheck:in-change": "recheck: code changed in this change",
}


def sample_links(results: list[dict], size: int, seed: int) -> list[dict]:
    """A reproducible random sample of section → source links; sorted for labelling."""
    links = [link for result in results for link in result["links"]]
    chosen = random.Random(seed).sample(links, min(size, len(links)))
    return sorted(chosen, key=lambda link: (link["repo"], link["file"], int(link["line"])))


# --- Scoring the labels ----------------------------------------------------------


def score(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "correct" not in rows[0]:
        raise ScanError(f"{path} has no `correct` column")
    groups: dict[str, Counter] = {"all": Counter()}
    for row in rows:
        verdict = _verdict(row.get("correct", ""))
        for group in ("all", row.get("type") or "?"):
            groups.setdefault(group, Counter())[verdict] += 1
    lines = [f"okf scan --score {path.name}: {len(rows)} links", "",
             "| Type | Labelled | Yes | No | Unclear | Precision (yes / labelled) | Excluding unclear |",
             "|---|---|---|---|---|---|---|"]
    for group in ["all", *sorted(g for g in groups if g != "all")]:
        c = groups[group]
        labelled = c["yes"] + c["no"] + c["unclear"]
        precise = f"{100 * c['yes'] / labelled:.1f}%" if labelled else "—"
        strict = f"{100 * c['yes'] / (c['yes'] + c['no']):.1f}%" if c["yes"] + c["no"] else "—"
        lines.append(f"| {group} | {labelled} of {sum(c.values())} | {c['yes']} | {c['no']} | {c['unclear']} | "
                     f"{precise} | {strict} |")
    unknown = groups["all"]["other"]
    if unknown:
        lines += ["", f"{unknown} rows have a value in `correct` that is not yes/no/unclear (да/нет/неясно)."]
    return "\n".join(lines) + "\n"


def _verdict(value: str) -> str:
    text = value.strip().lower()
    if not text:
        return "empty"
    if text in YES:
        return "yes"
    if text in NO:
        return "no"
    if text in UNCLEAR:
        return "unclear"
    return "other"


# --- Finding repositories --------------------------------------------------------


def find_repos(count: int, months: int = 3, log: Callable[[str], None] = lambda _: None) -> list[str]:
    """Public, not archived, not fork repositories with AGENTS.md or CLAUDE.md, pushed in the last `months`.

    Uses GitHub code search through `gh api`, so `gh` must be installed and signed in (`gh auth login`).
    """
    if shutil.which("gh") is None or subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        raise ScanError("finding repositories needs the GitHub CLI signed in (gh auth login); "
                        "or write repos.txt by hand, one owner/repo per line")
    since = datetime.now(timezone.utc) - timedelta(days=30 * months)
    candidates: list[str] = []
    for filename in ("AGENTS.md", "CLAUDE.md"):
        for page in range(1, 11):
            output = _gh(["api", "-X", "GET", "search/code", "-f", f"q=filename:{filename}", "-f", "per_page=100",
                          "-f", f"page={page}", "--jq", ".items[] | [.repository.full_name, .repository.fork] | @tsv"])
            names = [line.split("\t") for line in output.splitlines() if line.strip()]
            new = [name for name, fork in names if fork != "true" and name not in candidates]
            candidates.extend(dict.fromkeys(new))
            log(f"okf scan --find: {filename} page {page}: {len(candidates)} candidates")
            if not names or len(candidates) >= count * 4:
                break
            time.sleep(6)  # code search allows about 10 requests a minute
    found = []
    for name in candidates:
        info = _gh(["api", f"repos/{name}", "--jq", "[.archived, .private, .fork, .pushed_at] | @tsv"]).split("\t")
        if len(info) == 4 and info[:3] == ["false", "false", "false"]:
            pushed = datetime.fromisoformat(info[3].strip().replace("Z", "+00:00"))
            if pushed >= since:
                found.append(name)
                log(f"okf scan --find: {len(found)}/{count} {name}")
        if len(found) >= count:
            break
    return found


def _gh(args: list[str]) -> str:
    for attempt in range(3):
        result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0:
            return result.stdout
        if "rate limit" in result.stderr.lower() and attempt < 2:
            time.sleep(30)
            continue
        return ""
    return ""


# --- Helpers ------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")
    return result.stdout.strip()


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:  # the BOM lets Excel read UTF-8
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _remove(directory: Path) -> None:
    def writable(function, path, _):  # git marks pack files read-only, which Windows refuses to delete
        os.chmod(path, stat.S_IWRITE)
        function(path)

    if sys.version_info >= (3, 12):
        shutil.rmtree(directory, onexc=writable)
    else:
        shutil.rmtree(directory, onerror=writable)
