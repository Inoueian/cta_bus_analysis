# Legacy Michigan Ave segment view check: 461,215 rows, 37,651 trips, 43 of 45 kept PIDs (measured 2026-10-03)

Tags: `kind:qa source:mansueto stage:view topic:qa-table`

Migrated 2026-11-13 from vault `michigan-ave-segment-view` (file dated 2026-10-02, check run 2026-10-03).
It records what the legacy builder `cta.michigan_ave_segment.build_michigan_segment_view` does and the one
check run on it. That builder is deprecated: it reads Mansueto parquets directly and carries ping-interval
`speed_mph` (rule 6). `corridor_stops_from_view` and `corridor_segment_speeds` replace it (ADR-010,
`specs/michigan-segment-from-view.md`). Keep this note for the baseline numbers and for the TODO item on
backwards times. Nothing was re-run for the migration.

## Measurement

`kept_pid_cache_status`, `build_michigan_segment_view` and `segment_view_report`, as
`notebooks/michigan_ave_segment_view.ipynb` runs them, on `data/mansueto/trips_<pid>_last30d.parquet` for
the 45 kept PIDs of `notebooks/michigan_ave_kept_pids.json`. All 45 cache files were present. The window
is 2026-06-28 to 2026-07-28 (see Corrections).

| Metric | Value |
|---|---|
| PIDs in the view | 43 of 45 |
| Rows | 461,215 |
| Distinct trips | 37,651 |
| Interpolated row share | 13.15% |
| Null `speed_mph`, observed / interpolated | 0 / 0 |
| Trips with `bus_stop_time` running backwards against `seq_index` | 137 |
| PID 6402 rows at the trimmed stops 1104, 1105, 1106, 18396 | 0 (pass) |
| PIDs absent from the view | 14130, 14132 |

## What the legacy view is

- Stop sequences come from `notebooks/michigan_ave_stops_snapshot.json` (40 on-avenue stops):
  Northbound sorted by latitude ascending, Southbound descending. A stop serving both directions is in
  both. Each kept PID uses the sequence of its `rtdir` (`direction_stop_sequences`).
- Grain: one row per (`unique_trip_vehicle_day`, `stpid`) within the trip's observed span on that sequence.
- Observed rows carry Mansueto `bus_stop_time` and `speed_mph`, the earliest time when a stop repeats.
- Interpolated rows (`interpolated=True`) are stops inside the trip's observed index span with no
  published row. Their `speed_mph` is the mean of the nearest observed speeds on either side and their
  `bus_stop_time` is null. Arrival times are never fabricated.
- Stops outside the observed span are omitted: the bus did not cover that part of the corridor on that
  run. A trip with one corridor hit gives one row. For PID 6402 (148 SB, hand-trimmed to end at
  Hubbard) the stops south of the span are therefore not re-inserted.
- The speed plots (`notebooks/michigan_ave_speed_plots.ipynb`) use observed rows only
  (`observed_speed_rows`).
- Output: `data/michigan_ave/segment_view.parquet`, gitignored.

## Facts confirmed

- The 137 backwards trips were not sampled. The vault's reading was a mix of ~5-minute imputation and a
  latitude order that differs from pattern order; it was to be used for QA, not as a drop rule. The second
  cause has since been shown on the archive (route 4 NB PID 25899's loop off Michigan, playbook gotcha
  "Mansueto imputed times can run backwards along a pattern"). The per-pid count split by cause is still
  open (TODO.md, Michigan Ave, "Segment-view QA").
- A build in a Python environment without pyarrow returned an empty view while the cache preflight still
  showed 45 of 45 files, because the builder swallows `read_parquet` errors (playbook gotcha).

## Corrections

- The vault note says PIDs 14130 and 14132 are route 151 Northbound. They are route 157, labelled
  Westbound and Eastbound in `notebooks/michigan_ave_kept_pids.json`. The legacy builder has no sequence
  for those labels and skipped them; that is why they were absent, not missing corridor rows.
  `corridor_stops_from_view` places them by stop membership (TODO.md Done, 2026-11-08).
- "Last 30 days" is the 30 days before `max(bus_stop_time)`: 2026-06-28 to 2026-07-28, not the 30 days
  before the check (`docs/2026-11-04-mansueto-data-edge.md`).
- The vault note names `notebooks/michigan_ave_segment.py`; the module is `cta/michigan_ave_segment.py`
  (`specs/package-migration.md`).
- The vault note cited `michigan-ave-pattern-endpoint-coverage` and `dlsd-cache-last30d-semantics`, which
  are not in the repo or on the inbox list. `michigan-ave-bus-lane-segment`,
  `michigan-ave-corridor-stops-snapshot`, `michigan-ave-6402-pattern-trim` and
  `michigan-ave-slow-hour-corridor-plots` are on the list.

## How to re-check

Run `notebooks/michigan_ave_segment_view.ipynb` with the 45 `last30d` cache files in place
(`scripts/cache_dlsd_parquets.py`); `segment_view_report` prints the table above. While the Mansueto
parquets stay frozen the numbers should not move. For new work, run `corridor_stops_from_view` on the
run-level view instead and read its QA table.
