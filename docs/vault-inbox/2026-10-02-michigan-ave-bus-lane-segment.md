---
title: "Michigan Ave downtown bus speed — Roosevelt to Delaware (bus lane baseline)"
category: projects
project: cta-bus-analysis
tags: [michigan-ave, bus-lane, speed, roosevelt, delaware, dedicated-lane]
created: 2026-10-02
source: null
---

Measure **current** bus travel time / implied speed on downtown **Michigan Avenue** from **Roosevelt** (south) through **Delaware** (north) before the new **northbound dedicated bus lane** (Roosevelt → **Wacker** only). Analysis corridor is longer than the lane footprint.

## Segment endpoints

| End | Role | Stop IDs (known) |
|---|---|---|
| Roosevelt | South anchor | SB **`1591`** Michigan & Roosevelt; NB **`1580`** Michigan & Roosevelt (on-avenue; see **`michigan-ave-corridor-stops-snapshot`**) |
| Delaware | North anchor (DLSD southern family) | NB entry **`1128`** Michigan & Delaware/Walton; SB exit **`1097`** Michigan & Delaware |

Same Delaware stops as DLSD express 146/147/143/148 — see vault **`lsd-express-segment-boundaries`**.

## Candidate routes (system map)

Fetch **all patterns** for these routes via Bus Tracker `getpatterns` (notebook `notebooks/michigan_ave_stop_discovery.ipynb`):

`1`, `2`, `3`, `4`, `X4`, `6`, `7`, `10`, `J14`, `26`, `28`, `125`, `126`, `143`, `146`, `147`, `148`, `151`, `157`

PIDs from Mansueto `rt_to_pid.csv`; `X4` / `J14` must match `rt` column exactly or notebook flags missing.

## Route eligibility (after discovery)

- **Include route** in speed analysis only if **median per-run time** on the Roosevelt–Delaware Michigan segment is **≥ 5 minutes** (excludes routes that only clip the corridor).

## Metrics and slices

- **Primary (v1 plots)**: slow-hour **corridor** charts — latitude vs minutes/mile at each stop, hours = 3 slowest per slice (Mon–Thu, Friday, weekend). Detail: **`michigan-ave-slow-hour-corridor-plots`**; notebook `notebooks/michigan_ave_speed_plots.ipynb`. Observed `speed_mph` only; DLSD-adjacent northern stops excluded from charts only.
- **Stats**: median, IQR, p95 min/mi slow tail (`60/q05(speed)`).
- **Day slices**: Mon–Thu; Friday; Sat–Sun.
- **Holiday gap**: weekday slices currently treat calendar weekdays as regular service — see vault **`cta-holiday-schedule-filtering`**.

## Data / repo

| Artifact | Role |
|---|---|
| `notebooks/michigan_ave_stop_discovery.ipynb` | §1 PIDs + parquet probe; §2 `getpatterns`; §4 corridor filter; §4.5 side-street exclusions; optional §5 snapshot write |
| `notebooks/michigan_ave_stops_snapshot.json` | **40** stops after §4.5; written when `WRITE_SNAPSHOT=True` — detail in **`michigan-ave-corridor-stops-snapshot`** |
| Mansueto `trips_<PID>_last30d.parquet` | Local cache for **45** kept PIDs (`scripts/cache_dlsd_parquets.py --source michigan`) |
| Segment view | Per-trip corridor stops + gap-filled `speed_mph` — **`michigan-ave-segment-view`** (`notebooks/michigan_ave_segment_view.ipynb` → `data/michigan_ave/segment_view.parquet`) |
| Speed plots | Slow-hour corridor plots — `notebooks/michigan_ave_speed_plots.ipynb`; **`michigan-ave-slow-hour-corridor-plots`** |

## Related

- michigan-ave-segment-view
- michigan-ave-6402-pattern-trim
- michigan-ave-pattern-endpoint-coverage
- michigan-ave-corridor-stops-snapshot
- lsd-express-segment-boundaries
- dlsd-rush-express-routes
- cta-bus-tracker-api
- cta-holiday-schedule-filtering
- canonical-data-views
