---
title: "DLSD express segment boundaries for routes 146 and 147"
category: projects
project: cta-bus-analysis
tags: [dlsd, route-146, route-147, express, stpid, dlsd_boundaries, stop-watch]
created: 2026-09-23
source: notebooks/dlsd_travel_time_146_147.ipynb section 2
---

Express **DLSD** segment = largest hop between consecutive **pattern** stops (`getpatterns`); classify when hop **> 10_000 ft** (~1.9 mi). Notebook builds `dlsd_boundaries[pid]` for Mansueto join on `pid`. Snapshot: `notebooks/dlsd_boundaries_snapshot.json`.

## Boundary pairs (route + direction)

| route | rtdir | entry stpid | entry name | exit stpid | exit name |
|-------|-------|-------------|------------|------------|-----------|
| 146 | Northbound | 1128 | Michigan & Delaware/Walton | 1155 | Inner Lake Shore Drive & Belmont |
| 146 | Southbound | 4867 | Lake Shore Drive & Belmont | 1097 | Michigan & Delaware |
| 147 | Northbound | 1128 | Michigan & Delaware/Walton | 4847 | Foster & Marine Drive |
| 147 | Southbound | 4846 | Foster & Marine Drive | 1097 | Michigan & Delaware |

- Route **146** DLSD run ~3.1 mi (downtown Michigan area to Belmont).
- Route **147** DLSD run ~5.5 mi (same southern anchor to Foster).
- Southern anchor shared: Michigan & Delaware area (`1128` NB entry / `1097` SB exit).
- Stop **names** use CTA “Lake Shore Drive” wording — not the DLSD acronym.

## Non-DLSD pattern

- PID **839** (route 147, Northbound, ~9.3k trips): origin **Sheridan & Foster** — north of DLSD; max hop ~1000 ft; exclude from DLSD duration analysis.

## Duration computation (§3+)

- Per run: `dlsd_minutes` = `bus_stop_time` at exit `stpid` minus entry `stpid` for same `unique_trip_vehicle_day` and `pid`.
- Filter: **`analysis_ok`** structural flags (consecutive entry/exit on pattern, ordered times, non-null) — see `mansueto-imputed-stop-times` and `notebooks/dlsd_run_quality.py`. Avoid primary reliance on `[1, 120]` minute caps.
- Imputation resolution ~5 min; optional reporting with `dlsd_minutes_bin` (5-minute floors).
- Speed: **`implied_dlsd_mph`** = hop miles / `dlsd_minutes`; Mansueto column `speed_mph` is ping-interval speed, not DLSD leg speed.

## Notebooks

- Main: `notebooks/dlsd_travel_time_146_147.ipynb`
- Imputation / quality: `notebooks/mansueto_imputation_investigation.ipynb`

## Related

- pid-trip-count-skew
- rt-to-pid-missing-parquet
- canonical-data-views
- cta-bus-tracker-api
- dlsd-cache-last30d-semantics
