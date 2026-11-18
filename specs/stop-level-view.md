# Spec: Stop-level view for routes 8, 65 and 66 from the run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-17 (revised 2026-11-18: owner answers; measured stop windows; route 8 in the fixture)  ·  TODO item: Phase 1, Now — "Build the stop-level view for routes 8, 65, & 66 (route → direction → stop_id → arrival-time list) by grouping the run-level view: the second ADR-003 view and the first consumer of the run-level columns; the spec must state how patterns pool per (route, direction) and that `bracket_gap_s` NaN from Mansueto means unknown, not zero. Measured inputs (`docs/2026-11-13-routes-8-65-66-eda.md`): the key needs `route` (19 stpids are served by two of the three routes); 7 terminal stpids are served in both directions; pooling takes the union of stops (78 against the dominant pattern's 69 on route 66 eastbound); stops inside a detour block need a validity window per source, which the spec states as a rule from `geometry_changes` and the 2024-09-03 stop-list switch (before that date the stops really served are dropped as `stop_not_in_pattern`; from it until the pattern took today's geometry the parquet has arrivals at stops the bus did not serve). The spec also names the routes 8, 65, 66 fixtures, which do not exist yet (`tests/fixtures/` holds Michigan, route 3 and PID 6410 cuts): the 23 pids on archive day 2026-10-29 are 1.97 MB as `ndjson.gz` (over the 1 MB budget, Rule 3; 0.39 to 0.78 MB per route) or 0.95 MB as parquet, so the format follows the Foundation v2 spec; a Mansueto cut that tests the validity window needs a day on each side of a geometry change. Spec: to write."
Tags: `kind:spec source:mansueto source:archive stage:view topic:pattern-catalog topic:qa-table`

## Question

At a stop, which buses of a route and direction arrived, and when? That list is what a rider's wait is computed
from (ADR-003), and nothing builds it yet. It is needed now because the wait-time, travel-time and direction-only
items of Phase 1 all inherit two rules this spec fixes: how patterns pool into (route, direction), and on which
dates an arrival at a detour stop is real. Scope decided with the owner on 2026-11-17: fixtures are Mansueto cuts,
so this does not wait on the archive v2 adapter; the archive fixture is a named follow-up.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Run-level view | any `cta.views.run_level_from_*`; on disk `data/route_run_level/source=<s>/…` (`scripts/route_run_level.py`) | `cta.views.RUN_LEVEL_COLUMNS` | one row per (run, stop); `bracket_gap_s` NaN on `mansueto` |
| Pid list | `notebooks/routes_8_65_66_pids.json` | `pids[].dominant`, `geometry_changes[]` (`pid`, `first_day_new`) | 24 `getpatterns_ok` pids, 7 dated changes on 4 pids |
| Pattern stops | `cta.bustracker.pattern_stops_table` (local cache) | `pid`, `stpid`, `stpnm`, `lat`, `lon` | stop coordinates for Method 2 |
| Raw day CSVs | `cta.mansueto_raw.fetch_day` / `read_day` for `VALIDITY_SAMPLE_DAYS` into `data/mansueto_raw/` | `POSITION_COLUMNS` (`pid`, `lat`, `lon`) | read for Method 2 only; three of the four days are before ADR-009's declared window and do not enter any view |
| Stop validity (new) | `notebooks/routes_8_65_66_stop_validity.json` | rows of `route`, `direction`, `stop_id`, `stop_name`, `from_pid`, `source`, `first_arrival_day`, `nearest_ping_ft` ({sample day: feet}), `valid_from` (ISO day or null) | 38 candidate stops; built once by Method 2; committed, read by tests |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Stop arrivals + QA | `cta.stop_level.stop_arrivals(view, validity=None) -> (DataFrame, DataFrame)` | `STOP_ARRIVAL_COLUMNS`: `route`, `direction`, `stop_id`, `pattern_id`, `run_id`, `source`, `service_date`, `calendar_flag` str; `arrival_time` tz-aware UTC; `stop_sequence_index` int64; `bracket_gap_s` float64. Sorted by (`route`, `direction`, `stop_id`, `arrival_time`, `run_id`). QA: `["route"] + cta.qa.QA_COLUMNS`, stages `STAGES = ("source_overlap", "validity", "pool")` | one row per kept (run, stop): the stored stop-level form |
| List row | `cta.stop_level.stop_level_view(arrivals) -> DataFrame` | `route`, `direction`, `stop_id` str; `arrival_times` (list of tz-aware UTC timestamps, ascending); `pattern_ids`, `run_ids`, `sources` (lists parallel to it); `n_arrivals` int64 | one row per (`route`, `direction`, `stop_id`), derived on demand, not stored |
| Validity | `geometry_periods(pid_file, pid)`, `stop_validity_from_pings(candidates, stops, pings, periods)`, `load_stop_validity(path=None)` in `cta.stop_level` | periods: `pid`, `start` (ISO or null), `end_exclusive` (ISO or null), `sample_day`; the JSON's rows; the loader keeps rows with a `valid_from` | one row per period; per candidate stop |
| CLI | `scripts/route_stop_level.py` (`--write-validity`, `--source`, `--out-dir data/route_stop_level`) | arrivals as parquet per route and source, QA as CSV | thin; reads `data/route_run_level/` |
| `/qa` case | `cta.qa_baseline.FIXTURE_CASES["stop_level_2025_10_14"]`, recorded in `tests/fixtures/qa_baseline.csv` | baseline rows | a new case; `tests/test_qa_baseline.py` passes |
| ADR | DECISIONS.md via `/adr`, amending ADR-003 (shape of ADR-008) | — | the stored stop-level form is the long table sorted by key; the list row is derived |
| QA note | `docs/<date>-routes-8-65-66-stop-level-qa.md` (`/finding`) | stage totals per route and source; Method 2's distance table; first arrival per windowed key; overlap days flagged `known_gap_day` | — |

## Method

Prior art to copy: `cta/michigan_ave_segment.py` `corridor_stops_from_view` (a view in, a table and a per-key QA
table out, one reason per row) and `straight_line_feet`; `cta/qa.py` `qa_rows`;
`tests/test_michigan_segment_from_view.py` `test_corridor_stops_hand_built_qa`; CLI shape `scripts/route_run_level.py`.

Preparatory refactor: `scripts/route_run_level.py` `today_geometry_first_day` and `EPOCH_SLACK_DAYS` move to
`cta/stop_level.py`; the script imports them. No behaviour change (rule 7); `tests/test_route_run_level.py` is not edited.

1. **Key and pooling.** The key is (`route`, `direction`, `stop_id`), `direction` being the view's column (the
   getpatterns `rtdir`). Every pattern of a route and direction pools: the stops of a key are the union over
   patterns, and each arrival keeps its `pattern_id` (ADR-003). A stop served in both directions is two keys; a stop
   served by two routes is one key per route. Nothing is deduplicated across patterns or runs.
2. **Validity table** (`--write-validity`; the owner chose a measured rule, 2026-11-18).
   a. *Candidates*: on the four pids in `geometry_changes`, a stop whose first Mansueto `service_date` is more than
      `EPOCH_SLACK_DAYS` after the pid's first (the rule of `detour_stop_arrivals`): 11 / 13 / 8 / 6 on 6662 / 6665 /
      9368 / 9376, 38 in all.
   b. *Periods*: `geometry_periods` cuts a pid's history at each of its `first_day_new` (the first period open at the
      start, the last open at the end). Its `sample_day` is the latest of `VALIDITY_SAMPLE_DAYS` inside it; a period
      without one raises, naming the pid and period. Today: 6662 2025-09-16 / 2026-09-15; 6665 2025-09-16 /
      2025-10-14 / 2026-09-15; 9368 and 9376 2025-07-15 / 2025-10-14 / 2026-09-15.
   c. *Distance*: per candidate and period, `nearest_ping_ft` is the smallest `straight_line_feet` from the stop's
      getpatterns position to any ping of the candidate's pid on the sample day (rows with null `lat`/`lon` skipped).
      The stop is served in the period when that is at most `MAX_STOP_PING_DISTANCE_FT`.
   d. *Window*: `valid_from` is the start of the earliest period from which every later period is served. Served in
      every period: null (no window; its arrivals are kept). Not served in the last period: raise (today's stop
      missed on today's geometry is a threshold or data fault). A stop served, then not, then again keeps only the
      last stretch; the QA note lists any such stop.
   e. A row is keyed by its pid's route and direction, so it applies to every pattern pooled into the key (owner,
      2026-11-18; minor patterns are too sparse to bisect). The window starts on a geometry change, not on the day
      the buses moved: up to 13 days late on route 8 (moved 2025-08-04, geometry 2025-08-17), 2 on route 66.
3. **Stage `source_overlap`.** Within a (`route`, `service_date`), only rows of the first source present in
   `SOURCE_PRIORITY` are kept; the rest are `superseded_source`. The archive wins on its `known_gap_day`s too (owner,
   2026-11-18); preferring the raw CSV on the six afternoons lost 2026-10-12 to 2026-10-17 is for the archive half.
4. **Stage `validity`.** A row whose (`route`, `direction`, `stop_id`) has a window, with `source == "mansueto"` and
   `service_date < valid_from`, is dropped as `outside_stop_validity`. `mansueto_raw` and `archive` arrivals are
   imputed by us against today's geometry, which fits all 71 raw days (`docs/2026-11-15-routes-8-65-66-run-level-qa.md`).
   `validity=None` loads the committed table; an empty frame disables the stage.
5. **Stage `pool`.** Rows with a null or empty `route`, `direction` or `stop_id` are dropped as `null_key`; the rest
   are sorted. `bracket_gap_s` is carried and never compared (playbook gotcha "`bracket_gap_s` NaN means unknown, not
   zero"); `calendar_flag` is carried and nothing is dropped for it (playbook pattern "Flag a service date instead of
   filtering it").
6. Before 2024-09-03 the view has no arrivals at the stops really served inside a changed block (playbook gotcha
   "Mansueto stop lists do not follow the route the bus took"). Nothing is added for them.
7. QA rows per route through `cta.qa.qa_rows`; a route in the input with no drops still has its three stage rows.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `EPOCH_SLACK_DAYS` | 45 (existing, moved) | `notebooks/eda_routes_8_65_66.ipynb` 6.1: 38 added stops, all first seen 2024-09-03 | unknown; it only picks candidates, Method 2c decides |
| `VALIDITY_SAMPLE_DAYS` | `("2025-07-15", "2025-09-16", "2025-10-14", "2026-09-15")` | the notebook 6.2 Tuesdays from 2024-09-03 on; one inside every geometry period of the four pids | one weekday per period: a stop served only on some days of a period is judged by that day |
| `MAX_STOP_PING_DISTANCE_FT` | unknown | measure on 2026-09-15 (today's geometry on all four pids): the largest `nearest_ping_ft` over every stop of the four dominant patterns, rounded up to the next 100 ft. If any candidate on any sample day lies between that value and twice it, stop and report rather than choose | sets which candidates count as served |
| `SOURCE_PRIORITY` | `("archive", "mansueto_raw", "mansueto")` | ADR-009: the archive is primary, the CSVs fill the hole; 60 s fixes against 300 s | reversing it changes the 25 overlap days only |
| Validity windows | 38 candidates, ~30 to 36 with a window (estimate) | 2,127,091 arrivals at the candidates before each pid's last change (run-level QA note) | per stop, from the measurement |

New exclusion: `outside_stop_validity` (Rule 2; this spec, the QA table and the `/qa` baseline carry it).

## Fixtures

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/mansueto_2025-10-14_routes8_65_66.parquet` | `trips_<pid>_full.parquet` for the 24 `getpatterns_ok` pids | `bus_stop_time` on Tuesday 2025-10-14, 11 columns verbatim | ~50,000 rows, ~0.55 MB (estimate; measure, then pin) | `scripts/build_mansueto_fixtures.py` `cut_one_day`, via `/fixture` |
| `tests/fixtures/mansueto_2025-12-02_routes65_66.parquet` | the 15 `getpatterns_ok` pids of routes 65 and 66 | Tuesday 2025-12-02 | ~30,000 rows, ~0.35 MB (estimate) | same |
| `tests/fixtures/getpatterns/getpatterns_<pid>.json` × 24 | Bus Tracker `getpatterns`, one pid per call | whole response | 24 files (add-only; needs `CTA_API_KEY`, 24 calls) | `/fixture` |
| `notebooks/routes_8_65_66_stop_validity.json` | full-history view (2.0 GB of parquets) and four raw day CSVs (~150 MB, estimate), local | Method 2 | 38 rows | `scripts/route_stop_level.py --write-validity` |

Why these days: on 2025-10-14 route 66 eastbound is past its change, route 66 westbound is between its two, and
route 8 is between its two (a valid, a split and two mostly invalid directions); 2025-12-02 is after every change.
Route 65 shares detour stops with route 66. Follow-up, not built here: an archive cut of the 24 pids for
2026-10-29, in the format the Foundation v2 spec chooses.

## Acceptance tests

`tests/test_stop_level.py`. Fixture-day views are built as `tests/test_views_mansueto.py` builds the route 3 one.

- [ ] `test_stop_arrivals_hand_built_pooling`: a hand-built view (columns exactly `RUN_LEVEL_COLUMNS`): route `r1`
      Eastbound patterns `p1` (stops a, b, c) and `p2` (b, c, d), route `r2` Eastbound serving b, terminal t in both
      directions of `r1`. Output: 4 stops for (`r1`, Eastbound); arrivals at b ascending with `p1` and `p2` interleaved;
      (`r2`, Eastbound, b) and both t keys separate; columns equal `STOP_ARRIVAL_COLUMNS`, identifiers str,
      `arrival_time` tz-aware UTC, a `mansueto` row's NaN `bracket_gap_s` still NaN. `stop_level_view` on it: one row
      per key, the four lists of length `n_arrivals`, `arrival_times` ascending, exploding gives the arrivals back.
- [ ] `test_stop_arrivals_validity_window`: window (`r1`, Eastbound, c) from 2025-09-27. Dropped: `p1` and `p2`
      `mansueto` arrivals at c on service date 2025-09-26, including one at 00:30 Chicago on 2025-09-27 whose
      `service_date` is 2025-09-26. Kept: c on 2025-09-27, c in Westbound, c on `r2`, c from `mansueto_raw` on 2025-09-26.
- [ ] `test_stop_arrivals_source_priority_and_qa`: `archive` and `mansueto_raw` rows on one (`r1`, day) whose
      `calendar_flag` is `known_gap_day`, raw only on another day and on `r2` that day: only the first raw set is
      `superseded_source`. QA has the three stages per route, reasons sum to `rows_in − rows_out` at each, and each
      stage's `rows_in` is the previous `rows_out`.
- [ ] `test_stop_validity_from_pings_hand_built`: one pid, periods cut at 2025-08-17 and 2025-11-25 with three
      sample days; pings placed so each stop's distances are known to the foot (0.001° of latitude ≈ 364.8 ft), with
      the threshold passed in. s1 served in all → `valid_from` null; s2 from period 2 → 2025-08-17; s3 only in period 3
      → 2025-11-25; s4 in periods 1 and 3, not 2 → 2025-11-25; s5 not in period 3 → `ValueError`; a period with no
      sample day → `ValueError` from `geometry_periods`.
- [ ] `test_stop_validity_snapshot`: the committed JSON has 38 rows (11, 13, 8, 6 by `from_pid` 6662, 6665, 9368,
      9376), every `source` is `mansueto`, every non-null `valid_from` is the start of one of its pid's periods, and
      every row has a `nearest_ping_ft` per period. Expected from the ping map, not measured: `18720` and `18721`
      (6662) null, and the 6665 Wells stops (`18803`, `6613`, `6614`, `5020`) from 2025-11-24.
- [ ] `test_stop_arrivals_fixture_2025_10_14`: on that fixture, a key whose `valid_from` is after 2025-10-14 has no
      arrival left; a key with a null or earlier `valid_from` keeps every arrival the view has; `outside_stop_validity`
      is ~4,000 (estimate; measure, then pin) on routes 8 and 66 and 0 on route 65; the stop named Halsted Orange Line
      Station is a key under both route 8 directions; fixture rows and bytes as pinned by `/fixture`.
- [ ] `test_stop_arrivals_fixture_2025_12_02`: `rows_out` equals the view's rows (nothing dropped at any stage);
      (66, Eastbound) has ~78 stops against 69 on pid 6662 (estimate, from the 2026-05 to 2026-07 window); at least
      one `stop_id` is a key under both route 65 and route 66 (~15, estimate).

## Out of scope

- Wait times, headways, hour or day-type cells, any minimum-sample gate (the wait-time spec).
- Marking event days (2026-10-11) or changing `cta/calendar.py`, including ADR-009's declared raw window; the
  retired-pid shortfall on route 65.
- Dropping or flagging anything in the run-level view; the 2,127,091 rows stay there.
- Archive ingestion, the archive fixture, `--source archive`, preferring the raw CSV on archive gap days.
- Measuring windows per minor pattern; routes other than 8, 65 and 66; a route with no `geometry_changes`.
- A `bracket_gap_s` bound; deduplicating bunched buses; refreshing committed getpatterns files.

## Decisions (owner, 2026-11-18)

The recommendations of the 2026-11-17 revision were accepted; its evidence and options are in commit `61a2b4c`.

1. Stored shape: the long arrivals table; the list row is derived; an ADR amends ADR-003 (Outputs).
2. Which stops and from which day: measured per stop against raw pings (Method 2). This replaces the draft's
   one day per pid, which would have dropped real arrivals at the two route 66 east stop-id swaps (Chicago & Menard,
   Chicago & Waller) and at 6665's stops from 530 W Grand west from 2025-09-28.
3. Minor patterns take the window of their direction (Method 2e).
4. The archive wins on overlap days, `known_gap_day` included (Method 3).
5. Route 8 is in the 2025-10-14 fixture (Fixtures).

## Open questions

None.
