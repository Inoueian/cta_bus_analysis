# Spec: The `/qa` skill: fixture QA tables against a committed baseline

Status: draft
Owner: Satoru  ·  Date: 2026-11-16  ·  TODO item: Foundation — "`/qa` skill (`.claude/skills/qa/`): run an adapter on its committed fixture, print the per-stage QA table (rows in, rows out, reason counts) and diff it against the table recorded in the latest `docs/*-qa.md`, so Rule 2 (no silent threshold or exclusion change) is a command rather than a convention. The baseline is a committed CSV (`tests/fixtures/qa_baseline.csv`), not the markdown tables, which stay the human record, and a test on it fails CI on any QA change until `scripts/qa.py --record` (owner, 2026-11-16). After the shared QA-row helper (item above). Spec: specs/qa-skill.md (draft)."
Tags: `kind:spec source:archive source:mansueto stage:qa topic:qa-table`

## Question

When a threshold or exclusion changes, does anyone see the QA table move? Today the answer rests on a
reviewer comparing numbers by eye with a `docs/*-qa.md` note (Rule 2, Rule 7). This spec makes it one
command and one test: each adapter's QA table on its committed fixture is compared with a committed
baseline, and a difference fails. Now, because the stop-level view is about to add stages of its own.
Waits for `specs/qa-helper.md` (`cta/qa.py`).

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Shared helper | `cta/qa.py` `QA_COLUMNS` | `stage, rows_in, rows_out, reason, count` | from `specs/qa-helper.md` |
| Adapters | `cta.views.run_level_from_archive` + `cta.archive.qa`; `run_level_from_mansueto_with_qa`; `run_level_from_mansueto_raw_with_qa` | QA tables keyed by day or pid | called exactly as `tests/test_views_*.py` call them |
| Pid list, patterns | `notebooks/michigan_ave_kept_pids.json` (45 pids); `tests/fixtures/getpatterns/` | — | patterns read from the fixture directory, passed explicitly |
| Recorded tables | `docs/2026-11-03-archive-adapter-qa.md`, `docs/2026-11-04-mansueto-adapter-qa.md`; the raw adapter's table is only in its TODO.md Done line (2026-11-11) | markdown and prose, each laid out differently | human record; not parsed (Method 3) |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Fixture cases | `cta.qa_baseline.FIXTURE_CASES` (dict name → callable), `fixture_qa(name) -> DataFrame` | `case` str, `key` str (the pid or day), then `QA_COLUMNS`; `reason` is `""` when None; `rows_in`, `rows_out`, `count` int64 | one row per (case, key, stage, reason) |
| Diff | `cta.qa_baseline.diff_qa(observed, baseline) -> DataFrame` | `case, key, stage, reason, field, baseline, observed`; `field` ∈ `rows_in, rows_out, count, missing_row, new_row` | one row per differing cell; empty when equal. It compares exactly the rows it is given: callers filter the baseline by case |
| Baseline I/O | `cta.qa_baseline.BASELINE_PATH`, `read_baseline(path)`, `write_baseline(df, path)` | columns of `fixture_qa`; CSV, `\n` line ends; read with `case`, `key`, `stage`, `reason` as str and `keep_default_na=False`, counts int64 | — |
| Baseline | `tests/fixtures/qa_baseline.csv` | columns of `fixture_qa` | 4 cases in `FIXTURE_CASES` order, 25 rows |
| CLI | `scripts/qa.py [case ...] [--baseline PATH] [--record]`; `main(argv=None) -> int` | prints each case's table and the diff; returns 1 on any difference, else 0 | thin: argparse + `cta.qa_baseline` |
| Skill | `.claude/skills/qa/SKILL.md` | procedure text (shape: `.claude/skills/fixture/SKILL.md`) | — |
| Prose | `.claude/skills/implement/SKILL.md` (one step: run `/qa` after pytest); `.claude/skills/fixture/SKILL.md` (one step: run `/qa` after a rebuild, Method 5); `CLAUDE.md` Commands (`python scripts/qa.py`) and Layout; `cta/__init__.py` module list; a playbook pattern "Check a QA table against the baseline" via `/finding` | — | — |

## Method

Prior art to copy: `tests/test_views_archive.py` `ingested_con` and `run_level`, `tests/test_views_mansueto.py`
`one_day`, `tests/test_views_mansueto_raw.py` `view_and_qa` (how each case runs its adapter);
`scripts/archive_run_level.py` (CLI shape); `.claude/skills/fixture/SKILL.md` (skill shape).

1. The cases live in their own module, `cta/qa_baseline.py`, so that `cta/qa.py` stays free of `cta` imports.
   Its docstring says it is a development tool tied to the repo checkout (it reads `tests/fixtures/`).
   `FIXTURE_CASES` has four, each returning the QA table its adapter produces on a committed fixture:
   `archive` (`archive_2026-10-29_michigan.ndjson.gz` with its committed `.index.json`, the 45 kept pids,
   key = day), `mansueto_route3` (pids 18414, 18415 on `mansueto_2026-07-27_route3.parquet`, key = pid),
   `mansueto_6410` (PID 6410 on `mansueto_6410_last30d.parquet`, key = pid) and `mansueto_raw`
   (`mansueto_raw_2026-10-22_michigan.csv.gz`, the 45 kept pids, key = day). A new adapter adds a case.
2. `fixture_qa(name)` runs one case and normalises: `key` as a string (gotcha "Identifiers arrive as
   `6410.0`"), `reason` None → `""`, integer counts, rows in the adapter's own order. It never touches the
   network or `data/` (Rules 3, 4): patterns come from `tests/fixtures/getpatterns/` by explicit directory,
   never the local cache (gotcha "PID 6402's hand trim exists only in a local cache file"), and the archive
   case reads the v1 fixture index (gotcha "Archive `index.json` has no `days` key"). The archive and raw
   cases each open their own connection (`cta.mansueto_raw.check_db` refuses a shared one). The adapter gotchas
   for both sources are handled inside the adapters, which the cases call unchanged. `fixture_qa` caches its
   result per case for the session (`functools.lru_cache`, returning a copy), so the suite runs each case once.
   `read_baseline` reads keys and reasons as strings with `keep_default_na=False`: by default pandas would read
   key `6410` as an integer and reason `""` as NaN.
3. The baseline is a committed CSV, not the markdown notes, whose tables are laid out differently (Inputs);
   the `docs/*-qa.md` note stays the human record with the reasoning.
4. `scripts/qa.py` prints every requested case (default all), then `diff_qa` against the rows of `--baseline`
   (default `BASELINE_PATH`) for those cases only. `--record` replaces only the requested cases' rows in that
   file, keeping the others and `FIXTURE_CASES` order, and prints the diff it is accepting; it is the only
   writer of the committed file. With no case named it rewrites the whole file, which drops rows of a case no
   longer in `FIXTURE_CASES`; a missing baseline file counts as empty.
5. The baseline is a fixture, not a test assertion. `--record` is how it moves, in three cases only: (a) a
   spec whose Thresholds table names a threshold or exclusion change (Rule 2); (b) `/fixture` rebuilt a
   fixture a case reads; (c) a case is added. In (b) and (c) the report shows the accepted diff and the rows
   of every other case do not move. A refactor never records (Rule 7). The counts are pinned in the CSV alone:
   no test in this spec hard-codes them.
6. First baseline: the implementer records it once and compares it with the table under Fixtures, row by
   row, in the report. Any difference means the helper refactor or a fixture moved: stop and report.
7. `.claude/skills/qa/SKILL.md`: run `python scripts/qa.py`; if the diff is empty say so and stop; if not,
   name the stage and reason that moved and stop unless one of Method 5's three cases applies; if one does,
   `--record`, add the new table to a dated `docs/*-qa.md` note via `/finding`, and report both.

## Thresholds and exclusions

None. The comparison is exact: a QA count is an integer and any difference is a behaviour change.

## Fixtures

Existing, read only: `tests/fixtures/archive_2026-10-29_michigan.ndjson.gz` and `.index.json`,
`mansueto_2026-07-27_route3.parquet`, `mansueto_6410_last30d.parquet`,
`mansueto_raw_2026-10-22_michigan.csv.gz`, `getpatterns/`.

New: `tests/fixtures/qa_baseline.csv`, not cut from a public file but written by `scripts/qa.py --record`;
25 rows, about 1.5 kB (estimate; measure, then pin). Its first content, measured 2026-11-15 and again
2026-11-16 (requirements, Method 6):

| Case (rows) | Stages: rows in → rows out (reason count) |
|---|---|
| `archive` (7) | `ingest` 118,995 → 118,995; `clean` 118,995 → 118,014 (`duplicate_fix` 981); `pairs` 116,432 → 115,898 (`gap_over_max` 355, `backward_pdist` 117, `geometry_unsupported` 61, `speed_over_max` 1); `impute` 103,379 → 103,364 (`later_crossing` 15) |
| `mansueto_route3` (8) | `18414`: `read`, `dedup` 11,445 → 11,445; `pattern_join` → 11,337 (`stop_not_in_pattern` 108); `order` 11,337 → 11,337. `18415`: 12,443 → 12,443; `pattern_join` → 12,330 (`stop_not_in_pattern` 113); `order` 12,330 → 12,330 |
| `mansueto_6410` (4) | `read`, `dedup`, `pattern_join`, `order`: 4,730 → 4,730 each |
| `mansueto_raw` (6) | `read` 23,453 → 23,453; `clean` → 23,393 (`duplicate_fix` 60); `pairs` 21,834 → 21,696 (`gap_over_max` 85, `backward_pdist` 30, `geometry_unsupported` 23); `impute` 97,668 → 97,663 (`later_crossing` 5) |

## Acceptance tests

In `tests/test_qa_baseline.py` unless named; offline, with the network refused as in `tests/test_views_*.py`.

- [ ] `test_fixture_qa_schema`: for each of the four cases on its fixture above, `fixture_qa(case)` has columns `["case", "key"] + QA_COLUMNS`, string `key`, no null `reason`, int64 counts, and as many rows as that case has in `read_baseline(BASELINE_PATH)`, which reads `key` `6410` as the string `"6410"` and reason `""` as `""`.
- [ ] `test_baseline_matches_fixtures` (the QA-table case): on `tests/fixtures/qa_baseline.csv`, the baseline's set of cases equals `FIXTURE_CASES`; for every case `diff_qa(fixture_qa(case), baseline rows of that case)` is empty; and per (case, key, stage) `count` sums to `rows_in − rows_out`. This is the test that fails when a threshold moves.
- [ ] `test_diff_qa_reports_each_kind`: hand-built pair. One changed `count`, one row only in the baseline and one only in the observed table give three diff rows with `field` `count`, `missing_row`, `new_row`; equal tables in a different row order give none.
- [ ] `test_script_exit_codes` (`tests/test_qa_script.py`): `scripts.qa.main(["mansueto_6410"])` returns 0 on the committed baseline and reports no row of another case as missing; `main(["mansueto_6410", "--baseline", p])` with `p` a `tmp_path` copy whose one `mansueto_6410` `count` is edited returns 1 and prints that case, stage and reason.
- [ ] `test_record_reproduces_baseline` (`tests/test_qa_script.py`): `main(["--record", "--baseline", p])` with `p` in `tmp_path` writes a file byte for byte equal to `tests/fixtures/qa_baseline.csv`, and the committed file's modification time is unchanged; `main(["mansueto_6410", "--record", "--baseline", q])`, `q` a `tmp_path` copy, leaves `q` byte for byte equal too (the other cases' rows are kept); and `--record` to a path that does not exist yet writes the same bytes.

## Out of scope

- Changing any threshold, reason name, stage name or QA number.
- Hard-coding the baseline's counts in a test (Method 5), or editing the counts existing tests assert.
- Downstream QA stages (`corridor`, `hops` in `cta.michigan_ave_segment`; `endpoints` in
  `cta.dlsd_run_quality`; `coverage` in `cta.calendar`): no fixture case here; a follow-up TODO item.
- Real-data QA (`data/route_run_level/qa_*.csv`, `docs/2026-11-15-routes-8-65-66-run-level-qa.md`): not a
  fixture, so not a baseline. `/qa` compares fixtures only.
- Parsing or rewriting the tables in existing `docs/*-qa.md` notes.
- The archive v2 manifest and parquet day files (Foundation, first item): the `archive` case reads the
  committed v1 fixture. If that spec replaces the fixture, it re-records the baseline and says so; the two
  can land in either order.

## Open questions

All resolved by the owner on 2026-11-16: the baseline is a committed CSV (Method 3); the downstream stages
get fixture cases in a follow-up (TODO.md Foundation); `test_baseline_matches_fixtures` is the enforcement
(Method 5).
