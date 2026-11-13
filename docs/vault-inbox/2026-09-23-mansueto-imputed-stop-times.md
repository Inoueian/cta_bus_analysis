---
title: "Mansueto imputed bus_stop_time and speed_mph"
category: projects
project: cta-bus-analysis
tags: [mansueto, imputation, bus_stop_time, speed_mph, stop-watch, gps, dlsd]
created: 2026-09-23
source: notebooks/mansueto_imputation_investigation.ipynb
---

Mansueto StopWatch published parquets (`trips_<PID>_full.parquet`) store **imputed** stop arrival times, not raw GPS pings.

## Imputation model

Pipeline: [`../cta-stop-watch/cta-stop-watch/report_automation/interpolation.py`](../../cta-stop-watch/cta-stop-watch/report_automation/interpolation.py) (`interpolate_stoptime`).

1. Interleave pattern stops (`typ=="S"`) and bus locations (`typ=="B"`) ordered by `seg_combined`.
2. For each pair of consecutive pings with `data_time`, compute route distance `ping_dist` and elapsed time `ping_time_diff`.
3. Assign each stop time within that interval proportionally to accumulated distance along the route:

   `bus_stop_time = ping_time + ping_time_diff * (accumulated_distance / ping_dist)`

4. Stops before the first or after the last ping are extrapolated using implied segment speeds.

Published parquets contain **only** `typ=="S"` rows (stops); ping rows are dropped from CloudFront files.

## Raw ping timing

- Source: CTA Bus Tracker `getvehicles`, field `tmstmp` parsed as `%Y%m%d %H:%M` (minute resolution, no seconds).
- Ghost Bus scrape ~every 5 minutes; **not** clock-aligned to :00/:05.
- Effective resolution of imputed stop times is on the order of **~5 minutes** between GPS anchors.

## Column semantics (published parquet)

| Column | Meaning |
|--------|---------|
| `bus_stop_time` | Imputed arrival at stop |
| `speed_mph` | Speed of the **ping interval** enclosing the stop (not stop-to-stop leg speed) |
| `seg_combined` | Pattern segment index for ordering |
| `stop_sequence` | Stop index along pattern for the trip |

`speed_mph` is computed as `(ping_dist/1609) / (seconds/3600)`, then values **outside [1, 115] mph** are set to NaN and forward/back-filled (`interpolation.py`).

## DLSD analysis naming (routes 146/147)

- **`dlsd_minutes`**: `bus_stop_time` at DLSD exit minus entry for same `unique_trip_vehicle_day` / `pid`.
- **`implied_dlsd_mph`**: DLSD hop distance / `dlsd_minutes` — do not confuse with Mansueto `speed_mph`.

Shared module: `notebooks/dlsd_run_quality.py` (`build_dlsd_runs`, `load_dlsd_boundaries`).

## Recommended run filter

Structural **`analysis_ok`**:

- `exit_sequence == entry_sequence + 1`
- `exit_time > entry_time`
- both times non-null

Avoid arbitrary minute caps or posted speed limits as primary filters.

## Local cache

Last-30-day slices for 18 DLSD PIDs: `data/mansueto/trips_{pid}_last30d.parquet` via `scripts/cache_dlsd_parquets.py`. Window anchored on remote `max(bus_stop_time)` — see `dlsd-cache-last30d-semantics`.

Investigation notebook uses cache; full-history analysis uses CloudFront with `build_dlsd_runs(..., prefer_local=False)`.

## Related

- lsd-express-segment-boundaries
- dlsd-cache-last30d-semantics
- mansueto-processed-max-bus-stop-time
- canonical-data-views
- cta-stop-watch-dataset
