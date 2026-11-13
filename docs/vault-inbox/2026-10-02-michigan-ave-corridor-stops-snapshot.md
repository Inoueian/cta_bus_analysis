---
title: "Michigan Ave corridor stop list — 40 on-avenue stops (Roosevelt to Delaware)"
category: projects
project: cta-bus-analysis
tags: [michigan-ave, stpid, getpatterns, corridor-stops, roosevelt, delaware]
created: 2026-10-02
source: cta_bus_analysis/notebooks/michigan_ave_stops_snapshot.json
---

**40** unique Bus Tracker stops on downtown **Michigan Avenue** between **Roosevelt** and **Delaware** (northbound and southbound), after §4.5 side-street exclusions. Canonical ordered list: repo `notebooks/michigan_ave_stops_snapshot.json` (`patterns_fetched`: **97**).

## Endpoints (speed / segment anchors)

| End | Direction | `stpid` | `stpnm` |
|---|---|---|---|
| Roosevelt | Southbound | `1591` | Michigan & Roosevelt |
| Roosevelt | Northbound | `1580` | Michigan & Roosevelt |
| Delaware | Southbound | `1097` | Michigan & Delaware |
| Delaware | Northbound | `1128` | Michigan & Delaware/Walton |

Delaware pair matches DLSD southern family — **`lsd-express-segment-boundaries`**.

**Snapshot metadata quirk:** JSON `corridor.roosevelt_stpids` still includes `15362`, `17084` (Roosevelt-named **side-street** stops removed in §4.5). Use **`1591` / `1580`** as on-avenue south anchors for analysis.

## Corridor filter (notebook §4)

1. From deduped `getpatterns` catalog for all candidate-route PIDs.
2. Keep rows where `stpnm` contains **Michigan** (case-insensitive) **and** `lat` in **[41.865, 41.902]**, **or** `stpid` in Delaware anchors **`1097`**, **`1128`**.
3. Deduplicate by (`stpid`, `stpnm`, `lat`, `lon`); aggregate `routes`, `rtdirs`, `n_patterns`.

Pre-exclusion count: **51** stops.

## §4.5 exclusions (`EXCLUDE_CORRIDOR_STPIDS`)

Remove **11** stops: intersection / side-street stops not on Michigan Ave itself; notebook also excludes **13th St** (south of Roosevelt) and **Oak** (north of Delaware).

| `stpid` | Rationale (notebook intent) |
|---|---|
| `1592`, `1579` | Side-street at Michigan intersections |
| `15362`, `17084` | Roosevelt-named off-avenue (not `1591`/`1580`) |
| `4870`, `4884`, `74`, `4725`, `14482`, `1421`, `1129` | Side-street at Michigan intersections |

Post-exclusion: **51 → 40** stops. Policy lives in `notebooks/michigan_ave_stop_discovery.ipynb` §4.5; `exclude_stpids` **not** serialized in JSON today.

## Candidate routes vs corridor

- **19** system-map candidates in snapshot `candidate_routes` (includes **`10`**).
- **18** routes appear on at least one in-corridor stop in JSON `stops[].routes`.
- Route **`10`**: **no rows** in Mansueto `rt_to_pid.csv` → no PID, no parquet in v1 Mansueto path; see **`rt-to-pid-missing-parquet`** (routes absent from CSV). v1 speed work uses remaining Mansueto routes until route-10 refinement in repo TODO.

## Artifacts

| Path | Role |
|---|---|
| `notebooks/michigan_ave_stop_discovery.ipynb` | §1 PIDs; §2 `batch_pattern_stops` via `cta_api`; §4 filter; §4.5 exclude; §5 optional write |
| `notebooks/michigan_ave_stops_snapshot.json` | Frozen stop table + `corridor` lat band + `patterns_fetched` |

## Related

- michigan-ave-bus-lane-segment
- rt-to-pid-missing-parquet
- lsd-express-segment-boundaries
- cta-bus-tracker-api
