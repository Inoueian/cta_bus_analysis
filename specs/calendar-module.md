# Spec: Calendar module (source coverage and Mansueto freshness)

Status: done (implemented 2026-11-12 on branch `claude/awesome-hypatia-3bg9h4`; notes at the end)
Owner: Satoru  ·  Date: 2026-11-12 (revised 2026-11-12: owner answers, two reviews)  ·  TODO item (Foundation): "Calendar module (`cta/calendar.py`): CTA holidays, archive `known_gaps` windows, Mansueto freshness; one place, flag rows rather than drop them. Started 2026-11-03 with the archive adapter (six Sunday-schedule holidays, `known_gaps`, `calendar_flag`); Mansueto freshness (read `MANSUETO_DATA_EDGE` and the per-pid `trips_<pid>_full.meta.json` that `cta.mansueto.fetch_parquet` writes; the source-coverage holes belong here too: 2026-07-28 to 2026-08-12 covered by nothing, the five raw-CSV days missing between 2026-09-28 and 2026-10-27, and the raw-CSV edge 2026-10-27, per ADR-007, ADR-009 and `docs/2026-11-06-mansueto-raw-positions.md`) remain; the holiday vault note moves with the migration item above. Absorbs the former "Holiday schedule filtering (cross-cutting)" item; applies retroactively to the DLSD analysis once the helpers read the run-level view (next item). Spec: specs/calendar-module.md (ready)"
Tags: `kind:spec source:mansueto source:archive stage:clean topic:calendar`

## Question

Which service dates does each source cover, and has a frozen Mansueto source moved? ADR-007 and ADR-009 require every
time series to show the 2026-07-28 to 2026-08-12 hole and the missing raw-CSV days rather than bridge them, and ADR-009
declares those gaps "in `cta/calendar.py`". Today they live in prose and in adapter comments, so a wait-time or drift
chart cannot tell "no buses" from "no data" (playbook gotcha "Mansueto imputed history stops at 2026-07-28 and never
overlaps the archive"). This spec adds the two missing calendar facts (declared source coverage,
Mansueto freshness) to the module that already holds holidays and `known_gaps`. Holidays and `known_gaps` do not change.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Parquet data edge | `cta.mansueto.MANSUETO_DATA_EDGE` | `"2026-07-28"` | stays in `cta.mansueto` (ADR-007 names it there); `cta.calendar` reads `mansueto.MANSUETO_DATA_EDGE` at call time (no `from` import, so one monkeypatch reaches both modules) |
| Parquet download metadata | `<parquet_dir>/trips_<pid>_full.meta.json` (`cta.mansueto.write_meta`) | `pid`, `last_modified` (ISO UTC), `max_bus_stop_time` (naive Chicago wall time), `fetched_at` (ISO UTC) | written by `fetch_parquet`; read only |
| Raw-CSV download metadata | `<raw_dir>/YYYY-MM-DD.meta.json` (`cta.mansueto_raw.fetch_day`) | `url`, `last_modified`, `fetched_at`; the day is the file name | read only |
| Archive index | `index` dict (`cta.archive.fetch_index`) | `known_gaps`; `days[].date` with a `files.bus` entry | archive rows only; `days` gives the archive's last day and whole-day gaps (Method 3) |
| Coverage dates | `docs/2026-11-06-mansueto-raw-positions.md`, ADR-007, ADR-009 | see Thresholds | measured 2026-11-04 and 2026-11-06 |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Declared coverage | `cta.calendar.source_coverage(index=None) -> DataFrame` | `source` str, `first_day` str or None, `last_day` str or None (inclusive, `YYYY-MM-DD`, None = open), `missing_days` tuple of str, `evidence` str | one row per source (`mansueto`, `mansueto_raw`, `archive`) |
| Row flag | `cta.calendar.calendar_flag(service_date, *, index=None, source=None) -> Series` | str; adds `coverage_gap` after the existing parts, order `holiday:<name>;known_gap_day;coverage_gap` | one value per input row; `source=None` returns today's output unchanged |
| Date spine | `cta.calendar.coverage_days(start, end, *, sources=None, index=None) -> (DataFrame, DataFrame)` | `service_date` str, `source` str, `covered` bool, `reason` str (`""`, `before_first_day`, `after_edge`, `missing_day_file`), `calendar_flag` str | one row per (service date, source), both ends inclusive |
| QA table | second element of the tuple | `source`, `stage`, `rows_in`, `rows_out`, `reason`, `count` | one row per (source, reason); rows are days, one stage `coverage`, `rows_out` = covered days; columns `COVERAGE_QA_COLUMNS = ["source"] + mansueto.QA_COLUMNS` (shape of `views.MANSUETO_QA_COLUMNS`) |
| Freshness | `cta.calendar.source_freshness(*, parquet_dir=None, raw_dir=None) -> DataFrame` | `source` str, `declared_edge` str, `observed_edge` str or None, `newest_last_modified` / `oldest_fetched_at` tz-aware UTC, `files` int64, `status` str (`not_moved`, `moved`, `no_metadata`); a `no_metadata` row has `observed_edge` None, both timestamps NaT, `files` 0 | one row per source whose directory was passed (`mansueto`, `mansueto_raw`) |
| Freshness of records | `cta.calendar.freshness_status(source, records) -> dict` | the same fields as one Freshness row | one dict per call; `records` are `cta.mansueto.data_edge` dicts (`mansueto`) or dicts with `day`, `last_modified` (`mansueto_raw`), `fetched_at` optional |

`cta.views.run_level_from_archive`, `run_level_from_mansueto` and `run_level_from_mansueto_raw` pass their own source
constant as `source=`. No column is added to `RUN_LEVEL_COLUMNS` (ADR-003); only the flag vocabulary grows.

## Method

Prior art to copy: `cta/calendar.py` `calendar_flag` (playbook pattern "Flag a service date instead of filtering it");
QA rows from `cta/mansueto.py` `qa_rows`; `tests/test_calendar.py` `test_calendar_flag_marks_holidays_and_gap_days`,
`tests/test_mansueto.py` QA additivity check.

1. Add the constants in Thresholds to `cta/calendar.py`, each with its evidence comment (pattern "Name a threshold").
   `source_coverage()` builds its table from them at call time, so a test can monkeypatch a constant.
2. A private `_coverage_reason(source, day, index=None)` returns `before_first_day`, `after_edge`,
   `missing_day_file` or `""`, in that priority. An unknown source raises `ValueError`. `source_coverage`,
   `calendar_flag` and `coverage_days` all go through it; nothing else decides coverage.
3. The archive's upper edge comes from the index, not a constant. Without `index` the archive is open-ended from
   `ARCHIVE_FIRST_DAY` with no missing days. With `index`, the listed days are the `days[].date` values that have a
   `files.bus` entry; the index speaks only for the span from the first to the last listed day. Days after the last
   listed day are `after_edge`; an unlisted day inside the span is `missing_day_file`; days from `ARCHIVE_FIRST_DAY`
   up to the first listed day are covered, because the index makes no claim about them. This matters for cut
   manifests: `archive_2026-10-29_michigan.index.json` lists one day, yet its day file holds 1,091 rows whose
   `service_date` (`sched_start_date`) is 2026-10-28, and those must not be flagged. The full `index.json` starts
   2026-09-28, so the rule changes nothing there. `index` never affects the two Mansueto sources.
   The rule assumes the listed days are contiguous apart from real gaps: a cut manifest listing two non-adjacent days
   would mark the days between them missing (Rule 3 keeps cuts to one day, so none does today).
   Accepted, not flagged: a run that crosses midnight after the last listed day, or into a missing day, has its tail
   in a file that is not there. These are late-night fragments of an otherwise complete service day.
4. `calendar_flag(..., source=)` appends the single value `coverage_gap` when the reason is non-empty; the reason
   itself appears only in `coverage_days`. A missing day has no rows, so on rows the flag marks fragments, such as a
   `mansueto` run dated on the edge day. Rows are flagged, never dropped (playbook gotcha "Holidays and archive
   outages are flags, not drops").
5. `coverage_days` builds the date range times `sources` (default: all three), fills `covered` and `reason` from
   step 2 and `calendar_flag` from step 4. The QA table has `rows_in` = days in range and `rows_out` = covered days
   per source, reason counts via `qa_rows`.
6. Dates are compared as the view's `service_date`. For `mansueto_raw` that is the calendar date (gotcha "Mansueto raw
   day files are calendar days, not service days"), which is also how the day files are named, so no conversion.
7. `freshness_status` holds the status logic and takes the records themselves, so the refresh job can pass
   `data_edge` probe results without downloading a parquet (ADR-009, decision 3). `source_freshness` globs the
   metadata files, reads JSON only (no network, no parquet, no write), turns them into records (`day` from the raw
   file name) and calls it. `mansueto`:
   `observed_edge` = max of `max_bus_stop_time[:10]` (already Chicago wall time: gotcha "Mansueto `bus_stop_time` is
   naive Chicago wall time, not UTC"; never localize it as UTC); `moved` if `observed_edge` or any
   `last_modified[:10]` is later than `MANSUETO_DATA_EDGE` (the guard `scripts/build_mansueto_fixtures.py` already
   uses). `mansueto_raw`: `observed_edge` = latest record day; `moved` if later than `MANSUETO_RAW_EDGE`, or
   if any record's day is in `MANSUETO_RAW_MISSING_DAYS` (`fetch_day` writes metadata only after a successful
   download, so such a record means the day came back). No records gives a `no_metadata` row. `moved` means "re-measure and
   reopen ADR-007 / ADR-009", not "extend the window": the constants change only through Rule 2.
8. Update the module docstring, the three view docstrings and `cta/__init__.py`; update the playbook gotcha
   "Holidays and archive outages are flags, not drops" with the new flag, and the gotcha "Mansueto imputed history
   stops at 2026-07-28 and never overlaps the archive" to point at `source_coverage`, through `/finding`. No ADR: ADR-009 already
   decided that coverage gaps are declared in `cta/calendar.py` (owner, 2026-11-12).

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `cta.mansueto.MANSUETO_DATA_EDGE` (existing) | `"2026-07-28"`; `mansueto` covers through the day before, the edge day is a gap | footer probe 2026-11-04 (ADR-007): files regenerated about 10:15 UTC that day, last `bus_stop_time` 00:04 (18414), 01:41 (6414), 02:04 (18415), none for 6410; ADR-009 counts 07-28 inside the 16-day hole | counting 07-28 as covered makes the hole 15 days and leaves a two-hour fragment unflagged |
| `MANSUETO_FIRST_DAY` | `None` (open) | parquets start per pid (2022-05-31 for 6414, 2022-08-21 for 18414), so one date would be wrong per pattern; no analysis goes back four years (owner, 2026-11-12) | a pattern with no rows on a covered day is a fact about the pattern, not a calendar gap |
| `MANSUETO_RAW_FIRST_DAY` | `"2026-08-13"` | HEAD sweep 2026-11-06; ADR-009 bounds the source here. Files exist back to 2022-05-19 (sampled, not swept; `docs/2026-11-10-mansueto-raw-day-profile.md`), so a row from an earlier day is flagged `coverage_gap` meaning "outside the declared window", not "data missing" (owner accepted, 2026-11-12) | extending history needs a new ADR and a sweep that sets the real first day; dropping the bound without one would claim coverage for 2026-07-28 to 2026-08-12, where the sweep found no files |
| `MANSUETO_RAW_EDGE` | `"2026-10-27"` | same sweep; nothing since 2026-10-28 | re-measure before moving (ADR-009) |
| `MANSUETO_RAW_MISSING_DAYS` | `("2026-09-30", "2026-10-02", "2026-10-03", "2026-10-16", "2026-10-17")` | same sweep: 25 of 30 present | a day removed here must return HTTP 200 first |
| `ARCHIVE_FIRST_DAY` | `"2026-09-28"` | archive `index.json`; ADR-004, ADR-007 | none expected |
| archive last day and whole-day gaps | from the passed `index` (Method 3); open without one | live source, nightly (ADR-004); `known_gaps` only describes outages within a day | without the index a spine to today overstates coverage by the publishing lag and hides a day that was never published |
| `cta_holidays` (existing) | six Sunday-schedule holidays, on the day itself | vault note `cta-holiday-schedule-filtering` (not readable by agents; migration is its own TODO item) | unchanged by this spec |

## Fixtures

No new fixture. Metadata files for the freshness tests are written to `tmp_path` from the committed manifests; the archive-edge test uses a hand-built index dict.

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/archive_2026-10-29_michigan.index.json` | existing | | 8 `known_gaps` windows | |
| `tests/fixtures/mansueto.manifest.json`, `tests/fixtures/mansueto_raw.manifest.json` | existing | `sources[pid].data_edge` for 6410, 18414, 18415; `sources["2026-10-22"]` | 3 pids, 1 day | |
| view fixtures of `tests/test_views_archive.py`, `test_views_mansueto.py`, `test_views_mansueto_raw.py` | existing | | | |

## Acceptance tests

All in `tests/test_calendar.py` unless named. Counts below are calendar arithmetic on the constants, not estimates.

- [x] `test_source_coverage_windows`: no fixture. Without an index, three rows; `mansueto` (None, `2026-07-27`, `()`), `mansueto_raw` (`2026-08-13`, `2026-10-27`, the five missing days), `archive` (`2026-09-28`, None, `()`).
- [x] `test_coverage_days_known_case`: no fixture, range 2026-07-25 to 2026-10-31. 297 rows (99 days × 3 sources); covered days: `mansueto` 3, `mansueto_raw` 71, `archive` 34; days covered by no source: 16, exactly 2026-07-28 to 2026-08-12; days covered by both `archive` and `mansueto_raw`: 25; 2026-09-07 has `calendar_flag` `holiday:Labor Day;coverage_gap` for `mansueto` and `archive` and `holiday:Labor Day` for `mansueto_raw`.
- [x] `test_coverage_days_qa`: same range. Per source `rows_in` 99 and reason counts sum to `rows_in − rows_out`: `mansueto` `after_edge` 96; `archive` `before_first_day` 65; `mansueto_raw` `before_first_day` 19, `missing_day_file` 5, `after_edge` 4.
- [x] `test_calendar_flag_coverage_gap`: `tests/fixtures/archive_2026-10-29_michigan.index.json`. `source="mansueto"` on [`2026-07-27`, `2026-07-28`, `2026-07-04`] gives [`""`, `coverage_gap`, `holiday:Independence Day`]; `source="mansueto_raw"` on `2026-10-16` gives `coverage_gap`; `source="archive"` without an index on [`2026-09-27`, `2026-10-16`] gives [`coverage_gap`, `""`], and with the index on `2026-10-29` gives `""`; `source="mansueto_raw"` on `2026-11-26` gives `holiday:Thanksgiving Day;coverage_gap`; an unknown source raises `ValueError`; `source=None` output equals the existing test's.
- [x] `test_archive_coverage_from_index`: hand-built index listing 2026-09-28 to 2026-10-05 except 2026-10-02 (each with a `files.bus` entry) and one bus `known_gaps` window inside 2026-10-03. `coverage_days("2026-09-27", "2026-10-07", sources=["archive"], index=index)` has 11 rows, 7 covered; QA reasons `before_first_day` 1, `missing_day_file` 1 (2026-10-02), `after_edge` 2, summing to `rows_in − rows_out`; 2026-10-03 is covered with `known_gap_day`; `source_coverage(index)` gives the archive `last_day` `2026-10-05` and `missing_days` `("2026-10-02",)`; the same range with `sources=["mansueto_raw"]` is identical with and without the index.
- [x] `test_views_pass_source_to_calendar_flag` (one case in each of `tests/test_views_archive.py`, `test_views_mansueto.py`, `test_views_mansueto_raw.py`, on the view fixture each file already uses): with `ARCHIVE_FIRST_DAY` monkeypatched to `2026-10-30`, `cta.mansueto.MANSUETO_DATA_EDGE` to `2026-06-01` (before the 6410 fixture's 30-day window), and `MANSUETO_RAW_MISSING_DAYS` to include `2026-10-22` respectively, every row has `calendar_flag` ending in `coverage_gap`. Unpatched, the existing all-`""` assertions still pass (measured 2026-11-12: neither Mansueto parquet fixture has a `bus_stop_time` on or after 2026-07-28; the archive fixture's 1,091 rows dated 2026-10-28 fall before its index's first listed day, Method 3).
- [x] `test_source_freshness_not_moved`: metadata written to `tmp_path` from `tests/fixtures/mansueto.manifest.json` and `tests/fixtures/mansueto_raw.manifest.json`. Two rows, both `not_moved`; `mansueto` `observed_edge` `2026-07-28`, `files` 3; `mansueto_raw` `observed_edge` `2026-10-22`, `files` 1; timestamps tz-aware UTC; `freshness_status("mansueto", [the three data_edge dicts])` returns the same `status` and `observed_edge` with `oldest_fetched_at` NaT.
- [x] `test_source_freshness_moved_and_empty`: hand-built in `tmp_path`. A parquet metadata file with `max_bus_stop_time` `2026-11-01T08:00:00` gives `moved`; one with `last_modified` `2026-11-02T10:00:00+00:00` and an old `max_bus_stop_time` gives `moved`; a raw `2026-10-28.meta.json` gives `moved`; a raw `2026-10-02.meta.json` (a declared-missing day) alone gives `moved`; an empty directory gives `no_metadata` with `files` 0.

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

None open. The owner answered all six on 2026-11-12 (edge day is a gap; one flag value; no `mansueto` first day; archive edge from the index; ADR-009's raw bound kept; playbook update, no ADR); the answers are in Method and Thresholds.

## Implementation notes (2026-11-12)

- `coverage_days` passes `index` to `calendar_flag` for archive rows only, so `known_gap_day` never lands on a
  Mansueto row (Method 3: "`index` never affects the two Mansueto sources"). `test_archive_coverage_from_index`
  therefore compares the `mansueto_raw` spine with and without the index in full, `calendar_flag` included.
- `source_coverage` and `source_freshness` hold `None` as `None` (object columns); pandas 3 would otherwise
  turn it into NaN.
- The view tests use one or two pids (6414 for the archive view, 6414 and 18414 for the raw view, 6410 for Mansueto) to keep them fast.
