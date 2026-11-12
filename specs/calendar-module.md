# Spec: Calendar module (source coverage and Mansueto freshness)

Status: draft
Owner: Satoru  ·  Date: 2026-11-12  ·  TODO item (Foundation): "Calendar module (`cta/calendar.py`): CTA holidays, archive `known_gaps` windows, Mansueto freshness; one place, flag rows rather than drop them. Started 2026-11-03 with the archive adapter (six Sunday-schedule holidays, `known_gaps`, `calendar_flag`); Mansueto freshness (read `MANSUETO_DATA_EDGE` and the per-pid `trips_<pid>_full.meta.json` that `cta.mansueto.fetch_parquet` writes; the source-coverage holes belong here too: 2026-07-28 to 2026-08-12 covered by nothing, the five raw-CSV days missing between 2026-09-28 and 2026-10-27, and the raw-CSV edge 2026-10-27, per ADR-007, ADR-009 and `docs/2026-11-06-mansueto-raw-positions.md`) and the vault note migration remain. Absorbs the former "Holiday schedule filtering (cross-cutting)" item; applies retroactively to the DLSD analysis once the helpers read the run-level view (next item). Spec: to write."
Tags: `kind:spec source:mansueto source:archive stage:clean topic:calendar`

## Question

Which service dates does each source cover, and has a frozen Mansueto source moved? ADR-007 and ADR-009 require every
time series to show the 2026-07-28 to 2026-08-12 hole and the missing raw-CSV days rather than bridge them, and ADR-009
declares those gaps "in `cta/calendar.py`". Today they live in prose and in adapter comments, so a wait-time or drift
chart cannot tell "no buses" from "no data". This spec adds the two missing calendar facts (declared source coverage,
Mansueto freshness) to the module that already holds holidays and `known_gaps`. Holidays and `known_gaps` do not change.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Parquet data edge | `cta.mansueto.MANSUETO_DATA_EDGE` | `"2026-07-28"` | stays in `cta.mansueto` (ADR-007 names it there); `cta.calendar` imports it, no copy |
| Parquet download metadata | `<parquet_dir>/trips_<pid>_full.meta.json` (`cta.mansueto.write_meta`) | `pid`, `last_modified` (ISO UTC), `max_bus_stop_time` (naive Chicago wall time), `fetched_at` (ISO UTC) | written by `fetch_parquet`; read only |
| Raw-CSV download metadata | `<raw_dir>/YYYY-MM-DD.meta.json` (`cta.mansueto_raw.fetch_day`) | `url`, `last_modified`, `fetched_at`; the day is the file name | read only |
| Archive index | `index` dict (`cta.archive.fetch_index`) | `known_gaps` | as today; archive rows only |
| Coverage dates | `docs/2026-11-06-mansueto-raw-positions.md`, ADR-007, ADR-009 | see Thresholds | measured 2026-11-04 and 2026-11-06 |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Declared coverage | `cta.calendar.source_coverage() -> DataFrame` | `source` str, `first_day` str or None, `last_day` str or None (inclusive, `YYYY-MM-DD`, None = open), `missing_days` tuple of str, `evidence` str | one row per source (`mansueto`, `mansueto_raw`, `archive`) |
| Row flag | `cta.calendar.calendar_flag(service_date, *, index=None, source=None) -> Series` | str; adds `coverage_gap` after the existing parts, order `holiday:<name>;known_gap_day;coverage_gap` | one value per input row; `source=None` returns today's output unchanged |
| Date spine | `cta.calendar.coverage_days(start, end, *, sources=None, index=None) -> (DataFrame, DataFrame)` | `service_date` str, `source` str, `covered` bool, `reason` str (`""`, `before_first_day`, `after_edge`, `missing_day_file`), `calendar_flag` str | one row per (service date, source), both ends inclusive |
| QA table | second element of the tuple | `source`, `stage`, `rows_in`, `rows_out`, `reason`, `count` | one row per (source, reason); rows are days, one stage `coverage`, `rows_out` = covered days |
| Freshness | `cta.calendar.source_freshness(*, parquet_dir=None, raw_dir=None) -> DataFrame` | `source` str, `declared_edge` str, `observed_edge` str or None, `newest_last_modified` / `oldest_fetched_at` tz-aware UTC, `files` int64, `status` str (`not_moved`, `moved`, `no_metadata`) | one row per source whose directory was passed (`mansueto`, `mansueto_raw`) |

`cta.views.run_level_from_archive`, `run_level_from_mansueto` and `run_level_from_mansueto_raw` pass their own source
constant as `source=`. No column is added to `RUN_LEVEL_COLUMNS` (ADR-003); only the flag vocabulary grows.

## Method

Prior art to copy: `cta/calendar.py` `calendar_flag` (playbook pattern "Flag a service date instead of filtering it");
QA rows from `cta/mansueto.py` `qa_rows`; `tests/test_calendar.py` `test_calendar_flag_marks_holidays_and_gap_days`,
`tests/test_mansueto.py` QA additivity check.

1. Add the constants in Thresholds to `cta/calendar.py`, each with its evidence comment (pattern "Name a threshold").
   `source_coverage()` builds its table from them at call time, so a test can monkeypatch a constant.
2. A private `_coverage_reason(source, day)` returns `before_first_day`, `after_edge`, `missing_day_file` or `""`, in
   that priority. An unknown source raises `ValueError`. Both `calendar_flag` and `coverage_days` call it; nothing
   else decides coverage.
3. `calendar_flag(..., source=)` appends `coverage_gap` when the reason is non-empty. The reason itself is not in the
   flag (it is in `coverage_days`). Rows are flagged, never dropped (playbook gotcha "Holidays and archive outages are
   flags, not drops").
4. `coverage_days` builds the date range times `sources` (default: all three), fills `covered` and `reason` from
   step 2 and `calendar_flag` from step 3 (`index` applies to the `archive` rows only, as in the views today). The QA
   table has `rows_in` = days in range and `rows_out` = covered days per source, reason counts via `qa_rows`.
5. Dates are compared as the view's `service_date`. For `mansueto_raw` that is the calendar date (gotcha "Mansueto raw
   day files are calendar days, not service days"), which is also how the day files are named, so no conversion.
6. `source_freshness` globs the metadata files and reads JSON only: no network, no parquet, no write. `mansueto`:
   `observed_edge` = max of `max_bus_stop_time[:10]` (already Chicago wall time: gotcha "Mansueto `bus_stop_time` is
   naive Chicago wall time, not UTC"; never localize it as UTC); `moved` if `observed_edge` or any
   `last_modified[:10]` is later than `MANSUETO_DATA_EDGE` (the guard `scripts/build_mansueto_fixtures.py` already
   uses). `mansueto_raw`: `observed_edge` = latest day with a metadata file; `moved` if later than
   `MANSUETO_RAW_EDGE`. A directory with no metadata gives one `no_metadata` row. `moved` means "re-measure and
   reopen ADR-007 / ADR-009", not "extend the window": the constants change only through Rule 2.
7. Update the module docstring, the three view docstrings and `cta/__init__.py`; update the playbook gotcha
   "Holidays and archive outages are flags, not drops" with the new flag through `/finding`.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `cta.mansueto.MANSUETO_DATA_EDGE` (existing) | `"2026-07-28"`; `mansueto` covers through the day before | footer probe 2026-11-04 (ADR-007); ADR-009 counts 07-28 inside the 16-day hole; PID 18414 ends 00:04:59 that day | counting 07-28 as covered makes the hole 15 days and leaves a day with about five minutes of data unflagged |
| `MANSUETO_RAW_FIRST_DAY` | `"2026-08-13"` | HEAD sweep 2026-11-06; ADR-009 bounds the source here although files exist back to 2022-05-19 (`docs/2026-11-10-mansueto-raw-day-profile.md`) | earlier needs a new ADR |
| `MANSUETO_RAW_EDGE` | `"2026-10-27"` | same sweep; nothing since 2026-10-28 | re-measure before moving (ADR-009) |
| `MANSUETO_RAW_MISSING_DAYS` | `("2026-09-30", "2026-10-02", "2026-10-03", "2026-10-16", "2026-10-17")` | same sweep: 25 of 30 present | a day removed here must return HTTP 200 first |
| `ARCHIVE_FIRST_DAY` | `"2026-09-28"` | archive `index.json`; ADR-004, ADR-007 | none expected |
| archive last day | open (None) | live source, nightly (ADR-004) | see Open question 4 |
| `cta_holidays` (existing) | six Sunday-schedule holidays, on the day itself | vault note `cta-holiday-schedule-filtering` (not readable by agents; migration is its own TODO item) | unchanged by this spec |

## Fixtures

No new fixture. Metadata files for the freshness tests are written to `tmp_path` from the committed manifests.

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/archive_2026-10-29_michigan.index.json` | existing | | 8 `known_gaps` windows | |
| `tests/fixtures/mansueto.manifest.json`, `tests/fixtures/mansueto_raw.manifest.json` | existing | `sources[pid].data_edge` for 6410, 18414, 18415; `sources["2026-10-22"]` | 3 pids, 1 day | |
| view fixtures of `tests/test_views_archive.py`, `test_views_mansueto.py`, `test_views_mansueto_raw.py` | existing | | | |

## Acceptance tests

All in `tests/test_calendar.py` unless named. Counts below are calendar arithmetic on the constants, not estimates.

- [ ] `test_source_coverage_windows`: no fixture. Three rows; `mansueto` (None, `2026-07-27`, `()`), `mansueto_raw` (`2026-08-13`, `2026-10-27`, the five missing days), `archive` (`2026-09-28`, None, `()`).
- [ ] `test_coverage_days_known_case`: no fixture, range 2026-07-25 to 2026-10-31. 297 rows (99 days × 3 sources); covered days: `mansueto` 3, `mansueto_raw` 71, `archive` 34; days covered by no source: 16, exactly 2026-07-28 to 2026-08-12; days covered by both `archive` and `mansueto_raw`: 25; 2026-09-07 carries `holiday:Labor Day` on all three.
- [ ] `test_coverage_days_qa`: same range. Per source `rows_in` 99 and reason counts sum to `rows_in − rows_out`: `mansueto` `after_edge` 96; `archive` `before_first_day` 65; `mansueto_raw` `before_first_day` 19, `missing_day_file` 5, `after_edge` 4.
- [ ] `test_calendar_flag_coverage_gap`: `tests/fixtures/archive_2026-10-29_michigan.index.json`. `source="mansueto"` on [`2026-07-27`, `2026-07-28`, `2026-07-04`] gives [`""`, `coverage_gap`, `holiday:Independence Day`]; `source="mansueto_raw"` on `2026-10-16` gives `coverage_gap`; `source="archive"` with the index on `2026-10-16` gives `known_gap_day`; `source="mansueto_raw"` on `2026-11-26` gives `holiday:Thanksgiving Day;coverage_gap`; an unknown source raises `ValueError`; `source=None` output equals the existing test's.
- [ ] `test_views_pass_source_to_calendar_flag` (`tests/test_views_mansueto_raw.py`): on `tests/fixtures/mansueto_raw_2026-10-22_michigan.csv.gz`, with `MANSUETO_RAW_MISSING_DAYS` monkeypatched to include `2026-10-22`, every row of the view has `calendar_flag == "coverage_gap"`; unpatched, the existing all-`""` assertions of the three view tests still pass (measured 2026-11-12: neither Mansueto parquet fixture has a `bus_stop_time` on or after 2026-07-28).
- [ ] `test_source_freshness_not_moved`: metadata written to `tmp_path` from `tests/fixtures/mansueto.manifest.json` and `tests/fixtures/mansueto_raw.manifest.json`. Two rows, both `not_moved`; `mansueto` `observed_edge` `2026-07-28`, `files` 3; `mansueto_raw` `observed_edge` `2026-10-22`, `files` 1; timestamps tz-aware UTC.
- [ ] `test_source_freshness_moved_and_empty`: hand-built in `tmp_path`. A parquet metadata file with `max_bus_stop_time` `2026-11-01T08:00:00` gives `moved`; one with `last_modified` `2026-11-02T10:00:00+00:00` and an old `max_bus_stop_time` gives `moved`; a raw `2026-10-28.meta.json` gives `moved`; an empty directory gives `no_metadata` with `files` 0.

## Out of scope

- Probing the bucket or the archive (`data_edge`, HEAD sweeps): that is the Phase 3 refresh job, which calls `source_freshness` after fetching. No network in `cta/calendar.py`.
- Changing any constant because `source_freshness` says `moved`, or a staleness threshold on `fetched_at`.
- Dropping or filtering rows anywhere; a `covered` or flag column on `RUN_LEVEL_COLUMNS`.
- The holiday list, observed-day rules, non-Sunday holiday schedules, and migrating the vault note (TODO Foundation, "Migrate the durable knowledge-vault notes").
- Applying flags to the DLSD and Michigan figures (the "Reopens if the calendar retro-apply changes its figures" work).
- Stitching raw day files across midnight; raw CSV days before 2026-08-13; GTFS service calendars (Phase 3).
- The shared QA-row helper (`/qa` TODO item): use `cta.mansueto.qa_rows` as is.
- A script or notebook. Not handled because nothing here cleans rows: the other `source:mansueto stage:clean` gotchas (`6410.0` identifiers, backwards imputed times, null `origtatripno`).

## Open questions

1. Is the edge day itself a gap? Proposed yes: `mansueto` rows dated 2026-07-28 get `coverage_gap`, matching ADR-009's 16-day count.
2. One flag (`coverage_gap`) with the reason only in `coverage_days`, or the reason in the flag (`coverage_gap:missing_day_file`)? Proposed: one flag.
3. `mansueto` has no declared first day (parquets start per pid: 2022-06-01 for 6410, 2022-08-21 for 18414). Acceptable, or pin a global first day?
4. The archive has no declared last day and no whole-day gaps (the 2026-11-06 note found all 30 days present). Should `coverage_days` cap archive coverage at the newest day in a passed `index`? Proposed: not in this spec.
5. `mansueto_raw` rows before 2026-08-13 would be flagged `coverage_gap` although files exist. Confirm that ADR-009's bound is meant as a coverage declaration.
6. Adding a value to the published `calendar_flag` vocabulary: is a playbook update enough (Rule 2), or does it need an ADR line?
