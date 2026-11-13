---
title: "Michigan Ave — segment view (per-trip corridor stops + speed gap fill)"
category: projects
project: cta-bus-analysis
tags: [michigan-ave, segment-view, speed_mph, mansueto, interpolation]
created: 2026-10-03
source: cta_bus_analysis/notebooks/michigan_ave_segment.py
---

Per-run table of **Michigan Ave corridor** stop visits for the **45 kept PIDs** in `notebooks/michigan_ave_kept_pids.json`, built from `data/mansueto/trips_{pid}_last30d.parquet` (**dlsd-cache-last30d-semantics**).

## Stop sequences

From `notebooks/michigan_ave_stops_snapshot.json` (**40** on-avenue stops):

| Direction | Sort |
|---|---|
| Northbound | latitude **ascending** (south → north) |
| Southbound | latitude **descending** (north → south) |

A stop with both directions in `rtdirs` appears in **both** sequences. Each kept PID uses the sequence matching its `rtdir`.

## Grain and columns

- **Grain:** one row per (`unique_trip_vehicle_day`, `stpid`) within a PID’s corridor span on that sequence.
- **Observed rows:** Mansueto `bus_stop_time` and `speed_mph` from the parquet (earliest time if duplicate stop rows).
- **Interpolated rows:** stop was in the trip’s **observed index span** (`i_min`…`i_max` on the sequence) but had **no** published row. `speed_mph` = mean of the nearest **observed** flanking speeds; `bus_stop_time` is **null**; `interpolated=True`.

Policy: per **`canonical-data-views`** and **`michigan-ave-pattern-endpoint-coverage`**, do **not** fabricate arrival times. This view only fills **`speed_mph`**, not `bus_stop_time`.

## Speed semantics

Filled and observed values use Mansueto **`speed_mph`** (ping-interval speed around the stop — **`mansueto-imputed-stop-times`**). They are **not** consecutive-stop implied mph. **Speed plots** (`notebooks/michigan_ave_speed_plots.ipynb`) use **observed** rows only; gap-filled rows have no `bus_stop_time`. Chart spec: **`michigan-ave-slow-hour-corridor-plots`**.

## Span limits (skipped stops vs not served)

Stops **outside** the trip’s observed min/max sequence index are **omitted** (bus did not traverse that part of the corridor on that run). A trip with **one** corridor hit emits **one** row (no padding).

**148 SB PID 6402:** after **`michigan-ave-6402-pattern-trim`**, trips typically end at Hubbard; stops south of the observed span (e.g. Monroe, Lake) are not re-inserted by gap fill.

## Repo artifacts

| Path | Role |
|---|---|
| `notebooks/michigan_ave_segment.py` | `direction_stop_sequences`, `interpolate_trip_corridor`, `build_michigan_segment_view`, `observed_speed_rows`, `hour_stop_speed_stats`, `kept_pid_cache_status`, `segment_view_report` |
| `notebooks/michigan_ave_speed_plots.ipynb` | Slow-hour corridor plots from `segment_view.parquet` — **`michigan-ave-slow-hour-corridor-plots`** |
| `notebooks/michigan_ave_segment_view.ipynb` | Cache preflight, build, report, write parquet |
| `data/michigan_ave/segment_view.parquet` | Gitignored output |

## Check (2026-10-03)

Run: `env/bin/python` + `kept_pid_cache_status` / `build_michigan_segment_view` / `segment_view_report` (same as `michigan_ave_segment_view.ipynb`). **45 / 45** `trips_{pid}_last30d.parquet` files present under `data/mansueto/`.

| Metric | Value |
|---|---|
| PIDs in view | **43** / 45 |
| Rows | **461,215** |
| Distinct trips | **37,651** |
| Interpolated row share | **13.15%** |
| Null `speed_mph` (observed / interpolated) | **0** / **0** |
| Backwards `bus_stop_time` vs `seq_index` (observed trips) | **137** |
| PID **6402** rows at trimmed stpids `1104`–`1106`, `18396` | **0** (pass) |

**Absent from view:** PIDs **14130**, **14132** (route **151** Northbound) — cache files exist; no corridor `stpid` rows in last30d parquets (investigate before speed plots).

**Backwards-time flag:** Many trips show non-monotonic observed times along the latitude sequence; likely mixes **~5 min GPS imputation** (`mansueto-imputed-stop-times`) with latitude ordering that is not identical to pattern `stop_sequence`. Use for QA, not as a hard drop rule until sampled.

**Note:** Building with a Python env **without** pyarrow produced an **empty** view while cache preflight still showed 45 / 45 files (`read_parquet` failures are swallowed in `build_michigan_segment_view`). Use project `env/` or install pyarrow before trusting an empty build.

## Related

- michigan-ave-bus-lane-segment
- michigan-ave-corridor-stops-snapshot
- michigan-ave-6402-pattern-trim
- mansueto-imputed-stop-times
- canonical-data-views
