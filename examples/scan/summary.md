# okf scan: 50 repositories

Scanned 2026-10-22 16:27 UTC in 4.4 min; label sample seed 42.
Each repository was cloned with full history (`git clone --filter=blob:none`), mapped with `okf trust`, then deleted. Nothing was written to the repositories.

## Results

| | Repositories |
|---|---|
| processed | 49 |
| skipped | 1 |
| with ≥1 section to recheck | 24 of 49 (49%) |
| with ≥1 broken reference | 17 of 49 (35%) |
| with ≥1 finding of any kind (the "wow" moment) | 29 of 49 (59%) |
| … of those with agent instructions | 29 of 49 (59%) |
| without agent instructions | 0 of 49 (0%) |
| with both AGENTS.md and CLAUDE.md | 18 of 49 (37%) |
| shallow history (dates unknown) | 0 of 49 (0%) |

## Sections per repository

Median 7, mean 9.0, max 31.

| Sections | Repositories |
|---|---|
| 0 | 0 |
| 1–5 | 18 |
| 6–10 | 16 |
| 11–20 | 11 |
| 21–50 | 4 |
| more than 50 | 0 |

## Why sections were flagged

| Reason | Sections | Repositories |
|---|---|---|
| recheck: code changed after the section was verified or last edited | 47 | 24 |
| broken: a path that does not exist | 20 | 14 |
| broken: a glob matches no files | 3 | 3 |
| broken: no such script in package.json | 2 | 1 |

## Links section → code

1010 links found; by type: path 803, script 69, make 60, npm-script 57, glob 21.
By status: ok 873, unknown 60, unclear 46, broken 31.
`label.csv` holds a random sample of 100 for hand labelling; score it with `okf scan --score label.csv`.

## Skipped

| Repository | Reason |
|---|---|
| caretive-ai/project-careti | clone failed: fatal: active `post-checkout` hook found during `git clone`: |

To reproduce: `okf scan --repos repos.pinned.txt --now 2026-10-22T16:27:36Z --seed 42`.
