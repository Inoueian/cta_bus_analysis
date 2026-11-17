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

Each has the evidence found so far, the options, a recommendation and what the spec changes on the answer.
Evidence marked "notebook" is a saved output of `notebooks/eda_routes_8_65_66.ipynb` (sections 6.1, 6.2, 7), read
2026-11-17; nothing was re-run. Street positions read off the 6.2 ping map are approximate.

### 1. Stored shape: long table or list row?

- At stake: ADR-003 says the stop-level view is one row per (`stop_id`, `route`, `direction`) holding a list. The
  spec makes the long arrivals table the working and stored form and derives the list row.
- Evidence: 71.5M Mansueto rows over about 600 keys is about 120,000 arrivals per list. A wait filtered by day type
  or holiday needs `service_date`, `calendar_flag`, `source` and `bracket_gap_s` per arrival, so the list row would
  carry eight parallel lists, not the four in Outputs. A nightly refresh appends rows to a long table; it rewrites lists.
- Options: (a) long table stored, list row derived on demand; (b) list row stored, as ADR-003 reads, with the four
  extra lists added to `stop_level_view`; (c) both stored.
- Recommendation: (a), with a short ADR amending ADR-003 (as ADR-008 did): sorted by key, the long table gives the
  same lookup, and every later spec filters per arrival.
- Spec change: (a) adds `/adr` to the implementation steps; (b) extends the `stop_level_view` schema and moves the
  CLI output to it.

### 2. Which stops get a window (merged with question 3: from which day)?

- At stake: the 45-day rule marks 38 stops as "added". An added stop that the buses did serve loses real arrivals;
  a detour stop left out keeps arrivals of buses that were on another street.
- Evidence (notebook 6.1, stop names; 6.2, ping map on 2024-07-16, 2025-07-15, 2025-09-16, 2025-10-14, 2026-09-15):
  - 6662 (66 east), 11 added: `18720` Chicago & Menard and `18721` Chicago & Waller replace `512` and `513` at the
    same two sequence positions, far west of the works: a stop-id swap, not a detour. The other 9 (Milwaukee &
    Carpenter to Orleans & Chicago) are the detour, and the 2025-10-14 pings run along them.
  - 6665 (66 west), 13 added: `18794` Chicago & Milwaukee (Blue Line) and `18802` Chicago & Noble are on Chicago
    Avenue, which the buses drove on every sampled day; neither replaces a dropped stop, so whether a stop stood
    there before 2024-09-03 is not known. Of the other 11, the 2025-10-14 westbound pings come south about half a
    mile west of where they do on 2026-09-15, so the Wells stops (`18803`, `6613`, `6614`, `5020`, and probably
    `769` Grand & Franklin) were not served until the second change (2025-11-24), while the stops from 530 W Grand
    west to Milwaukee & Carpenter probably were from the first (2025-09-28).
  - 9368 and 9376 (route 8), 8 and 6 added: all on Division and Milwaukee. On 2025-09-16 and 2025-10-14 the buses
    ran the first detour, east of Halsted, and passed none of them; the last change is the right day for all 14.
- Options: (a) as drafted: all 38, each from its pid's last change; (b) owner-reviewed list: remove the two id
  swaps, decide `18794` and `18802`, keep one day per pid; (c) measured per stop: `valid_from` is the first
  geometry period in which the dominant pid's raw pings pass within a named distance of the stop (one raw day per
  period, stop coordinates from getpatterns), which settles the swaps, the two Chicago Avenue stops and the split
  of 6665's block by one rule.
- Recommendation: (c). It replaces a judgment per stop with a measurement the QA note can show, and the JSON schema
  already holds a day per stop. Cost: one new threshold (`MAX_STOP_PING_DISTANCE_FT`, unknown; measure on stops
  present throughout, then name it), about five raw day files (37 MB each) and no extra getpatterns calls.
- Spec change: (b) pins a smaller row count in `test_stop_validity_snapshot`; (c) rewrites Method 2, adds the
  threshold row and an analytic test, and the row count becomes an estimate (~30 to 36). Under (a) or (b) the 6665
  rows from 2025-09-28 to 2025-11-23 at the stops west of Grand & Franklin are dropped although probably real.

### 3. Does a window measured on the dominant pattern apply to the minor patterns?

- At stake: geometry changes were bisected only for the four dominant pids; the minor ones have too few pings a day
  to bisect (a minor pattern can read 2.84 miles short of its length on a day).
- Evidence (notebook 7): on route 8 four minor patterns start or end inside the block (10951 and 9343 start at
  Division & Cherry; 10954 and 9250 end at Division & Hooker), so they have arrivals at these stops and their first
  or last stop is a validity stop. On route 66, 4357 and 4355 cross the block; 6661 and 6658 add 8 and 7 stops, none
  near it. Minor patterns are 13% to 18% of a direction's runs. The two directions of a route changed 0 to 2 days apart.
- Options: (a) key the window by (`route`, `direction`, `stop_id`) and apply it to every pattern, as drafted;
  (b) measure a day per minor pid; (c) apply it to the dominant pid only.
- Recommendation: (a). The likely error is a day or two; (c) leaves imputed arrivals from one run in six at the
  same stops, which shortens every headway there.
- Spec change: none for (a); (b) needs a measurement the notebook does not have and delays the spec; (c) changes
  the key of the table to `pid`.

### 4. Overlap days: does the archive always win?

- At stake: 25 days (2026-09-28 to 2026-10-27) are in both the archive (60 s fixes) and the raw CSVs (300 s).
- Evidence (`tests/fixtures/archive_2026-10-29_michigan.index.json` `known_gaps`): the archive lost the afternoon
  and evening of six consecutive days, 2026-10-12 to 2026-10-17 (from between 13:13 and 18:03 to midnight; "daily
  request limit hit; data unrecoverable"), and 11 minutes on 2026-10-22. The raw CSVs have whole days for four of
  the six (10-16 and 10-17 are missing there too). Sunday 2026-10-11 is short in both sources.
- Options: (a) archive whenever it has the (route, day), as drafted; the day keeps its `known_gap_day` flag;
  (b) raw CSV on a day whose archive gap is longer than a named duration; (c) raw CSV on any `known_gap_day`.
- Recommendation: (a) for this spec. No archive day can be ingested until the Foundation v2 item lands, so the
  stage drops nothing on real data yet; (b) is worth four afternoons and is better decided in the archive half,
  with both sources on disk. The QA note lists the overlap days flagged `known_gap_day`.
- Spec change: none for (a); (b) adds a threshold and a calendar lookup; (c) changes `SOURCE_PRIORITY` to a rule.

### 5. Is route 8 in a fixture?

- At stake: route 8 holds 14 of the 38 windows, the only two-direction stop that is not a terminal (Halsted Orange
  Line), and the four patterns that start or end inside a block (question 3). As drafted it is tested only by the
  hand-built cases and the QA note.
- Cost: about 20,000 rows (~0.22 MB, estimate) per day and 9 more getpatterns files (9 calls); `tests/fixtures/`
  is at 5.8 MB of 20.
- Options: (a) no route 8 fixture; (b) widen the 2025-10-14 file to all three routes (~50,000 rows, ~0.55 MB,
  estimate; still under 1 MB), leaving 2025-12-02 at routes 65 and 66; (c) a separate route 8 file.
- Recommendation: (b). On 2025-10-14 both route 8 directions are before their window, so the day then holds a
  direction that is valid (66 east), one that is not or is split (66 west) and two that are not (route 8).
- Spec change: (b) renames the fixture to `mansueto_2025-10-14_routes8_65_66.parquet`, raises getpatterns to 24
  files and adds route 8 assertions to `test_stop_arrivals_fixture_2025_10_14`.
