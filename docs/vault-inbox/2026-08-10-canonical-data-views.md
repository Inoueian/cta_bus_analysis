---
title: "Canonical data views for cta-bus-analysis (run-level, stop-level)"
category: projects
project: cta-bus-analysis
tags: [schema, data-model, run-level, stop-level, mansueto, parquet]
created: 2026-08-10
source: cta_bus_analysis/DECISIONS.md#ADR-003
---

Two derived views built from Mansueto `trips_<PID>_full.parquet`. Preserve Mansueto trip key as `run_id`; map source columns at ingestion (verified 2026-09-15 on route 66 / PID 6662 — see `parquet-verification-results`).

## Mansueto source columns (verified)

File: `trips_<PID>_full.parquet` (11 columns on PID 6662). PID list by route: `https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/rt_to_pid.csv`.

| Run-level column | Mansueto column | Notes |
|---|---|---|
| `run_id` | `unique_trip_vehicle_day` | 0 nulls; encodes route/pattern/vehicle/date (e.g. `666662.0********10852024-11-29`) |
| `route` | `rt` | string route number |
| `pattern_id` | `pid` | string; file is already per-PID |
| `stop_id` | `stpid` | CTA stop id; `p_stp_id` is pattern-stop composite `{pid}-{stpid}` |
| `stop_sequence_index` | `stop_sequence` | int64 |
| `arrival_time` | `bus_stop_time` | datetime64[ns] |
| `direction` | *(none)* | Not in parquet; join GTFS or pattern metadata when building run-level view |

Passthrough / optional: `vid` (vehicle), `speed_mph`, `seg_combined`, `typ` (all `S` on sample).

Ingestion rename only in derived views — do not mutate CloudFront source reads without documenting.

## Run-level view

- Grain: one row per (`run_id`, `stop_sequence_index`) — Mansueto has 0 duplicate (`run_id`, `stpid`) on PID 6662.
- Columns: `run_id`, `route`, `direction`, `pattern_id`, `stop_id`, `stop_sequence_index`, `arrival_time` (logical names after mapping above).
- Built by: union all Mansueto Pattern parquets, normalize column names.
- Used for: travel-time distribution (filter to one run, join two stops), time-series of average travel time by date.

## Stop-level view

- Grain: one row per (`stop_id`, `route`, `direction`).
- Columns: keys + `arrival_times` (ordered list of timestamps) + `pattern_ids` (parallel list, same length, per-timestamp Pattern label).
- Built by: group the run-level view; do NOT partition further by pattern in this view.
- Used for: wait-time distribution at a stop, dropdown lookups (route -> direction -> stop).

## Query -> view mapping

- Wait-time distribution -> stop-level.
- Travel-time distribution -> run-level.
- Direction-only destination (aggregate over downstream stops) -> run-level, filter to stops with `stop_sequence_index > origin_index` in the same run.
- Average travel time over calendar time -> run-level, groupby date.

## Constraints

- Mansueto column names verified 2026-09-15 (`scripts/verify_parquet.py`, route 66 PID 6662). Empirical date range on that file: 2022-05-31 through 2026-07-28.
- `direction` is not in Mansueto parquet; required for ADR-003 stop-level keys — derive before or during run-level materialization.
- Multiple Patterns collapse into one (route, direction) row in the stop-level view. Retained `pattern_id` label enables later per-pattern disaggregation without a rebuild.
- Both views refresh together whenever Mansueto data is pulled (upstream lag ~14 days — see `cta-stop-watch-freshness-check`).
- Runs where a stop is missing (bus skipped or ping loss) simply do not contribute a timestamp; do not fabricate.
