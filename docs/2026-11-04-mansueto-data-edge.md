# Mansueto StopWatch data edge: 2026-07-28 (measured 2026-11-04)

Durable finding from probing the CloudFront bucket while drafting `specs/mansueto-adapter.md`.
It corrects two earlier notes (below) and is the evidence for ADR-007.

## Measurement

Each `trips_<pid>_full.parquet` was probed with HTTP range requests: a HEAD for size and
`Last-Modified`, then the parquet footer (~200 KB) for per-row-group `bus_stop_time` statistics,
then one row group (~1.2 MB) for the clock-hour profile. Nothing was downloaded in full.

| PID | Route / dir | Rows | Row groups | Earliest `bus_stop_time` | Latest `bus_stop_time` | `Last-Modified` |
|---|---|---|---|---|---|---|
| 18414 | 3 NB | 14,167,004 | 121 | 2022-08-21 05:54 | 2026-07-28 00:04 | 2026-07-28 10:11 UTC |
| 18415 | 3 SB | 15,493,762 | 128 | 2022-08-21 07:11 | 2026-07-28 02:04 | 2026-07-28 10:12 UTC |
| 6414 | 151 NB | 9,318,340 | 82 | 2022-05-31 23:13 | 2026-07-28 01:41 | 2026-07-28 10:19 UTC |
| 6662 | 66 | not read | | | | 2026-07-28 10:19 UTC |

`rt_to_pid.csv` was last modified 2025-01-16. Every file was regenerated in one run on 2026-07-28
and not since. The "roughly two-week lag" recorded in ADR-001 on 2026-08-10 was this stall at
thirteen days old, not a steady cadence. The Transit Alerts archive starts 2026-09-28, so as of
today **no service day exists in both sources**, and 2026-07-28 to 2026-09-27 is covered by neither.

## Schema facts confirmed on PID 18414

- `bus_stop_time` is a tz-naive `timestamp[ns]` with sub-second precision. The clock-hour profile
  of the last row group (59,420 rows) has 1 to 3 rows per hour at 01:00–03:00 and ramps from 04:00,
  which is route 3's local service pattern, so the values are **America/Chicago wall time**, not UTC.
- `pid`, `rt`, `stpid`, `vid` are string columns in this file (legacy code casts `pid` through float
  for safety; an adapter must accept either).
- `unique_trip_vehicle_day` looks like `318414.038912802023-04-24`: route, pid, vehicle and the
  service date are embedded. Zero duplicate `(trip, stop)` keys in the probed row group.
- Row groups are **not time-ordered** (the last one spans 2022-08-22 to 2026-07-27), so a date-range
  filter cannot rely on row-group statistics to skip I/O; the whole file is read.
- Column order in the file: `seg_combined, typ, stop_sequence, bus_stop_time, speed_mph,
  unique_trip_vehicle_day, stpid, p_stp_id, vid, rt, pid`.

## Corrections to earlier notes

`docs/2026-11-03-archive-adapter-qa.md`, `docs/2026-11-03-archive-imputation-prototype.md` and the
context of ADR-006 say the Mansueto 30-day medians in `notebooks/michigan_ave_kept_pids.json` come
from a window "ending ~2026-10-03". That was the cache date. `scripts/cache_dlsd_parquets.py` keeps
the 30 days before `max(bus_stop_time)`, so the window is **2026-06-28 to 2026-07-28**. The archive
validation therefore compared one late-October day against a midsummer window three months earlier,
which makes the 20% tolerance of ADR-006 more defensible, not less, and makes a same-source
self-consistency test the right gate for the Mansueto adapter.

## How to re-check

Run the footer probe again (a `cta.mansueto.data_edge(pid)` helper is specified in
`specs/mansueto-adapter.md`); if `max(bus_stop_time)` moves past 2026-07-28, reopen ADR-007 and the
cross-source items it deferred.
