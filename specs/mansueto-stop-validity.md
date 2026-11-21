# Spec: Dated stop validity in the Mansueto adapter (routes 8 and 66)

Status: draft
Owner: Satoru  ·  Date: 2026-11-17 (revised 2026-11-18: measured windows, route 8 in the fixture; 2026-11-19: no separate analysis view, the window is applied in the Mansueto adapter's pattern join, ADR-011; 2026-11-21: TODO section, route 66 windows start early, DuckDB gotcha cited; review: one fixture day per view, unwindowed re-measure, argument schemas, run-id date check; split: the measurement moved to `specs/stop-validity-measurement.md`)  ·  TODO item: Phase 1, Next — "Dated stop validity in the Mansueto adapter for routes 8 and 66 ([ADR-011](DECISIONS.md)): have `cta.mansueto.clean_trips` drop arrivals dated before a stop's `valid_from` in `pattern_join` as `stop_before_valid_from`, …" (full text in TODO.md; it replaces the item "Build the stop-level view for routes 8, 65, & 66", rescoped 2026-11-18 and 2026-11-19)
Tags: `kind:spec source:mansueto stage:clean topic:pattern-catalog topic:qa-table`

## Question

The Mansueto parquet has an arrival at every stop of today's route 8 and 66 detours for every run from 2024-09-03,
though the buses reached those streets only in late 2025: 2,127,091 arrivals on the four dominant patterns, 5.9% to
18.6% of their rows in that period (`docs/2026-11-15-routes-8-65-66-run-level-qa.md`). They look like real arrivals,
so a wait at those stops describes another street, and a travel time ending there uses a time projected onto a road
the bus was not on. `specs/stop-validity-measurement.md` measures, per stop, the date from which the buses served it
and commits it as pattern metadata. This spec has the Mansueto adapter's pattern join drop earlier arrivals, as it
already drops arrivals at stops not in the pattern (ADR-011). Fixtures are Mansueto cuts, so it does not wait on the
archive v2 adapter (owner, 2026-11-17); it does wait on the measurement spec, whose JSON the fixture tests read.
Choosing one source per day is the other half of ADR-011, in `specs/run-level-reader.md`.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Stop validity | `notebooks/routes_8_65_66_stop_validity.json` via `cta.stop_validity.load_stop_validity()` (`specs/stop-validity-measurement.md`) | `route`, `direction`, `stop_id`, `valid_from` (non-null ISO day) | committed; 38 candidates, the ones with a `valid_from` apply |
| Mansueto trips | `cta.mansueto.read_trips`; the fixtures below | `cta.mansueto.TRIP_COLUMNS` | |
| Pattern stops | `cta.bustracker.pattern_stops_table` | `pid`, `stpid`, `seq`, `rtdir` | the `getpatterns` fixtures in tests; the local cache for the rebuild |
| Full-history parquets | `data/mansueto/` (2.0 GB), local | `trips_<pid>_full.parquet` | the rebuild only |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Adapter | `cta.mansueto.clean_trips(trips, pattern_stops, stop_validity=None)`: stage `pattern_join` gains `REASON_STOP_BEFORE_VALID_FROM = "stop_before_valid_from"`; `None` applies no window. `mansueto_view_from_trips` and `run_level_from_mansueto[_with_qa]` gain `stop_validity=None`, which loads the committed table (an empty frame applies none), so every caller is windowed by default; only keys of routes 8 and 66 match | `stop_validity` is `load_stop_validity()`'s frame, of which only `route`, `direction`, `stop_id` and `valid_from` (non-null ISO day) are read, all strings; `CLEAN_COLUMNS`, `STAGES` and `RUN_LEVEL_COLUMNS` unchanged | one row per kept (run, stop) |
| CLI | `scripts/route_run_level.py --source mansueto` applies the JSON; `--no-validity` builds the view without windows (to re-measure, per `specs/stop-validity-measurement.md`, and for the QA note's comparison); `detour_stop_arrivals.csv` then counts the arrivals the windows kept (stops served in a middle period, stops with no window); the docstring's "nothing is dropped … for the stop-level spec" is replaced | — | — |
| `/qa` case | `cta.qa_baseline.FIXTURE_CASES["mansueto_2025_10_14_routes8_65_66"]` (`_mansueto_case` gains `day=None`, passed as `start=day` and `end=` the next day), recorded in `tests/fixtures/qa_baseline.csv` | baseline rows | a new case; the route 3 and 6410 rows do not move |
| Docs | playbook gotcha "Mansueto stop lists do not follow the route the bus took": its Fix line names `stop_before_valid_from` and cites both this spec and `specs/stop-validity-measurement.md` | — | — |
| QA note | `docs/<date>-routes-8-65-66-stop-validity-qa.md` (`/finding`) | route 8, 65, 66 `pattern_join` totals after the rebuild against the 2026-11-15 note; per dominant pid, `stop_before_valid_from` plus the windowed build's `arrivals_before_today_geometry` against the unwindowed build's (equal, apart from rows the `order` stage drops differently once a stop is gone: 1 on route 8 in the whole history, none on route 66); runs whose `run_id` has no trailing date, over the 24 pids (expected 0) | — |

## Method

Prior art to copy: `cta/mansueto.py` `clean_trips` stage `pattern_join` (a reason inside an existing stage);
`tests/test_mansueto.py` `test_clean_trips_analytic_case` and `test_qa_reasons_sum_to_rows_dropped_and_stages_chain`;
`tests/test_views_mansueto.py` for a fixture-day view.

Preparatory refactor (no behaviour change, rule 7; no test edited; `/qa` shows no diff): the service-date rule at the
end of `clean_trips` becomes `_service_date(df)`.

1. *Adapter*: in `pattern_join`, after the join gives each row its `rtdir`, a row whose (`route`, `rtdir`, `stpid`)
   has a window and whose run's `_service_date` (on the rows at this stage) is before `valid_from` is dropped as
   `stop_before_valid_from`. One reason per row; the stage's reasons sum to its `rows_in − rows_out`. The service
   date at this stage equals the final one when the run id ends in its date, as Mansueto ids are built (the column
   mapping note checked it on pid 6662); otherwise `_service_date` falls back to the Chicago date of the run's earliest
   row, which moves as rows drop, so the QA note counts runs without one (expected 0).
2. *Defaults*: `clean_trips` applies a window only when given one. The view functions load the committed table when
   `stop_validity` is `None`; `scripts/route_run_level.py --no-validity` passes an empty frame.
3. *Dates*: a window starts on a geometry change, not on the day the buses moved (`specs/stop-validity-measurement.md`
   Method 5): 13 days late on route 8, 1 to 2 days early on route 66. This spec applies the dates as measured.
4. The raw-CSV and archive adapters are unchanged: they impute against today's geometry, which fits all 71 raw days
   and the archive days checked. Older days, and the stops served before 2024-09-03 that today's patterns lack,
   need dated geometry (TODO item "Historical pattern geometry from GTFS").
5. `scripts/route_run_level.py --source mansueto --no-validity` (keeping its `detour_stop_arrivals.csv`), then
   `--source mansueto`, are run for routes 8, 65 and 66, and the QA note written.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| Validity windows | each key's `valid_from` in the committed JSON; none new here | `specs/stop-validity-measurement.md`; 2,127,091 arrivals at the candidates before each pid's last change | per stop, from the measurement |

New exclusion: `stop_before_valid_from` (Rule 2; this spec, the QA table and the `/qa` baseline carry it; ADR-011
point 3 records the decision).

## Fixtures

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/mansueto_2025-10-14_routes8_65_66.parquet` | `trips_<pid>_full.parquet` for the 24 `getpatterns_ok` pids | `bus_stop_time` on Tuesday 2025-10-14, 11 columns verbatim | ~50,000 rows, ~0.55 MB (estimate; measure, then pin) | `scripts/build_mansueto_fixtures.py` `cut_one_day`, via `/fixture` |
| `tests/fixtures/mansueto_2025-12-02_routes65_66.parquet` | the 15 `getpatterns_ok` pids of routes 65 and 66 | Tuesday 2025-12-02 | ~30,000 rows, ~0.35 MB (estimate) | same |
| `tests/fixtures/getpatterns/getpatterns_<pid>.json` × 24 | Bus Tracker `getpatterns`, one pid per call | whole response | 24 files (add-only; needs `CTA_API_KEY`, 24 calls) | `/fixture` |
| `notebooks/routes_8_65_66_stop_validity.json` | from `specs/stop-validity-measurement.md` | — | 38 rows | already committed when this spec is implemented |

Why these days: on 2025-10-14 route 66 eastbound is past its change, route 66 westbound is between its two, and
route 8 is between its two (a valid, a split and two mostly invalid directions); 2025-12-02 is after every change.
Route 65 shares detour stops with route 66 and has no window of its own. Both parquets hold the route 65 and 66 pids,
and `cta.mansueto.parquet_files_for_pid` reads every parquet in the directory for a pid with no file of its own, so
every view over these fixtures passes `start` and `end` for its day (naive Chicago time, `end` exclusive).

## Acceptance tests

`tests/test_mansueto.py` for the first; fixture-day views as `tests/test_views_mansueto.py` builds the route 3 one,
each passing `start` and `end` for its day (see Fixtures).

- [ ] `test_clean_trips_stop_validity_hand_built`: hand-built trips and pattern stops; route `r1` Eastbound patterns
      `p1` (a, b, c) and `p2` (b, c, d), `p3` Westbound (c), route `r2` Eastbound (c); window (`r1`, Eastbound, c)
      from 2025-09-27; run ids embed their date. Dropped as `stop_before_valid_from`: `p1` and `p2` arrivals at c on
      runs dated 2025-09-26, one of them at 00:30 Chicago on 2025-09-27. Kept: c on 2025-09-27, c on `p3`, c on `r2`,
      every other stop of the runs that lost c. A stop in no pattern is still `stop_not_in_pattern`; `pattern_join`
      reasons sum to `rows_in − rows_out`; `stop_validity=None` gives exactly the output without this spec.
- [ ] `test_view_stop_validity_default_and_empty`: hand-built trips on one run, dated the day before the `valid_from`
      of the first row of `load_stop_validity()`, at that row's stop, route and direction. `mansueto_view_from_trips`
      with `stop_validity=None` drops that arrival (one `stop_before_valid_from` in its QA table), exactly as with the
      loaded frame passed explicitly; an empty frame keeps it and equals the output of `clean_trips` without a window.
- [ ] `test_mansueto_view_fixture_2025_10_14`: `run_level_from_mansueto_with_qa` on that fixture with the committed
      table: a key whose `valid_from` is after 2025-10-14 has no arrival; a key with a null or earlier `valid_from`
      keeps every arrival of the build with an empty table; `stop_before_valid_from` is ~4,000 (estimate; measure,
      then pin) in all on routes 8 and 66 together, and 0 on route 65; fixture rows and bytes as pinned by `/fixture`.
- [ ] `test_mansueto_view_fixture_2025_12_02`: `stop_before_valid_from` is 0 on every pid. Grouped by the stop key of
      ADR-011, (66, Eastbound) has ~78 stops against 69 on pid 6662 (estimate, from the 2026-05 to 2026-07 window), and
      ~15 `stop_id`s are keys under both route 65 and route 66 (estimate).
- [ ] `test_baseline_matches_fixtures` (existing, `tests/test_qa_baseline.py`): passes with the new case recorded and
      the `mansueto_route3` and `mansueto_6410` rows not re-recorded.

## Out of scope

- The measurement, the JSON, `cta/stop_validity.py` and `cta/geo.py` (`specs/stop-validity-measurement.md`); one
  source per day, the reader, the stop key's code (`specs/run-level-reader.md`).
- The raw-CSV and archive adapters; dated pattern stop tables from GTFS; stops served before 2024-09-03 that today's
  patterns lack (TODO item "Historical pattern geometry from GTFS").
- Windows per minor pattern; route 65 (no geometry change); routes beyond 8, 65 and 66 (Phase 2 ingestion).
- Waits, headways, any minimum-sample gate; event days; the route 65 retired-pid shortfall.
- A `bracket_gap_s` bound; refreshing committed getpatterns files.

## Decisions (owner)

- 2026-11-18: route 8 in the 2025-10-14 fixture; the window decisions (measured per stop, minor patterns take their
  direction's window) are in `specs/stop-validity-measurement.md`.
- 2026-11-19: no separate analysis view; the window is pattern metadata and the Mansueto adapter applies it (ADR-011).
  Earlier revisions: commit `61a2b4c` (options and evidence), `488b2bc` (the analysis view).
- 2026-11-21: the measurement is its own spec, so that a "stop and report" on the distances does not hold this one.

## Open questions

None. ADR-011 was accepted on 2026-11-19. The measurement spec is done before this one is implemented.
