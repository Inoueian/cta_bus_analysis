# Mansueto parquet columns mapped to the ADR-003 views: 11 columns, 0 null or duplicate trip keys on PID 6662 (measured 2026-09-15)

Tags: `kind:measurement source:mansueto stage:view topic:identifiers`

Migrated 2026-11-13 from vault `canonical-data-views` (created 2026-08-10 alongside ADR-003, revised after
the 2026-09-15 verification). It is the record of which Mansueto column feeds which run-level column and
of how each query maps to a view. Nothing was re-measured for the migration; where later work replaced a
statement, the replacement is under "Corrections".

## Measurement

`scripts/verify_parquet.py` on route 66 / PID 6662, `trips_6662_full.parquet` read from CloudFront,
2026-09-15. The PID list by route came from `rt_to_pid.csv` (`cta.mansueto.RT_TO_PID_URL`).

| Run-level column (ADR-003) | Mansueto column | Verified on PID 6662 |
|---|---|---|
| `run_id` | `unique_trip_vehicle_day` | 0 nulls; embeds route, pid, vehicle and date |
| `route` | `rt` | string route number |
| `pattern_id` | `pid` | string; the file is already one pid |
| `stop_id` | `stpid` | CTA stop id; `p_stp_id` is the composite `{pid}-{stpid}` |
| `stop_sequence_index` | `stop_sequence` | int64 (see Corrections: no longer the source of the index) |
| `arrival_time` | `bus_stop_time` | `datetime64[ns]` |
| `direction` | none | not in the parquet |

| Fact | Value |
|---|---|
| Columns in the file | 11 |
| Duplicate (`unique_trip_vehicle_day`, `stpid`) | 0 |
| `typ` | all `S` on the sample |
| `bus_stop_time` range | 2022-05-31 to 2026-07-28 |
| Other columns | `vid`, `speed_mph`, `seg_combined`, `typ`, `p_stp_id` |

## Facts confirmed

- The trip key is Mansueto's own and is kept as `run_id`; no replacement identifier is invented (ADR-003).
  The vault's example key shows the pid embedded as `6662.0`, the float form the "Identifiers arrive as
  `6410.0`" gotcha is about.
- The grain is one row per run and stop. A run that skipped a stop, or lost the pings around it, has no
  row for it. Missing arrivals are never fabricated.
- Renaming happens only in the derived views; the CloudFront read keeps Mansueto's names
  (`cta.mansueto.PARQUET_COLUMNS`, then `TRIP_COLUMNS`).

## Query to view mapping (design carried over from the vault note)

| Question | View | How |
|---|---|---|
| Wait-time distribution at a stop | stop-level | one row per (`stop_id`, `route`, `direction`) |
| Travel-time distribution | run-level | filter to one run, join two of its stops |
| Destination given as a direction only | run-level | stops with `stop_sequence_index` above the origin's in the same run |
| Average travel time over calendar time | run-level | group by date |

The stop-level row holds `arrival_times` (an ordered list) and `pattern_ids` (a parallel list of the same
length, one pattern label per timestamp). Patterns are pooled into one (`route`, `direction`) row and the
view is not partitioned further by pattern; the parallel list is what makes a later per-pattern split a
query change. No stop-level view exists in `cta/` as of 2026-11-13 (TODO.md Phase 1, "Build the stop-level
view").

## Corrections

- `stop_sequence_index` is the dense getpatterns `stop_rank` on every adapter, not Mansueto
  `stop_sequence` (ADR-008).
- `direction` is the getpatterns `rtdir`, joined in `cta.mansueto.clean_trips`
  (`docs/2026-09-23-bustracker-api-endpoints.md`), not GTFS.
- The run-level view now carries five more columns than the vault listed: `bracket_gap_s`, `vehicle_id`,
  `service_date`, `calendar_flag`, `source` (`cta.views.RUN_LEVEL_COLUMNS`, ADR-004, ADR-009).
- "Built by: union all Mansueto pattern parquets" is one of three adapters now (`cta.views`).
- "Upstream lag about 14 days" was the 2026-07-28 freeze seen thirteen days in (ADR-007,
  `docs/2026-11-04-mansueto-data-edge.md`). `bus_stop_time` is naive Chicago wall time, which the vault
  note did not say (same note).
- The vault note cited `parquet-verification-results` and `cta-stop-watch-freshness-check`; neither is
  in the repo. The second is still listed in `docs/vault-inbox/README.md`.

## How to re-check

`python scripts/verify_parquet.py -h`, then run it on a pid; it prints the mapping and the null and
duplicate counts. `cta.mansueto.data_edge(pid)` gives the date range without a full download. If a
column is renamed upstream, `cta.mansueto.PARQUET_COLUMNS` and this table move together.
