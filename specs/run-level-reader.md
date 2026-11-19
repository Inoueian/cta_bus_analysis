# Spec: Run-level reader: one source per route and service date

Status: draft
Owner: Satoru  ·  Date: 2026-11-19  ·  TODO item: Phase 1, Now — "Run-level reader: one source per route and service date ([ADR-011](DECISIONS.md), Proposed): `cta.calendar.primary_source` picks the first of archive, raw CSVs, Mansueto parquet whose declared coverage holds the date …" (full text in TODO.md)
Tags: `kind:spec source:archive source:mansueto stage:view topic:calendar`

## Question

Analyses of routes 8, 65 and 66 read run-level views from up to three sources whose coverage overlaps: the archive and
the raw CSVs both cover 25 days, 2026-09-28 to 2026-10-27 less the five raw days missing. Reading the source folders
together puts every bus in twice on those days: headways about halve and run counts double. The owner decided on
2026-11-19 that the archive wins wherever it covers a date (60 s fixes against 300 s; ADR-009 already makes it the
primary source), so which source to read on a date is a calendar fact. This spec puts that fact in `cta/calendar.py`,
gives analyses one reader that applies it, and names the stop key the wait-time spec groups by (ADR-011).

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Run-level views on disk | `data/route_run_level/source=<s>/**/*.parquet` (`scripts/route_run_level.py`: `source=mansueto/pid=<pid>/year=<YYYY>.parquet`, `source=mansueto_raw/<day>.parquet`; the archive half sets its own layout under `source=archive/`) | `cta.views.RUN_LEVEL_COLUMNS` | per-source views keep overlap days for the cross-source checks |
| Declared coverage | `cta.calendar._window` / `_coverage_reason` (`specs/calendar-module.md`) | first day, last day, missing days per source | the archive's last day and whole-day gaps need its index |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Priority | `cta.calendar.SOURCE_PRIORITY = (SOURCE_ARCHIVE, SOURCE_MANSUETO_RAW, SOURCE_MANSUETO)` | tuple of str | — |
| Primary source | `cta.calendar.primary_source(service_dates, *, index=None) -> Series` | str, or None where no source's declared coverage holds the date | one per input date |
| Rule on a frame | `cta.views.one_source_per_day(view, *, index=None) -> (DataFrame, DataFrame)` | `RUN_LEVEL_COLUMNS` and dtypes unchanged, order kept. QA: `["route"] + cta.qa.QA_COLUMNS`, one stage `primary_source` | one row per kept (run, stop) |
| Reader | `cta.views.read_run_level(root, *, routes=None, start=None, end=None, index=None) -> (DataFrame, DataFrame)` | as `one_source_per_day`, sorted as the run-level view | as above |
| Stop key | `cta.views.STOP_KEY = ["route", "direction", "stop_id"]` | — | ADR-011's definition of the stop-level view |
| Docs | `cta/__init__.py` `views` and `calendar` lines; once ADR-011 is Accepted, README "Data Model" and CLAUDE.md's data-source paragraph | — | — |

## Method

Prior art to copy: `cta/calendar.py` `coverage_days` (declared coverage per date, with a QA stage);
`cta/views.py` `mansueto_view_from_trips` (a view and a per-key QA table out); `tests/test_calendar.py`
`test_archive_coverage_from_index` (a hand-built index).

1. `primary_source`: the first source in `SOURCE_PRIORITY` whose `_coverage_reason(source, date, index)` is empty.
   So: Mansueto parquet through 2026-07-27; none from 2026-07-28 to 2026-08-12; raw CSVs from 2026-08-13 to
   2026-09-27; the archive from 2026-09-28 (open-ended without an index; with one, through its last day, and a
   whole-day archive gap falls back to the raw CSVs where they cover it). The rule uses declared coverage, not what
   happens to be loaded, so the same date always maps to the same source.
2. `one_source_per_day` keeps a row when its `source` is the primary source of its `service_date`. A dropped row
   gets one reason: `no_declared_source` (no source covers the date: rows flagged `coverage_gap` by their adapter);
   `primary_source_absent` (the primary source has no rows for that route and date, so an ingestion hole shows
   instead of being filled); otherwise `not_primary_source`. Reasons sum to `rows_in − rows_out` per route.
3. `read_run_level` reads `root/source=*/**/*.parquet` with DuckDB (CLAUDE.md: over ~1M rows), pushes the
   `routes` and `start`/`end` (service date, inclusive) filters into the scan, joins a (service_date → primary
   source) table built by `primary_source` over the dates present, and returns pandas. Its QA equals
   `one_source_per_day` on the same rows. Per-source folders stay untouched for the cross-source checks.
4. `STOP_KEY` pools every pattern of a route and direction at a stop, each arrival keeping its `pattern_id`; a stop
   in both directions is two keys, a stop on two routes one key per route (ADR-011). Nothing here groups by it.
5. Archive `known_gaps` days stay with the archive (owner, 2026-11-18): the afternoons lost 2026-10-12 to 2026-10-17
   are empty although the raw CSVs have four of those days. `calendar_flag` carries `known_gap_day`; consumers must
   not take a headway across a gap.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `SOURCE_PRIORITY` | `("archive", "mansueto_raw", "mansueto")` | ADR-009: the archive is primary, the raw CSVs fill the hole; 60 s fixes against 300 s; owner 2026-11-19 | swapping the first two changes the 25 overlap days only |

New exclusions: `not_primary_source`, `primary_source_absent`, `no_declared_source` (Rule 2; this spec and its QA table).

## Fixtures

None new: hand-built frames and parquet files written under `tmp_path`; a hand-built archive index as in
`tests/test_calendar.py`. Real overlap days arrive with the archive half of the run-level view.

## Acceptance tests

`tests/test_run_level_reader.py`.

- [ ] `test_primary_source_dates`: without an index, 2026-07-27 → `mansueto`; 2026-07-28 and 2026-08-12 → None;
      2026-08-13 and 2026-09-27 → `mansueto_raw`; 2026-09-28, 2026-09-30 (raw file missing) and 2026-11-13 →
      `archive`. With a hand-built index listing 2026-09-28 to 2026-11-12 except 2026-10-05: 2026-10-05 →
      `mansueto_raw`, 2026-11-13 → None.
- [ ] `test_one_source_per_day_hand_built_qa`: rows (columns exactly `RUN_LEVEL_COLUMNS`) for 2026-10-01 from `archive`
      and `mansueto_raw` on route `r1` → the raw rows are `not_primary_source`; `mansueto_raw` only on route `r2` that
      day → `primary_source_absent`; `mansueto_raw` on 2026-09-20 → kept; `mansueto` on 2026-07-28 →
      `no_declared_source`. The output never holds two sources for one (`route`, `service_date`); dtypes unchanged, a
      `mansueto` row's NaN `bracket_gap_s` still NaN; reasons sum to `rows_in − rows_out` per route.
- [ ] `test_read_run_level_layout`: under `tmp_path`, parquet files in the script's layout for `mansueto` (one pid,
      one year), `mansueto_raw` (two days) and `archive` (one day overlapping a raw day): `read_run_level` equals
      `one_source_per_day` on the concatenated files, `routes` and `start`/`end` filter, and the files are unchanged.
- [ ] `test_stop_key`: `STOP_KEY == ["route", "direction", "stop_id"]`; on a hand-built frame, grouping by it gives one
      key for a stop served by two patterns of a direction and two keys for a stop served by two routes.

## Out of scope

- The stop windows (`specs/mansueto-stop-validity.md`); building or changing any run-level view.
- Preferring the raw CSVs on archive `known_gaps` days; per-route source choice; any source other than the three.
- Waits, headways, gap handling across `known_gaps` (the wait-time spec).
- A stored combined or stop-sorted table (ADR-011: only as a cache, when a consumer measures the need).

## Open questions

1. ADR-011 is Proposed. Accept it (or say what to change) before this spec goes to `ready`.
