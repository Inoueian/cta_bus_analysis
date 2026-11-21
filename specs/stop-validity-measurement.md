# Spec: Measured stop validity windows for routes 8 and 66

Status: draft
Owner: Satoru  ·  Date: 2026-11-21 (split out of `specs/mansueto-stop-validity.md`, which keeps the adapter half; the one-spec history is commits `61a2b4c`, `488b2bc`, `3887b46`)  ·  TODO item: Phase 1, Next — "Measure dated stop validity for routes 8 and 66 ([ADR-011](DECISIONS.md)): the parquet has an arrival at every stop of today's route 8 and 66 detours for every run from 2024-09-03 …" (full text in TODO.md)
Tags: `kind:spec source:mansueto stage:clean topic:pattern-catalog topic:thresholds`

## Question

The Mansueto parquet has an arrival at every stop of today's route 8 and 66 detours for every run from 2024-09-03,
though the buses reached those streets only in late 2025: 2,127,091 arrivals on the four dominant patterns, 5.9% to
18.6% of their rows in that period (`docs/2026-11-15-routes-8-65-66-run-level-qa.md`). A wait at those stops describes
another street, and a travel time ending there uses a time projected onto a road the bus was not on. A stop belongs to
a pattern from a date (ADR-011, point 3). This spec measures that date per stop against raw pings and commits it as
pattern metadata. It changes no view: `specs/mansueto-stop-validity.md` has the Mansueto adapter drop the earlier
arrivals, and reads the file this spec writes. It does not wait on the archive v2 adapter (owner, 2026-11-17).

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Mansueto run-level view, full history | `data/route_run_level/source=mansueto/…` (`scripts/route_run_level.py --source mansueto`) | `RUN_LEVEL_COLUMNS` | built without windows, which is the only kind until `specs/mansueto-stop-validity.md` lands; finds each stop's first arrival day |
| Pid list | `notebooks/routes_8_65_66_pids.json` | `pids[].dominant`, `geometry_changes[]` (`pid`, `first_day_new`) | 7 dated changes on 4 pids |
| Pattern stops | `cta.bustracker.pattern_stops_table` (local cache) | `pid`, `stpid`, `stpnm`, `lat`, `lon` | stop positions |
| Raw day CSVs | `cta.mansueto_raw.fetch_day` / `read_day` for `VALIDITY_SAMPLE_DAYS` into `data/mansueto_raw/` | `POSITION_COLUMNS` (`pid`, `lat`, `lon`) | read for the measurement only; three of the four days are before ADR-009's declared window and enter no view |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Stop validity | `notebooks/routes_8_65_66_stop_validity.json` | `route`, `direction`, `stop_id`, `stop_name`, `from_pid`, `source`, `first_arrival_day`, `nearest_ping_ft` ({sample day: feet}), `valid_from` (ISO day or null); strings except the feet | one row per candidate stop (38); committed |
| Measurement | `cta/stop_validity.py`: `geometry_periods(pid_file, pid) -> DataFrame`, `stop_validity_from_pings(candidates, stops, pings, periods, max_ft) -> DataFrame`, `load_stop_validity(path=None) -> DataFrame`; constants `EPOCH_SLACK_DAYS`, `VALIDITY_SAMPLE_DAYS`, `MAX_STOP_PING_DISTANCE_FT` | periods: `pid`, `start` / `end_exclusive` (ISO day strings or null), `sample_day`; `candidates`: `route`, `direction`, `stop_id`, `stop_name`, `from_pid`, `first_arrival_day`; `stops`: `pattern_stops_table`; `pings`: `read_day` output (`POSITION_COLUMNS`, the day in `data_date`); result and loader: the JSON's rows, the loader keeping those with a `valid_from` | one row per period; per candidate stop |
| Geometry helper | `cta/geo.py`: `straight_line_feet` (moved), `nearest_feet(lat, lon, lats, lons) -> float` | haversine feet, `EARTH_RADIUS_FEET` | one point against many |
| CLI | `scripts/route_run_level.py --write-validity` reads the view under `--out-dir`, writes the JSON, and refuses when `qa_mansueto.csv` holds a `stop_before_valid_from` row (none exists until the adapter spec lands; the guard keeps the measurement on an unwindowed view) | — | — |
| Docs | `cta/__init__.py` module list and CLAUDE.md's Layout paragraph name `stop_validity` and `geo` | — | — |
| QA note | `docs/<date>-stop-validity-windows.md` (`/finding`) | the distance table (`nearest_ping_ft` per candidate and period, the threshold and the largest distance over the dominant patterns' stops); windows; any served, then not, then served stop; first arrival per windowed key | — |

## Method

Prior art to copy: `scripts/route_run_level.py` `detour_stop_arrivals` (the candidates) and `today_geometry_first_day`
(the dated changes); `cta/mansueto_raw.py` `read_day` (pings); `tests/test_route_run_level.py` `test_detour_stop_arrivals`.

Preparatory refactor (no behaviour change, rule 7; no test edited; `/qa` shows no diff): `today_geometry_first_day` and
`EPOCH_SLACK_DAYS` move from `scripts/route_run_level.py` to `cta/stop_validity.py`; `straight_line_feet` and
`EARTH_RADIUS_FEET` move from `cta/michigan_ave_segment.py` to `cta/geo.py`. `scripts/route_run_level.py` and
`cta/michigan_ave_segment.py` import the moved names, so `rrl.today_geometry_first_day` (`tests/test_route_run_level.py`)
and `mas.straight_line_feet` (`tests/test_michigan_segment_from_view.py`) still resolve. The helper leaves
`michigan_ave_segment` because `specs/mansueto-stop-validity.md` makes `cta.views` import `cta.stop_validity`, and
`michigan_ave_segment` imports `cta.views`.

1. *Candidates*: on the four pids in `geometry_changes`, a stop whose first Mansueto `service_date` is more than
   `EPOCH_SLACK_DAYS` after the pid's first (the rule of `detour_stop_arrivals`): 11 / 13 / 8 / 6 on 6662 / 6665 /
   9368 / 9376, 38 in all (`notebooks/eda_routes_8_65_66.ipynb` 6.1). It reads days from `service_date` (a string), not
   `arrival_time`, which DuckDB's `.df()` returns without its zone (playbook gotcha "DuckDB returns tz-aware view
   timestamps as naive").
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
6. `scripts/route_run_level.py --write-validity` runs on the local full-history view and the QA note is written.
   To re-measure after another geometry change, rebuild the view without windows first (`--no-validity`, added by
   `specs/mansueto-stop-validity.md`; before it lands, any build is unwindowed).

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `EPOCH_SLACK_DAYS` | 45 (existing, moved) | `notebooks/eda_routes_8_65_66.ipynb` 6.1: 38 added stops, all first seen 2024-09-03 | unknown; it only picks candidates, Method 3 decides |
| `VALIDITY_SAMPLE_DAYS` | `("2025-07-15", "2025-09-16", "2025-10-14", "2026-09-15")` | the notebook 6.2 Tuesdays from 2024-09-03 on; one inside every geometry period of the four pids | one weekday per period: a stop served only on some days of a period is judged by that day |
| `MAX_STOP_PING_DISTANCE_FT` | unknown | measure on 2026-09-15 (today's geometry on all four pids): the largest `nearest_ping_ft` over every stop of the four dominant patterns, rounded up to the next 100 ft. If any candidate on any sample day lies between that value and twice it, stop and report rather than choose | sets which candidates count as served |
| Validity windows | 38 candidates, ~30 to 36 with a window (estimate) | 2,127,091 arrivals at the candidates before each pid's last change | per stop, from the measurement |

This spec adds no exclusion; `stop_before_valid_from` is `specs/mansueto-stop-validity.md`'s. A threshold in a Method
step above is a named constant of `cta/stop_validity.py` with its evidence in a trailing comment.

## Fixtures

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `notebooks/routes_8_65_66_stop_validity.json` | full-history view (2.0 GB of parquets) and four raw day CSVs (~150 MB, estimate), local | Method 1–4 | 38 rows | `scripts/route_run_level.py --write-validity` |

The other tests are hand-built. The parquet and `getpatterns` fixtures belong to `specs/mansueto-stop-validity.md`.

## Acceptance tests

`tests/test_stop_validity.py`.

- [ ] `test_stop_validity_from_pings_hand_built`: one pid, periods cut at 2025-08-17 and 2025-11-25 with three sample
      days; pings placed so distances are known to the foot (0.001° of latitude ≈ 364.8 ft), threshold passed in. s1
      served in all → `valid_from` null; s2 from period 2 → 2025-08-17; s3 only in period 3 → 2025-11-25; s4 in
      periods 1 and 3, not 2 → 2025-11-25; s5 not in period 3 → `ValueError`; a period with no sample day →
      `ValueError` from `geometry_periods`; `nearest_feet` equals the minimum of `straight_line_feet` over the points.
- [ ] `test_stop_validity_snapshot`: the committed JSON has 38 rows (11, 13, 8, 6 by `from_pid` 6662, 6665, 9368,
      9376), every `source` is `mansueto`, every non-null `valid_from` is the start of one of its pid's periods, and
      every row has a `nearest_ping_ft` per period. Expected from the ping map (estimate; measure, then pin): `18720`
      and `18721` (6662) null, and the 6665 Wells stops (`18803`, `6613`, `6614`, `5020`) from 2025-11-24.
- [ ] `test_write_validity_refuses_windowed_view`: a hand-built `qa_mansueto.csv` under `tmp_path` with a
      `stop_before_valid_from` row makes the guard raise `ValueError` naming the file; one without it passes. Nothing
      is written under `data/`.
- [ ] `test_baseline_matches_fixtures` (existing, `tests/test_qa_baseline.py`): passes with no case re-recorded. The
      refactor leaves every QA table identical, and this spec adds no pipeline stage, so its QA is the note's distance
      table and the snapshot test's invariants.

## Out of scope

- The adapter, the `stop_before_valid_from` reason, the views and their fixtures (`specs/mansueto-stop-validity.md`);
  one source per day (`specs/run-level-reader.md`).
- The raw-CSV and archive adapters, which impute against today's geometry (it fits all 71 raw days and the archive days
  checked); dated stop tables from GTFS; stops served before 2024-09-03 that today's patterns lack (TODO item
  "Historical pattern geometry from GTFS").
- Windows per minor pattern; route 65 (no geometry change); routes beyond 8, 65 and 66 (Phase 2 ingestion decides how
  geometry changes are detected and windows measured on every route).
- Automating the re-measurement; refreshing committed getpatterns files.

## Decisions (owner)

- 2026-11-18: windows measured per stop against raw pings, not one day per pid (which would have dropped real
  arrivals at the route 66 east stop-id swaps, Chicago & Menard and Chicago & Waller, and at 6665's stops from
  530 W Grand west from 2025-09-28); minor patterns take their direction's window.
- 2026-11-21: split from the adapter spec, so a "stop and report" on the distances does not hold the adapter's spec.

## Open questions

None. `MAX_STOP_PING_DISTANCE_FT` is unknown by design; Method 3 and the threshold table say how it is measured.
