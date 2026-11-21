# Spec: Dated stop validity in the Mansueto adapter (routes 8 and 66)

Status: draft
Owner: Satoru  ·  Date: 2026-11-17 (revised 2026-11-18: measured windows, route 8 in the fixture; 2026-11-19: no separate analysis view, the window is applied in the Mansueto adapter's pattern join, ADR-011; 2026-11-21: TODO section, route 66 windows start early, DuckDB gotcha cited; 2026-11-21 review: one fixture day per view, unwindowed re-measure, argument schemas, run-id date check)  ·  TODO item: Phase 1, Next — "Dated stop validity in the Mansueto adapter for routes 8 and 66 ([ADR-011](DECISIONS.md)): the parquet has an arrival at every stop of today's route 8 and 66 detours for every run from 2024-09-03 …" (full text in TODO.md; it replaces the item "Build the stop-level view for routes 8, 65, & 66", rescoped 2026-11-18 and 2026-11-19)
Tags: `kind:spec source:mansueto stage:clean topic:pattern-catalog topic:qa-table`

## Question

The Mansueto parquet has an arrival at every stop of today's route 8 and 66 detours for every run from 2024-09-03,
though the buses reached those streets only in late 2025: 2,127,091 arrivals on the four dominant patterns, 5.9% to
18.6% of their rows in that period (`docs/2026-11-15-routes-8-65-66-run-level-qa.md`). They look like real arrivals,
so a wait at those stops describes another street, and a travel time ending there uses a time projected onto a road
the bus was not on. A stop belongs to a pattern from a date: this spec measures that date per stop, records it as
pattern metadata, and has the Mansueto adapter's pattern join drop earlier arrivals, as it already drops arrivals at
stops not in the pattern (ADR-011). Fixtures are Mansueto cuts, so this does not wait on the archive v2 adapter
(owner, 2026-11-17). Choosing one source per day is the other half of ADR-011, in `specs/run-level-reader.md`.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Mansueto parquets, run-level view | `data/mansueto/`; `data/route_run_level/source=mansueto/…` (`scripts/route_run_level.py`) | `cta.mansueto.TRIP_COLUMNS`; `RUN_LEVEL_COLUMNS` | the full-history view, built with `--no-validity`, finds each stop's first arrival day |
| Pid list | `notebooks/routes_8_65_66_pids.json` | `pids[].dominant`, `geometry_changes[]` (`pid`, `first_day_new`) | 7 dated changes on 4 pids |
| Pattern stops | `cta.bustracker.pattern_stops_table` (local cache) | `pid`, `stpid`, `stpnm`, `lat`, `lon` | stop positions |
| Raw day CSVs | `cta.mansueto_raw.fetch_day` / `read_day` for `VALIDITY_SAMPLE_DAYS` into `data/mansueto_raw/` | `POSITION_COLUMNS` (`pid`, `lat`, `lon`) | read for the measurement only; three of the four days are before ADR-009's declared window and enter no view |
| Stop validity (new) | `notebooks/routes_8_65_66_stop_validity.json` | rows of `route`, `direction`, `stop_id`, `stop_name`, `from_pid`, `source`, `first_arrival_day`, `nearest_ping_ft` ({sample day: feet}), `valid_from` (ISO day or null) | 38 candidate stops; built once (Method 1–4); committed, read by the adapter and tests |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Measurement | `cta/stop_validity.py`: `geometry_periods(pid_file, pid) -> DataFrame`, `stop_validity_from_pings(candidates, stops, pings, periods, max_ft) -> DataFrame`, `load_stop_validity(path=None) -> DataFrame`; constants `EPOCH_SLACK_DAYS`, `VALIDITY_SAMPLE_DAYS`, `MAX_STOP_PING_DISTANCE_FT` | periods: `pid`, `start` / `end_exclusive` (ISO day strings or null), `sample_day`; `candidates`: `route`, `direction`, `stop_id`, `stop_name`, `from_pid`, `first_arrival_day`; `stops`: `pattern_stops_table`; `pings`: `read_day` output (`POSITION_COLUMNS`, the day in `data_date`); result and loader: the JSON's rows, the loader keeping those with a `valid_from` | one row per period; per candidate stop |
| Geometry helper | `cta/geo.py`: `straight_line_feet` (moved), `nearest_feet(lat, lon, lats, lons) -> float` | haversine feet, `EARTH_RADIUS_FEET` | one point against many |
| Adapter | `cta.mansueto.clean_trips(trips, pattern_stops, stop_validity=None)`: stage `pattern_join` gains `REASON_STOP_BEFORE_VALID_FROM = "stop_before_valid_from"`; `None` applies no window. `mansueto_view_from_trips` and `run_level_from_mansueto[_with_qa]` gain `stop_validity=None`, which loads the committed table (an empty frame applies none), so every caller is windowed by default; only keys of routes 8 and 66 match | `stop_validity` is `load_stop_validity()`'s frame, of which only `route`, `direction`, `stop_id` and `valid_from` (non-null ISO day) are read, all strings; `CLEAN_COLUMNS`, `STAGES` and `RUN_LEVEL_COLUMNS` unchanged | one row per kept (run, stop) |
| CLI | `scripts/route_run_level.py`: `--no-validity` (with `--source mansueto`) builds the view without windows; `--write-validity` reads that view, writes the JSON, and refuses when `qa_mansueto.csv` holds a `stop_before_valid_from` row; `--source mansueto` applies the JSON, and `detour_stop_arrivals.csv` then counts the arrivals the windows kept (stops served in a middle period, stops with no window). The docstring's "nothing is dropped … for the stop-level spec" is replaced | — | — |
| `/qa` case | `cta.qa_baseline.FIXTURE_CASES["mansueto_2025_10_14_routes8_65_66"]` (`_mansueto_case` gains `day=None`, passed as `start=day` and `end=` the next day), recorded in `tests/fixtures/qa_baseline.csv` | baseline rows | a new case; the route 3 and 6410 rows do not move |
| Docs | `cta/__init__.py` module list and CLAUDE.md's Layout paragraph name `stop_validity` and `geo`; playbook gotcha "Mansueto stop lists do not follow the route the bus took" Fix line names the reason | — | — |
| QA note | `docs/<date>-routes-8-65-66-stop-validity-qa.md` (`/finding`) | the distance table; windows; route 8, 65, 66 `pattern_join` totals after the rebuild against the 2026-11-15 note; per dominant pid, `stop_before_valid_from` plus the windowed build's `arrivals_before_today_geometry` against the unwindowed build's (equal, apart from rows the `order` stage drops differently once a stop is gone: 1 on route 8 in the whole history, none on route 66); runs whose `run_id` has no trailing date, over the 24 pids (expected 0); first arrival per windowed key | — |

## Method

Prior art to copy: `cta/mansueto.py` `clean_trips` stage `pattern_join` (a reason inside an existing stage);
`scripts/route_run_level.py` `detour_stop_arrivals` (the candidates); `tests/test_mansueto.py`
`test_clean_trips_analytic_case` and `test_qa_reasons_sum_to_rows_dropped_and_stages_chain`.

Preparatory refactor (no behaviour change, rule 7; no test edited; `/qa` shows no diff): `today_geometry_first_day` and
`EPOCH_SLACK_DAYS` move from `scripts/route_run_level.py` to `cta/stop_validity.py`; `straight_line_feet` and
`EARTH_RADIUS_FEET` move from `cta/michigan_ave_segment.py` to `cta/geo.py`, which `michigan_ave_segment` imports
(`cta.views` will import `cta.stop_validity`, and `michigan_ave_segment` imports `cta.views`, so the helper cannot
stay there); the service-date rule at the end of `clean_trips` becomes `_service_date(df)`. `scripts/route_run_level.py`
and `cta/michigan_ave_segment.py` import the moved names, so `rrl.today_geometry_first_day`
(`tests/test_route_run_level.py`) and `mas.straight_line_feet` (`tests/test_michigan_segment_from_view.py`) still resolve.

1. *Candidates*: on the four pids in `geometry_changes`, a stop whose first Mansueto `service_date` is more than
   `EPOCH_SLACK_DAYS` after the pid's first (the rule of `detour_stop_arrivals`): 11 / 13 / 8 / 6 on 6662 / 6665 /
   9368 / 9376, 38 in all. It reads days from `service_date` (a string), not `arrival_time`, which DuckDB's `.df()`
   returns without its zone (playbook gotcha "DuckDB returns tz-aware view timestamps as naive"). It reads the view
   built with `--no-validity`, since a windowed view no longer shows each stop's first arrival.
2. *Periods*: `geometry_periods` cuts a pid's history at each of its `first_day_new` (first period open at the start,
   last open at the end). Its `sample_day` is the latest of `VALIDITY_SAMPLE_DAYS` inside it; a period without one
   raises, naming pid and period. Today: 6662 2025-09-16 / 2026-09-15; 6665 2025-09-16 / 2025-10-14 / 2026-09-15;
   9368 and 9376 2025-07-15 / 2025-10-14 / 2026-09-15.
3. *Distance*: per candidate and period, `nearest_ping_ft` is `cta.geo.nearest_feet` from the stop's getpatterns
   position to the pings of the candidate's pid on the sample day (null `lat`/`lon` skipped). The stop is served in
   the period when that is at most `MAX_STOP_PING_DISTANCE_FT`.
4. *Window*: `valid_from` is the start of the earliest period from which every later period is served. Served in
   every period: null (no window). Not served in the last period: raise (today's stop missed on today's geometry is a
   threshold or data fault). Served, then not, then again: only the last stretch counts; the QA note lists any.
5. *Key*: a row applies to (`route`, `direction`, `stop_id`), so to every pattern of that direction (owner,
   2026-11-18; minor patterns are too sparse to bisect). A window starts on a geometry change, not on the day the
   buses moved. On route 8 it starts 13 days late (moved Monday 2025-08-04, geometry 2025-08-17), so real arrivals
   at the detour stops in those days are dropped. On route 66 it starts 1 to 2 days early (moved Monday 2025-09-29,
   geometry Saturday 2025-09-27 on 6662 and Sunday 2025-09-28 on 6665), so if the buses moved on the Monday, up to
   two weekend days of arrivals at stops not yet served are kept. Both move dates come from news coverage and
   segment medians (TODO item "Confirm the closure dates").
6. *Adapter*: in `pattern_join`, after the join gives each row its `rtdir`, a row whose (`route`, `rtdir`, `stpid`)
   has a window and whose run's `_service_date` (on the rows at this stage) is before `valid_from` is dropped as
   `stop_before_valid_from`. One reason per row; the stage's reasons sum to its `rows_in − rows_out`. The service
   date at this stage equals the final one when the run id ends in its date, as Mansueto ids are built (the column
   mapping note checked it on pid 6662); otherwise `_service_date` falls back to the Chicago date of the run's earliest
   row, which moves as rows drop, so the QA note counts runs without one (expected 0).
7. The raw-CSV and archive adapters are unchanged: they impute against today's geometry, which fits all 71 raw days
   and the archive days checked. Older days, and the stops served before 2024-09-03 that today's patterns lack,
   need dated geometry (TODO item "Historical pattern geometry from GTFS").
8. `scripts/route_run_level.py --source mansueto --no-validity`, `--write-validity`, then `--source mansueto` are run for
   routes 8, 65 and 66, and the QA note written.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `EPOCH_SLACK_DAYS` | 45 (existing, moved) | `notebooks/eda_routes_8_65_66.ipynb` 6.1: 38 added stops, all first seen 2024-09-03 | unknown; it only picks candidates, Method 3 decides |
| `VALIDITY_SAMPLE_DAYS` | `("2025-07-15", "2025-09-16", "2025-10-14", "2026-09-15")` | the notebook 6.2 Tuesdays from 2024-09-03 on; one inside every geometry period of the four pids | one weekday per period: a stop served only on some days of a period is judged by that day |
| `MAX_STOP_PING_DISTANCE_FT` | unknown | measure on 2026-09-15 (today's geometry on all four pids): the largest `nearest_ping_ft` over every stop of the four dominant patterns, rounded up to the next 100 ft. If any candidate on any sample day lies between that value and twice it, stop and report rather than choose | sets which candidates count as served |
| Validity windows | 38 candidates, ~30 to 36 with a window (estimate) | 2,127,091 arrivals at the candidates before each pid's last change | per stop, from the measurement |

New exclusion: `stop_before_valid_from` (Rule 2; this spec, the QA table and the `/qa` baseline carry it).

## Fixtures

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/mansueto_2025-10-14_routes8_65_66.parquet` | `trips_<pid>_full.parquet` for the 24 `getpatterns_ok` pids | `bus_stop_time` on Tuesday 2025-10-14, 11 columns verbatim | ~50,000 rows, ~0.55 MB (estimate; measure, then pin) | `scripts/build_mansueto_fixtures.py` `cut_one_day`, via `/fixture` |
| `tests/fixtures/mansueto_2025-12-02_routes65_66.parquet` | the 15 `getpatterns_ok` pids of routes 65 and 66 | Tuesday 2025-12-02 | ~30,000 rows, ~0.35 MB (estimate) | same |
| `tests/fixtures/getpatterns/getpatterns_<pid>.json` × 24 | Bus Tracker `getpatterns`, one pid per call | whole response | 24 files (add-only; needs `CTA_API_KEY`, 24 calls) | `/fixture` |
| `notebooks/routes_8_65_66_stop_validity.json` | full-history view (2.0 GB of parquets) and four raw day CSVs (~150 MB, estimate), local | Method 1–4 | 38 rows | `scripts/route_run_level.py --write-validity` |

Why these days: on 2025-10-14 route 66 eastbound is past its change, route 66 westbound is between its two, and
route 8 is between its two (a valid, a split and two mostly invalid directions); 2025-12-02 is after every change.
Route 65 shares detour stops with route 66 and has no window of its own. Both parquets hold the route 65 and 66 pids,
and `cta.mansueto.parquet_files_for_pid` reads every parquet in the directory for a pid with no file of its own, so
every view over these fixtures passes `start` and `end` for its day (naive Chicago time, `end` exclusive).

## Acceptance tests

`tests/test_stop_validity.py`; fixture-day views as `tests/test_views_mansueto.py` builds the route 3 one, each passing
`start` and `end` for its day (see Fixtures).

- [ ] `test_clean_trips_stop_validity_hand_built`: hand-built trips and pattern stops; route `r1` Eastbound patterns
      `p1` (a, b, c) and `p2` (b, c, d), `p3` Westbound (c), route `r2` Eastbound (c); window (`r1`, Eastbound, c)
      from 2025-09-27; run ids embed their date. Dropped as `stop_before_valid_from`: `p1` and `p2` arrivals at c on
      runs dated 2025-09-26, one of them at 00:30 Chicago on 2025-09-27. Kept: c on 2025-09-27, c on `p3`, c on `r2`,
      every other stop of the runs that lost c. A stop in no pattern is still `stop_not_in_pattern`; `pattern_join`
      reasons sum to `rows_in − rows_out`; `stop_validity=None` gives exactly the output without this spec.
- [ ] `test_stop_validity_from_pings_hand_built`: one pid, periods cut at 2025-08-17 and 2025-11-25 with three sample
      days; pings placed so distances are known to the foot (0.001° of latitude ≈ 364.8 ft), threshold passed in. s1
      served in all → `valid_from` null; s2 from period 2 → 2025-08-17; s3 only in period 3 → 2025-11-25; s4 in
      periods 1 and 3, not 2 → 2025-11-25; s5 not in period 3 → `ValueError`; a period with no sample day →
      `ValueError` from `geometry_periods`; `nearest_feet` equals the minimum of `straight_line_feet` over the points.
- [ ] `test_stop_validity_snapshot`: the committed JSON has 38 rows (11, 13, 8, 6 by `from_pid` 6662, 6665, 9368,
      9376), every `source` is `mansueto`, every non-null `valid_from` is the start of one of its pid's periods, and
      every row has a `nearest_ping_ft` per period. Expected from the ping map (estimate; measure, then pin): `18720` and `18721`
      (6662) null, and the 6665 Wells stops (`18803`, `6613`, `6614`, `5020`) from 2025-11-24.
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

- One source per day, the reader, the stop key's code (`specs/run-level-reader.md`).
- The raw-CSV and archive adapters; dated pattern stop tables from GTFS; stops served before 2024-09-03 that today's
  patterns lack (TODO item "Historical pattern geometry from GTFS").
- Windows per minor pattern; route 65 (no geometry change); routes beyond 8, 65 and 66 (Phase 2 ingestion).
- Waits, headways, any minimum-sample gate; event days; the route 65 retired-pid shortfall.
- A `bracket_gap_s` bound; refreshing committed getpatterns files.

## Decisions (owner)

- 2026-11-18: windows measured per stop against raw pings, not one day per pid (which would have dropped real
  arrivals at the route 66 east stop-id swaps, Chicago & Menard and Chicago & Waller, and at 6665's stops from
  530 W Grand west from 2025-09-28); minor patterns take their direction's window; route 8 in the 2025-10-14 fixture.
- 2026-11-19: no separate analysis view; the window is pattern metadata and the Mansueto adapter applies it (ADR-011).
  Earlier revisions: commit `61a2b4c` (options and evidence), `488b2bc` (the analysis view).

## Open questions

None. ADR-011 was accepted on 2026-11-19.
