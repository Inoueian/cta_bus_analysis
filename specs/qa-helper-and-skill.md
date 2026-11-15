# Spec: Shared QA helper (`cta/qa.py`) and the `/qa` skill

Status: draft
Owner: Satoru  ·  Date: 2026-11-15  ·  TODO item: Foundation — "`/qa` skill (`.claude/skills/qa/`): run an adapter on its committed fixture, print the per-stage QA table (rows in, rows out, reason counts) and diff it against the table recorded in the latest `docs/*-qa.md`, so Rule 2 (no silent threshold or exclusion change) is a command rather than a convention. Needs a shared QA-row helper first: `cta.archive._record_qa` and `cta.mansueto.qa_rows` are two copies of the same additivity check. Spec: to write (the helper is a small API decision)."
Tags: `kind:spec source:archive source:mansueto stage:qa topic:qa-table`

## Question

When a threshold or exclusion changes, does anyone see the QA table move? Today the answer rests on a
reviewer comparing numbers by eye with a `docs/*-qa.md` note (Rule 2, Rule 7). This spec makes it one
command and one test: each adapter's QA table on its committed fixture is compared with a committed
baseline, and a difference fails. Now, because Phase 1 has just added a third copy of the QA arithmetic
(`scripts/route_run_level.py` `stage_totals`, after `cta.mansueto.qa_rows` and `cta.archive._record_qa`)
and the stop-level view will add stages of its own.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| QA row builders | `cta/mansueto.py` `qa_rows`; `cta/archive.py` `_record_qa` | `QA_COLUMNS` = `stage, rows_in, rows_out, reason, count` in both | same additivity check twice; importers of `mansueto.qa_rows`: `cta/calendar.py`, `cta/michigan_ave_segment.py`, `cta/dlsd_run_quality.py` |
| QA summing | `scripts/route_run_level.py` `stage_totals`; notebook copy `stage_table` in `notebooks/eda_routes_8_65_66.ipynb` | per-call QA table | third and fourth copies |
| Adapters | `cta.views.run_level_from_archive` + `cta.archive.qa`; `run_level_from_mansueto_with_qa`; `run_level_from_mansueto_raw_with_qa` | QA tables keyed by day or pid | called exactly as `tests/test_views_*.py` call them |
| Recorded tables | `docs/2026-11-03-archive-adapter-qa.md`, `docs/2026-11-04-mansueto-adapter-qa.md`; the raw adapter's table is only in its TODO.md Done line (2026-11-11) | markdown and prose, each laid out differently | human record; not parsed (Method 4) |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| QA columns | `cta.qa.QA_COLUMNS` | `["stage", "rows_in", "rows_out", "reason", "count"]` | — |
| Row builder | `cta.qa.qa_rows(stage, rows_in, rows_out, reasons) -> list[dict]` | keys = `QA_COLUMNS`; `rows_in`, `rows_out`, `count` int; `reason` str or None | one row per non-zero reason, one `None` row when nothing dropped |
| Summing | `cta.qa.stage_totals(qa, by, call_keys) -> DataFrame` | index `by + ["stage"]`; `rows_in`, `rows_out` int64, one int64 column per reason | one row per (group, stage) |
| Fixture cases | `cta.qa.FIXTURE_CASES` (dict name → callable) and `cta.qa.fixture_qa(name) -> DataFrame` | `case` str, `key` str (the pid or day), then `QA_COLUMNS`; `reason` is `""` when None | one row per (case, key, stage, reason) |
| Diff | `cta.qa.diff_qa(observed, baseline) -> DataFrame` | `case, key, stage, reason, field, baseline, observed`; `field` ∈ `rows_in, rows_out, count, missing_row, new_row` | one row per differing cell; empty when equal |
| Baseline | `tests/fixtures/qa_baseline.csv` | columns of `fixture_qa` | all cases in `FIXTURE_CASES` order; 4 cases, 25 rows (Method 5) |
| CLI | `scripts/qa.py [case ...] [--record]` | prints each case's table and the diff; exit 1 on any difference | thin: argparse + `cta.qa` |
| Skill | `.claude/skills/qa/SKILL.md` | procedure text (shape: `.claude/skills/fixture/SKILL.md`) | — |

## Method

Prior art to copy: `cta/mansueto.py` `qa_rows` (the builder, unchanged); `scripts/route_run_level.py`
`stage_totals` (the summing); `tests/test_mansueto.py` additivity test; `tests/test_views_archive.py`
`ingested_con` for how the archive case ingests its fixture. Playbook pattern "Emit a QA table from a
pipeline stage".

Preparatory refactor: `cta.mansueto.qa_rows` and `QA_COLUMNS` move to `cta/qa.py` and `cta.mansueto`
re-exports both names (three modules import them from there); `cta.archive.QA_COLUMNS` becomes the same
object; `cta.archive._record_qa` builds its rows with `cta.qa.qa_rows` and then inserts them;
`scripts/route_run_level.py` `stage_totals` moves to `cta.qa.stage_totals` and the script imports it. No
QA table or view changes on any fixture and no test assertion is edited (Rule 7). One error path differs:
`_record_qa` today inserts rows and then raises on a failed additivity check; after the move it raises
first and inserts nothing.

1. `cta/qa.py` imports nothing from `cta` at module level (every source module imports it); the adapter
   imports it needs for `FIXTURE_CASES` are inside the case functions.
2. `FIXTURE_CASES` has four cases, each returning the QA table its adapter produces on a committed fixture:
   `archive` (`archive_2026-10-29_michigan.ndjson.gz`, the 45 kept pids, key = day), `mansueto_route3`
   (pids 18414, 18415 on `mansueto_2026-07-27_route3.parquet`, key = pid), `mansueto_6410` (PID 6410 on
   `mansueto_6410_last30d.parquet`, key = pid) and `mansueto_raw` (`mansueto_raw_2026-10-22_michigan.csv.gz`,
   the 45 kept pids, key = day). Patterns come from `tests/fixtures/getpatterns/`. A new adapter adds a case.
3. `fixture_qa(name)` runs one case and normalises: identifiers and `key` as strings, `reason` None → `""`,
   integer counts, rows in the adapter's own order. It never touches the network or `data/` (Rules 3, 4).
4. The baseline is a committed CSV, not the markdown notes: the notes lay their tables out
   differently (blank continuation cells, an em dash for no reason, a pid column or none), so parsing them
   would be a second thing to keep right. The `docs/*-qa.md` note stays the human record with the reasoning;
   the CSV is what the machine compares. The skill tells the author to update both together.
5. `scripts/qa.py` prints every requested case (default all), then `diff_qa` against the baseline; exit 0
   when empty, 1 otherwise. `--record` rewrites `qa_baseline.csv` from the observed tables and prints the
   diff it is accepting; it is the only writer of that file.
6. `.claude/skills/qa/SKILL.md`: run `python scripts/qa.py`; if the diff is empty say so and stop; if not,
   name the stage and reason that moved and stop unless a spec covers the change (Rule 2); with a spec,
   `--record`, add the new table to a dated `docs/*-qa.md` note via `/finding`, and report both. `/implement`
   calls it after pytest.

## Thresholds and exclusions

None. The comparison is exact: a QA count is an integer and any difference is a behaviour change.

## Fixtures

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/archive_2026-10-29_michigan.ndjson.gz` | existing | | | |
| `tests/fixtures/mansueto_2026-07-27_route3.parquet`, `mansueto_6410_last30d.parquet` | existing | | | |
| `tests/fixtures/mansueto_raw_2026-10-22_michigan.csv.gz` | existing | | | |
| `tests/fixtures/qa_baseline.csv` | not a public file: written by `scripts/qa.py --record` from the fixtures above | all four cases | 25 rows; about 1.5 kB (estimate; measure, then pin) | `scripts/qa.py --record` |

## Acceptance tests

All in `tests/test_qa.py` unless named; offline. Counts below were measured on the committed fixtures on
2026-11-15.

- [ ] `test_qa_rows_known_case`: `qa_rows("s", 10, 7, {"a": 2, "b": 1, "c": 0})` returns two rows (`a` 2, `b` 1) with `rows_in` 10 and `rows_out` 7; `qa_rows("s", 5, 5, {})` returns one row with `reason` None and `count` 0; `qa_rows("s", 10, 7, {"a": 2})` raises `AssertionError`.
- [ ] `test_old_names_are_the_shared_helper`: `cta.mansueto.qa_rows is cta.qa.qa_rows`, and `cta.mansueto.QA_COLUMNS`, `cta.archive.QA_COLUMNS` and `cta.qa.QA_COLUMNS` are equal.
- [ ] `test_fixture_qa_archive`: `fixture_qa("archive")` on `archive_2026-10-29_michigan.ndjson.gz` has 7 rows: `ingest` 118,995 → 118,995; `clean` → 118,014 (`duplicate_fix` 981); `pairs` 116,432 → 115,898 (`gap_over_max` 355, `backward_pdist` 117, `geometry_unsupported` 61, `speed_over_max` 1); `impute` 103,379 → 103,364 (`later_crossing` 15).
- [ ] `test_fixture_qa_mansueto`: `mansueto_route3` has 8 rows with `pattern_join` dropping 108 (`18414`) and 113 (`18415`) as `stop_not_in_pattern` and final `rows_out` 11,337 and 12,330; `mansueto_6410` has 4 rows, 4,730 in and out at every stage.
- [ ] `test_fixture_qa_mansueto_raw`: on `mansueto_raw_2026-10-22_michigan.csv.gz`, 6 rows: `read` 23,453; `clean` → 23,393 (`duplicate_fix` 60); `pairs` 21,834 → 21,696 (`gap_over_max` 85, `backward_pdist` 30, `geometry_unsupported` 23); `impute` 97,668 → 97,663 (`later_crossing` 5).
- [ ] `test_baseline_matches_fixtures`: for every case in `FIXTURE_CASES`, `diff_qa(fixture_qa(case), baseline)` is empty, and per (case, key, stage) `count` sums to `rows_in − rows_out` (the QA-table case). This is the test that fails when a threshold moves.
- [ ] `test_diff_qa_reports_each_kind`: on a hand-built pair, one changed `count`, one row only in the baseline and one only in the observed table give three diff rows with `field` `count`, `missing_row`, `new_row`.
- [ ] `test_script_exit_codes` (`tests/test_qa_script.py`): `scripts.qa.main([])` returns 0 on the committed baseline; with a baseline copy in `tmp_path` whose one `count` is edited it returns 1 and prints that stage and reason; `--record` to a `tmp_path` baseline reproduces the committed file byte for byte.

## Out of scope

- Changing any threshold, reason name, stage name or QA number. If a number moves during the refactor, stop.
- Downstream QA stages (`corridor`, `hops` in `cta.michigan_ave_segment`; `endpoints` in
  `cta.dlsd_run_quality`; `coverage` in `cta.calendar`): they keep calling `qa_rows` through its old name
  and get no fixture case here.
- Real-data QA (`data/route_run_level/qa_*.csv`, `docs/2026-11-15-routes-8-65-66-run-level-qa.md`): not a
  fixture, so not a baseline. `/qa` compares fixtures only.
- Parsing or rewriting the tables in existing `docs/*-qa.md` notes; editing the notebook's `stage_table`.
- Replacing the DuckDB `archive_qa` table with in-memory QA, or changing what `archive.qa` returns.

## Open questions

1. Baseline as a committed CSV (`tests/fixtures/qa_baseline.csv`) rather than the markdown tables the TODO
   item names: accepted? The alternative is a parser per note layout.
2. `cta/qa.py` is a new module on the `cta/` import surface (ADR-005 lists one module per source, the views,
   the calendar and the migrated helpers). Is a line in CLAUDE.md's Layout paragraph enough, or does it want
   an ADR?
3. Should the downstream stages (`corridor`, `hops`, `endpoints`, `coverage`) get fixture cases in a
   follow-up, or stay covered by their own tests only?
4. Should `test_baseline_matches_fixtures` be the enforcement (CI fails on any QA change), with `/qa` as the
   way to read and accept the diff? The TODO item asks only for the command.
