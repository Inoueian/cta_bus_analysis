# Spec: Stop-level view for routes 8, 65 and 66 from the run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-17  ·  TODO item: Phase 1, Now — "Build the stop-level view for routes 8, 65, & 66 (route → direction → stop_id → arrival-time list) by grouping the run-level view: the second ADR-003 view and the first consumer of the run-level columns; the spec must state how patterns pool per (route, direction) and that `bracket_gap_s` NaN from Mansueto means unknown, not zero. Measured inputs (`docs/2026-11-13-routes-8-65-66-eda.md`): the key needs `route` (19 stpids are served by two of the three routes); 7 terminal stpids are served in both directions; pooling takes the union of stops (78 against the dominant pattern's 69 on route 66 eastbound); stops inside a detour block need a validity window per source, which the spec states as a rule from `geometry_changes` and the 2024-09-03 stop-list switch (before that date the stops really served are dropped as `stop_not_in_pattern`; from it until the pattern took today's geometry the parquet has arrivals at stops the bus did not serve). The spec also names the routes 8, 65, 66 fixtures, which do not exist yet (`tests/fixtures/` holds Michigan, route 3 and PID 6410 cuts): the 23 pids on archive day 2026-10-29 are 1.97 MB as `ndjson.gz` (over the 1 MB budget, Rule 3; 0.39 to 0.78 MB per route) or 0.95 MB as parquet, so the format follows the Foundation v2 spec; a Mansueto cut that tests the validity window needs a day on each side of a geometry change. Spec: to write."
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
| Stop validity (new) | `notebooks/routes_8_65_66_stop_validity.json` | rows of `route`, `direction`, `stop_id`, `stop_name`, `source`, `valid_from` (ISO day), `from_pid`, `first_arrival_day` | built once from the full-history view (Method 2); committed, read by tests |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Stop arrivals + QA | `cta.stop_level.stop_arrivals(view, validity=None) -> (DataFrame, DataFrame)` | `STOP_ARRIVAL_COLUMNS`: `route`, `direction`, `stop_id`, `pattern_id`, `run_id`, `source`, `service_date`, `calendar_flag` str; `arrival_time` tz-aware UTC; `stop_sequence_index` int64; `bracket_gap_s` float64. Sorted by (`route`, `direction`, `stop_id`, `arrival_time`, `run_id`). QA: `["route"] + cta.qa.QA_COLUMNS`, stages `STAGES = ("source_overlap", "validity", "pool")` | one row per kept (run, stop) |
| Stop-level view | `cta.stop_level.stop_level_view(arrivals) -> DataFrame` | `route`, `direction`, `stop_id` str; `arrival_times` (list of tz-aware UTC timestamps, ascending); `pattern_ids`, `run_ids`, `sources` (lists parallel to it); `n_arrivals` int64 | one row per (`route`, `direction`, `stop_id`): the ADR-003 row |
| Validity table | `cta.stop_level.load_stop_validity(path=None) -> DataFrame`; `added_stop_validity(first_days, pid_file) -> DataFrame` | the JSON's rows; `valid_from` str | one row per (`route`, `direction`, `stop_id`, `source`) with a window |
| CLI | `scripts/route_stop_level.py` (`--write-validity`, `--source`, `--out-dir data/route_stop_level`) | arrivals as parquet per route and source, QA as CSV | thin; reads `data/route_run_level/` |
| `/qa` case | `cta.qa_baseline.FIXTURE_CASES["stop_level_routes65_66"]`, recorded in `tests/fixtures/qa_baseline.csv` | baseline rows | a new case, not a changed one |
| QA note | `docs/<date>-routes-8-65-66-stop-level-qa.md` (`/finding`) | per route and stage totals over both ingested sources | — |

## Method

Prior art to copy: `cta/michigan_ave_segment.py` `corridor_stops_from_view` (a view in, a table and a per-key QA
table out, one reason per row); `cta/qa.py` `qa_rows`; `tests/test_michigan_segment_from_view.py`
`test_corridor_stops_hand_built_qa`; CLI shape `scripts/route_run_level.py`.

Preparatory refactor: `scripts/route_run_level.py` `today_geometry_first_day` and `EPOCH_SLACK_DAYS` move to
`cta/stop_level.py`; the script imports them. No behaviour change (rule 7); `tests/test_route_run_level.py` is not edited.

1. **Key and pooling.** The key is (`route`, `direction`, `stop_id`), `direction` being the view's column (the
   getpatterns `rtdir`). Every pattern of a route and direction pools: the stops of a key set are the union over
   patterns, and each arrival keeps its `pattern_id` (ADR-003). A stop served in both directions is two keys; a stop
   served by two routes is one key per route. Nothing is deduplicated across patterns or runs.
2. **Validity table.** A stop is *added* to a pattern when its first Mansueto `service_date` is more than
   `EPOCH_SLACK_DAYS` after the pid's first (the rule of `scripts/route_run_level.py` `detour_stop_arrivals`).
   For each pid in `geometry_changes`, each added stop gets one row: `source = "mansueto"`, `valid_from` = the pid's
   `today_geometry_first_day` (6662 2025-09-27, 6665 2025-11-24, 9368 2025-11-25, 9376 2025-11-23). The row is keyed
   by the pid's route and direction, not by pid, so it applies to every pattern pooled into that key.
   `--write-validity` computes first days from `data/route_run_level/source=mansueto` and writes the JSON with stop names.
3. **Stage `source_overlap`.** Within a (`route`, `service_date`), only rows of the first source present in
   `SOURCE_PRIORITY` are kept; the rest are `superseded_source`. Without it the 25 days covered by both the archive
   and the raw CSVs would hold every bus twice.
4. **Stage `validity`.** A row whose (`route`, `direction`, `stop_id`, `source`) has a validity row and whose
   `service_date < valid_from` is dropped as `outside_stop_validity`. `mansueto_raw` and `archive` have no rows in
   the table: their arrivals are imputed by us against today's geometry, which fits all 71 raw days
   (`docs/2026-11-15-routes-8-65-66-run-level-qa.md`). `validity=None` loads the committed table; an empty frame disables the stage.
5. **Stage `pool`.** Rows with a null or empty `route`, `direction` or `stop_id` are dropped as `null_key`; the rest are
   sorted. `bracket_gap_s` is carried and never compared: NaN means unknown, not zero (playbook gotcha "`bracket_gap_s`
   NaN means unknown, not zero"); this spec sets no gap bound. `calendar_flag` is carried and nothing is dropped for it
   (playbook pattern "Flag a service date instead of filtering it").
6. Before 2024-09-03 the view has no arrivals at any stop inside a changed block (the stops then served are not in
   today's patterns, playbook gotcha "Mansueto stop lists do not follow the route the bus took"). Nothing is added
   for them; the QA note reports, per key with a validity row, the first service date with an arrival.
7. QA rows per route through `cta.qa.qa_rows`; a route in the input with no drops still has its three stage rows.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `EPOCH_SLACK_DAYS` | 45 (existing, moved) | `notebooks/eda_routes_8_65_66.ipynb` 6.1; gives 11 / 13 / 8 / 6 added stops on 6662 / 6665 / 9368 / 9376 | unknown; added stops all start 2024-09-03, 27 months after the pids' first day |
| `SOURCE_PRIORITY` | `("archive", "mansueto_raw", "mansueto")` | ADR-009: the archive is primary, the CSVs fill the hole; 60 s fixes against 300 s | reversing it changes the 25 overlap days only |
| Validity windows | 38 rows, `valid_from` as in Method 2 | 2,127,091 arrivals at these stops before those days on the four dominant pids (run-level QA note) | first change instead of last on 6665 (2025-09-28) keeps about two more months at 13 stops |

New exclusion: `outside_stop_validity` (Rule 2; this spec, the QA table and the `/qa` baseline carry it).

## Fixtures

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/mansueto_2025-10-14_routes65_66.parquet` | `trips_<pid>_full.parquet` for the 15 `getpatterns_ok` pids of routes 65 and 66 | `bus_stop_time` on Tuesday 2025-10-14, 11 columns verbatim | ~30,000 rows, ~0.35 MB (estimate; measure, then pin) | `scripts/build_mansueto_fixtures.py` `cut_one_day`, via `/fixture` |
| `tests/fixtures/mansueto_2025-12-02_routes65_66.parquet` | same | Tuesday 2025-12-02 | ~30,000 rows, ~0.35 MB (estimate) | same |
| `tests/fixtures/getpatterns/getpatterns_<pid>.json` × 15 | Bus Tracker `getpatterns`, one pid per call | whole response | ~15 files (add-only; needs `CTA_API_KEY`, 15 calls) | `/fixture` |
| `notebooks/routes_8_65_66_stop_validity.json` | full-history view (2.0 GB of parquets, rebuilt locally) | Method 2 | 38 rows | `scripts/route_stop_level.py --write-validity` |

Why these days: 2025-10-14 lies between the two route 66 windows (eastbound valid from 2025-09-27, westbound not
until 2025-11-24), 2025-12-02 after both. Route 65 is there because it shares detour stops with route 66. Follow-up,
not built here: an archive cut of the same pids for 2026-10-29, in the format the Foundation v2 spec chooses.

## Acceptance tests

`tests/test_stop_level.py`. The fixture-day view is built as `tests/test_views_mansueto.py` builds the route 3 one.

- [ ] `test_stop_arrivals_hand_built_pooling`: a hand-built view (columns exactly `RUN_LEVEL_COLUMNS`): route `r1`
      Eastbound patterns `p1` (stops a, b, c) and `p2` (b, c, d), route `r2` Eastbound serving b, terminal t in both
      directions of `r1`. Output: 4 stops for (`r1`, Eastbound); arrivals at b ascending with `p1` and `p2` interleaved;
      (`r2`, Eastbound, b) and both t keys separate; columns equal `STOP_ARRIVAL_COLUMNS`, identifiers str,
      `arrival_time` tz-aware UTC, a `mansueto` row's NaN `bracket_gap_s` still NaN.
- [ ] `test_stop_arrivals_validity_window`: validity row (`r1`, Eastbound, c, `mansueto`, 2025-09-27). Dropped: `p1`
      and `p2` arrivals at c on service date 2025-09-26, including one at 00:30 Chicago on 2025-09-27 whose
      `service_date` is 2025-09-26. Kept: the same stop on 2025-09-27, in Westbound, on `r2`, and a `mansueto_raw` row.
- [ ] `test_stop_arrivals_source_priority_and_qa`: `archive` and `mansueto_raw` rows on one (`r1`, day), raw only on
      another day and on `r2` that day: only the first raw set is `superseded_source`. QA has the three stages per
      route, reasons sum to `rows_in − rows_out` at each, and each stage's `rows_in` is the previous `rows_out`.
- [ ] `test_stop_level_view_lists`: on the hand-built arrivals, one row per key; the four lists have length
      `n_arrivals`; `arrival_times` ascending; `n_arrivals` sums to `len(arrivals)`; exploding gives the arrivals back.
- [ ] `test_stop_validity_snapshot`: the committed JSON has 38 rows (11, 13, 8, 6 by `from_pid` 6662, 6665, 9368,
      9376), every `source` is `mansueto`, and `valid_from` equals `today_geometry_first_day` of the pid file.
- [ ] `test_stop_arrivals_fixture_2025_10_14`: on that fixture, no arrival remains at the 13 (66, Westbound) validity
      stops, the 11 (66, Eastbound) ones have arrivals, `outside_stop_validity` is ~2,000 (estimate; measure, then
      pin) and 0 for route 65; fixture rows and bytes as pinned by `/fixture`.
- [ ] `test_stop_arrivals_fixture_2025_12_02`: `rows_out` equals the view's rows (nothing dropped at any stage);
      (66, Eastbound) has ~78 stops against 69 on pid 6662 (estimate, from the 2026-05 to 2026-07 window); at least
      one `stop_id` is a key under both route 65 and route 66 (~15, estimate).
- [ ] `test_baseline_matches_fixtures` (existing, `tests/test_qa_baseline.py`): passes with the new case recorded.

## Out of scope

- Wait times, headways, hour or day-type cells, any minimum-sample gate (the wait-time spec).
- Marking event days (2026-10-11) or changing `cta/calendar.py`; the retired-pid shortfall on route 65.
- Dropping or flagging anything in the run-level view; the 2,127,091 rows stay there.
- Archive ingestion, the archive fixture, `--source archive` (they follow the Foundation v2 spec).
- Routes other than 8, 65 and 66; inferring validity for a route with no `geometry_changes`.
- A `bracket_gap_s` bound; deduplicating bunched buses; refreshing committed getpatterns files.

## Open questions

1. **Stored shape.** ADR-003 says the stop-level view is one row per key with a list. This spec stores the long
   arrivals table and derives the list row on demand. If the stored artifact is the long table, is a short ADR
   amending ADR-003 (as ADR-008 did) wanted?
2. **Which stops are in the table.** The 45-day rule also catches the two stops swapped at the far west end of
   route 66 on 2024-09-03 (Chicago & Menard, Chicago & Waller) if they are among the 11 and 13; they are not on the
   detour and the buses may have served them throughout. Review the stop names in the JSON and say which to remove.
3. **6665's window.** Its geometry changed twice (9.45 miles from 2025-09-28, 9.36 from 2025-11-24). The rule takes
   the last change, as the measured 2,127,091 does. Is the first change enough for route 66 westbound?
4. **Minor patterns.** A window measured on the dominant pattern is applied to every pattern of its direction. Agreed?
5. **Overlap days.** Archive over raw CSV whenever both have a (route, day), even on an archive `known_gap_day`?
6. **Fixture routes.** Route 8 is in no fixture (its two-direction stop at Halsted Orange Line and its 14 validity
   stops are tested only through the hand-built cases and the QA note). Add a third day file for route 8?
