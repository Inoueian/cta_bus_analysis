# Spec: Analysis-ready run-level view for routes 8, 65 and 66

Status: draft
Owner: Satoru  ·  Date: 2026-11-17 (revised 2026-11-18: owner answers; measured stop windows; route 8 in the fixture; rescoped from "stop-level view" under ADR-011)  ·  TODO item: Phase 1, Now — "Analysis-ready run-level view for routes 8, 65, & 66 (ADR-011): one table, `RUN_LEVEL_COLUMNS` unchanged, from the per-source run-level views after two stages every Phase 1 consumer needs …" (full text in TODO.md; it replaces the item "Build the stop-level view for routes 8, 65, & 66", rescoped 2026-11-18)
Tags: `kind:spec source:mansueto source:archive stage:view topic:pattern-catalog topic:qa-table`

## Question

Which arrivals of routes 8, 65 and 66 can a wait, a travel time or a time series trust? The per-source run-level
views hold two kinds of row that none of them can: Mansueto arrivals at detour stops dated before the bus served them
(2,127,091 on the four dominant route 8 and 66 patterns), and the same bus twice on the 25 days both the archive and
the raw CSVs cover. This spec removes both, once, and states the stop key the wait-time spec groups by. It began as
the stop-level view; with the stop-level form a long table, that view was the run-level view filtered and re-sorted,
and both filters serve travel time too, so ADR-011 (Proposed) makes the filtered run-level view the one stored table
and defines the stop-level view as a grouping of it. Fixtures are Mansueto cuts, so this does not wait on the archive
v2 adapter (owner, 2026-11-17).

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Run-level views | any `cta.views.run_level_from_*`; on disk `data/route_run_level/source=<s>/…` (`scripts/route_run_level.py`) | `cta.views.RUN_LEVEL_COLUMNS` | one row per (run, stop); `bracket_gap_s` NaN on `mansueto` |
| Pid list | `notebooks/routes_8_65_66_pids.json` | `pids[].dominant`, `geometry_changes[]` (`pid`, `first_day_new`) | 24 `getpatterns_ok` pids, 7 dated changes on 4 pids |
| Pattern stops | `cta.bustracker.pattern_stops_table` (local cache) | `pid`, `stpid`, `stpnm`, `lat`, `lon` | stop coordinates for Method 3 |
| Raw day CSVs | `cta.mansueto_raw.fetch_day` / `read_day` for `VALIDITY_SAMPLE_DAYS` into `data/mansueto_raw/` | `POSITION_COLUMNS` (`pid`, `lat`, `lon`) | read for Method 3 only; three of the four days are before ADR-009's declared window and enter no view |
| Stop validity (new) | `notebooks/routes_8_65_66_stop_validity.json` | rows of `route`, `direction`, `stop_id`, `stop_name`, `from_pid`, `source`, `first_arrival_day`, `nearest_ping_ft` ({sample day: feet}), `valid_from` (ISO day or null) | 38 candidate stops; built once by Method 3; committed, read by tests |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Analysis view + QA | `cta.views.analysis_view(view, validity=None) -> (DataFrame, DataFrame)` | `RUN_LEVEL_COLUMNS` with their dtypes, unchanged; sorted as the run-level view (`service_date`, `pattern_id`, `run_id`, `stop_sequence_index`). QA: `["route"] + cta.qa.QA_COLUMNS`, stages `ANALYSIS_STAGES = ("source_overlap", "stop_validity")` | one row per kept (run, stop) |
| Stop key | `cta.views.STOP_KEY = ["route", "direction", "stop_id"]` | — | the grouping ADR-011 names as the stop-level view |
| Validity | `cta/stop_validity.py`: `geometry_periods(pid_file, pid)`, `stop_validity_from_pings(candidates, stops, pings, periods, max_ft)`, `load_stop_validity(path=None)` | periods: `pid`, `start` / `end_exclusive` (ISO or null), `sample_day`; the JSON's rows; the loader keeps rows with a `valid_from` | one row per period; per candidate stop |
| CLI | `scripts/route_analysis_view.py` (`--write-validity`, `--sources`, `--out-dir data/route_analysis_view`) | `route=<r>/year=<YYYY>.parquet` (year of `service_date`), QA as CSV | thin; reads `data/route_run_level/` |
| `/qa` case | `cta.qa_baseline.FIXTURE_CASES["analysis_view_2025_10_14"]`, recorded in `tests/fixtures/qa_baseline.csv` | baseline rows | a new case; `tests/test_qa_baseline.py` passes |
| Docs | README "Data Model" and `cta/__init__.py` module list name the analysis view and `cta.stop_validity`; the `scripts/route_run_level.py` docstring points here instead of "the stop-level spec" | — | only once ADR-011 is Accepted |
| QA note | `docs/<date>-routes-8-65-66-analysis-view-qa.md` (`/finding`) | stage totals per route and source; Method 3's distance table; first arrival per windowed key; overlap days flagged `known_gap_day` | — |

## Method

Prior art to copy: `cta/views.py` `mansueto_view_from_trips` (a view in, a view and a per-key QA table out);
`cta/michigan_ave_segment.py` `straight_line_feet`; `cta/qa.py` `qa_rows`;
`tests/test_michigan_segment_from_view.py` `test_corridor_stops_hand_built_qa`; CLI shape `scripts/route_run_level.py`.

Preparatory refactor: `scripts/route_run_level.py` `today_geometry_first_day` and `EPOCH_SLACK_DAYS` move to
`cta/stop_validity.py`; the script imports them. No behaviour change (rule 7); `tests/test_route_run_level.py` is not edited.

1. **Schema.** The output is the input's columns and dtypes, rows removed only by the two stages. A run that loses
   stops keeps its others; a travel time between two of them is unaffected.
2. **Stage `source_overlap`.** Within a (`route`, `service_date`), only rows of the first source present in
   `SOURCE_PRIORITY` are kept; the rest are `superseded_source`. The archive wins on its `known_gap_day`s too (owner,
   2026-11-18); preferring the raw CSV on the six afternoons lost 2026-10-12 to 2026-10-17 is for the archive half.
3. **Validity table** (`--write-validity`; a measured rule, owner 2026-11-18).
   a. *Candidates*: on the four pids in `geometry_changes`, a stop whose first Mansueto `service_date` is more than
      `EPOCH_SLACK_DAYS` after the pid's first (the rule of `detour_stop_arrivals`): 11 / 13 / 8 / 6 on 6662 / 6665 /
      9368 / 9376, 38 in all.
   b. *Periods*: `geometry_periods` cuts a pid's history at each of its `first_day_new` (first period open at the
      start, last open at the end). Its `sample_day` is the latest of `VALIDITY_SAMPLE_DAYS` inside it; a period
      without one raises, naming pid and period. Today: 6662 2025-09-16 / 2026-09-15; 6665 2025-09-16 / 2025-10-14 /
      2026-09-15; 9368 and 9376 2025-07-15 / 2025-10-14 / 2026-09-15.
   c. *Distance*: per candidate and period, `nearest_ping_ft` is the smallest `straight_line_feet` from the stop's
      getpatterns position to any ping of the candidate's pid on the sample day (null `lat`/`lon` skipped). The stop
      is served in the period when that is at most `MAX_STOP_PING_DISTANCE_FT`.
   d. *Window*: `valid_from` is the start of the earliest period from which every later period is served. Served in
      every period: null (no window). Not served in the last period: raise (today's stop missed on today's geometry
      is a threshold or data fault). A stop served, then not, then again keeps only the last stretch; the QA note
      lists any such stop.
   e. A row is keyed by (`route`, `direction`, `stop_id`), so it applies to every pattern of that direction (owner,
      2026-11-18; minor patterns are too sparse to bisect). A window starts on a geometry change, not on the day the
      buses moved: up to 13 days late on route 8 (moved 2025-08-04, geometry 2025-08-17), 2 on route 66.
4. **Stage `stop_validity`.** A row whose (`route`, `direction`, `stop_id`) has a window, with `source == "mansueto"`
   and `service_date < valid_from`, is dropped as `outside_stop_validity`. `mansueto_raw` and `archive` arrivals are
   imputed by us against today's geometry, which fits all 71 raw days (`docs/2026-11-15-routes-8-65-66-run-level-qa.md`).
   `validity=None` loads the committed table; an empty frame disables the stage.
5. **Stop key** (for the wait-time spec; nothing here groups by it). A stop of a route and direction pools every
   pattern serving it, the union of their stops, each arrival keeping its `pattern_id` (ADR-003, ADR-011). A stop in
   both directions is two keys; a stop on two routes is one key per route. Nothing is deduplicated.
6. Carried, never used to drop: `bracket_gap_s` (playbook gotcha "`bracket_gap_s` NaN means unknown, not zero") and
   `calendar_flag` (playbook pattern "Flag a service date instead of filtering it"). Before 2024-09-03 the view has no
   arrivals at the stops really served inside a changed block (playbook gotcha "Mansueto stop lists do not follow the
   route the bus took"); nothing is added for them.
7. QA rows per route through `cta.qa.qa_rows`; a route in the input with no drops still has both stage rows.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `EPOCH_SLACK_DAYS` | 45 (existing, moved) | `notebooks/eda_routes_8_65_66.ipynb` 6.1: 38 added stops, all first seen 2024-09-03 | unknown; it only picks candidates, Method 3c decides |
| `VALIDITY_SAMPLE_DAYS` | `("2025-07-15", "2025-09-16", "2025-10-14", "2026-09-15")` | the notebook 6.2 Tuesdays from 2024-09-03 on; one inside every geometry period of the four pids | one weekday per period: a stop served only on some days of a period is judged by that day |
| `MAX_STOP_PING_DISTANCE_FT` | unknown | measure on 2026-09-15 (today's geometry on all four pids): the largest `nearest_ping_ft` over every stop of the four dominant patterns, rounded up to the next 100 ft. If any candidate on any sample day lies between that value and twice it, stop and report rather than choose | sets which candidates count as served |
| `SOURCE_PRIORITY` | `("archive", "mansueto_raw", "mansueto")` | ADR-009: the archive is primary, the CSVs fill the hole; 60 s fixes against 300 s | reversing it changes the 25 overlap days only |
| Validity windows | 38 candidates, ~30 to 36 with a window (estimate) | 2,127,091 arrivals at the candidates before each pid's last change (run-level QA note) | per stop, from the measurement |

New exclusions: `superseded_source`, `outside_stop_validity` (Rule 2; this spec, the QA table and the `/qa` baseline carry them).

## Fixtures

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/mansueto_2025-10-14_routes8_65_66.parquet` | `trips_<pid>_full.parquet` for the 24 `getpatterns_ok` pids | `bus_stop_time` on Tuesday 2025-10-14, 11 columns verbatim | ~50,000 rows, ~0.55 MB (estimate; measure, then pin) | `scripts/build_mansueto_fixtures.py` `cut_one_day`, via `/fixture` |
| `tests/fixtures/mansueto_2025-12-02_routes65_66.parquet` | the 15 `getpatterns_ok` pids of routes 65 and 66 | Tuesday 2025-12-02 | ~30,000 rows, ~0.35 MB (estimate) | same |
| `tests/fixtures/getpatterns/getpatterns_<pid>.json` × 24 | Bus Tracker `getpatterns`, one pid per call | whole response | 24 files (add-only; needs `CTA_API_KEY`, 24 calls) | `/fixture` |
| `notebooks/routes_8_65_66_stop_validity.json` | full-history view (2.0 GB of parquets) and four raw day CSVs (~150 MB, estimate), local | Method 3 | 38 rows | `scripts/route_analysis_view.py --write-validity` |

Why these days: on 2025-10-14 route 66 eastbound is past its change, route 66 westbound is between its two, and
route 8 is between its two (a valid, a split and two mostly invalid directions); 2025-12-02 is after every change.
Route 65 shares detour stops with route 66. Follow-up, not built here: an archive cut of the 24 pids for
2026-10-29, in the format the Foundation v2 spec chooses.

## Acceptance tests

`tests/test_analysis_view.py`. Fixture-day views are built as `tests/test_views_mansueto.py` builds the route 3 one.

- [ ] `test_analysis_view_hand_built_schema`: a hand-built two-source view (columns exactly `RUN_LEVEL_COLUMNS`) on
      days with no overlap and an empty validity frame: output equals input (`pd.testing.assert_frame_equal`, dtypes
      included, `vehicle_id` kept, a `mansueto` row's NaN `bracket_gap_s` still NaN); QA has both stages per route with
      `rows_in == rows_out`.
- [ ] `test_analysis_view_stop_validity`: window (`r1`, Eastbound, c) from 2025-09-27; patterns `p1` (a, b, c) and
      `p2` (b, c, d). Dropped: `mansueto` arrivals at c on service date 2025-09-26 on both patterns, including one at
      00:30 Chicago on 2025-09-27 whose `service_date` is 2025-09-26. Kept: c on 2025-09-27, c in Westbound, c on
      `r2`, c from `mansueto_raw` on 2025-09-26, and every other stop of the runs that lost c.
- [ ] `test_analysis_view_source_overlap_and_qa`: `archive` and `mansueto_raw` rows on one (`r1`, day) whose
      `calendar_flag` is `known_gap_day`, raw only on another day and on `r2` that day: only the first raw set is
      `superseded_source`. Reasons sum to `rows_in − rows_out` at each stage, and `stop_validity` `rows_in` equals
      `source_overlap` `rows_out`.
- [ ] `test_stop_validity_from_pings_hand_built`: one pid, periods cut at 2025-08-17 and 2025-11-25 with three
      sample days; pings placed so each stop's distances are known to the foot (0.001° of latitude ≈ 364.8 ft), the
      threshold passed in. s1 served in all → `valid_from` null; s2 from period 2 → 2025-08-17; s3 only in period 3
      → 2025-11-25; s4 in periods 1 and 3, not 2 → 2025-11-25; s5 not in period 3 → `ValueError`; a period with no
      sample day → `ValueError` from `geometry_periods`.
- [ ] `test_stop_validity_snapshot`: the committed JSON has 38 rows (11, 13, 8, 6 by `from_pid` 6662, 6665, 9368,
      9376), every `source` is `mansueto`, every non-null `valid_from` is the start of one of its pid's periods, and
      every row has a `nearest_ping_ft` per period. Expected from the ping map, not measured: `18720` and `18721`
      (6662) null, and the 6665 Wells stops (`18803`, `6613`, `6614`, `5020`) from 2025-11-24.
- [ ] `test_analysis_view_fixture_2025_10_14`: on that fixture, a `STOP_KEY` whose `valid_from` is after 2025-10-14
      has no arrival left; one with a null or earlier `valid_from` keeps every arrival the view has;
      `outside_stop_validity` is ~4,000 (estimate; measure, then pin) on routes 8 and 66 and 0 on route 65;
      `superseded_source` is 0; fixture rows and bytes as pinned by `/fixture`.
- [ ] `test_analysis_view_fixture_2025_12_02`: nothing dropped at either stage; grouped by `STOP_KEY`, (66, Eastbound)
      has ~78 stops against 69 on pid 6662 (estimate, from the 2026-05 to 2026-07 window) and ~15 `stop_id`s are keys
      under both route 65 and route 66 (estimate).

## Out of scope

- A stored stop-sorted copy or list-per-stop table (ADR-011: only when a consumer measures the need).
- Wait times, headways, hour or day-type cells, any minimum-sample gate (the wait-time spec).
- Changing the per-source run-level views or their adapters; the 2,127,091 rows stay in `data/route_run_level/`.
- Marking event days (2026-10-11) or changing `cta/calendar.py`, including ADR-009's declared raw window; the
  retired-pid shortfall on route 65.
- Archive ingestion, the archive fixture, `--sources archive`, preferring the raw CSV on archive gap days.
- Measuring windows per minor pattern; routes other than 8, 65 and 66; a route with no `geometry_changes`.
- A `bracket_gap_s` bound; deduplicating bunched buses; refreshing committed getpatterns files.

## Decisions (owner, 2026-11-18)

The recommendations of the 2026-11-17 revision were accepted; its evidence and options are in commit `61a2b4c`.

1. Stored shape: long, not a list per stop; then (same day) not a separate table at all: ADR-011.
2. Which stops and from which day: measured per stop against raw pings (Method 3), not one day per pid, which would
   have dropped real arrivals at the route 66 east stop-id swaps (Chicago & Menard, Chicago & Waller) and at 6665's
   stops from 530 W Grand west from 2025-09-28.
3. Minor patterns take the window of their direction (Method 3e).
4. The archive wins on overlap days, `known_gap_day` included (Method 2).
5. Route 8 is in the 2025-10-14 fixture (Fixtures).

## Open questions

1. ADR-011 is Proposed. Accept it (or say what to change) before this spec goes to `ready`.
