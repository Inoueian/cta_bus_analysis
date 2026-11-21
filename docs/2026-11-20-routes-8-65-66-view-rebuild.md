# Run-level view for routes 8, 65 and 66 rebuilt: QA equal to 2026-11-15, first-results table equal run for run (measured 2026-11-20)

Tags: `kind:qa source:mansueto stage:view topic:qa-table topic:metrics`

`docs/2026-11-20-routes-8-65-66-first-results.md` computed its travel times from the Mansueto parquets
directly, because the Bus Tracker API was down that morning and `scripts/route_run_level.py` could not build the
view. Its "How to re-check" section asked for the view to be built once the API answered, and for the before and
during medians to be recomputed from it. This note does that. It confirms that note's first table and the
build QA of `docs/2026-11-15-routes-8-65-66-run-level-qa.md`. The archive half of the view is still a separate
TODO.md item (Phase 1, Later) and is not covered here.

## Measurement

In a cloud container. The 24 view parquets were fetched earlier the same day with `cta.mansueto.fetch_parquet`;
there was no `data/route_run_level/`, no raw day file, and no getpatterns cache for these pids.

```
python scripts/route_run_level.py --source mansueto --fetch       # fetched the other 17 parquets (41 in all, 2.05 GB), 24 getpatterns calls, 13 min
python scripts/route_run_level.py --source mansueto_raw --fetch   # 71 day files (2.77 GB), patterns from the cache, 5 min
```

The output under `data/route_run_level/` is 600 MB for `source=mansueto` and 35 MB for `source=mansueto_raw`.

Build QA, compared figure by figure with the 2026-11-15 note:

| Check | Rebuilt | 2026-11-15 note |
|---|---|---|
| `mansueto`: pids, service dates, runs, view rows, stops | 24; 1,518 (2022-06-01 to 2026-07-27); 997,561; 71,524,187; 489 | equal |
| `mansueto` per route: rows in, `dst_ambiguous_time`, `stop_not_in_pattern`, `nonmonotone_time`, rows out | 8: 31,029,179, 1,336, 1,441,269, 1, 29,586,573; 65: 13,134,074, 0, 48,621, 0, 13,085,453; 66: 30,629,634, 1,534, 1,775,939, 0, 28,852,161 | equal |
| `mansueto` pids, runs and rows per route and direction | the six rows of that note's direction table | equal |
| Arrivals at detour stops before today's geometry (`detour_stop_arrivals.csv`) | 2,127,091 | equal |
| `mansueto_raw`: pids, days, runs, view rows, stops | 24; 71 (2026-08-13 to 2026-10-27, 5 days without a file); 55,154; 3,631,433; 491 | equal |
| `mansueto_raw` `bracket_gap_s` | median 300 s, 95th percentile 360 s, never NaN | equal |
| `mansueto_raw` stages, rows in → out | read 806,950 → 806,950; clean 806,950 → 805,583; pairs 748,386 → 745,317; impute 3,631,598 → 3,631,433 | equal |
| `mansueto_raw` reasons | `duplicate_fix` 1,118; `other_data_date` 229; `null_run_key_or_pdist` 20; `gap_over_max` 2,235; `backward_pdist` 692; `geometry_unsupported` 142; `later_crossing` 165 | equal |
| `mansueto_raw` pid-days longer than the cached pattern by more than 0.05 mi | 0 | equal |

First-results comparison. Path A is the notebook's first two code cells, executed unchanged: its `read_stop_rows`
on the parquets, `cta.mansueto.clean_trips`, and the segment pivot. Path B reads the same six segment pids from
`data/route_run_level/source=mansueto/` (`pattern_id` equal to the segment pid, the two segment stops) and pivots
per run. Both then go through the notebook's own filters: Mon to Thu by its `add_day_type`, entry hour 06 to 19
Chicago, `minutes > 0`. Then the same before and during table.

| Check | Result |
|---|---|
| Runs with both segment stops | 845,785 on each path; none on one path only |
| Per run: service date, entry time, minutes | equal on all 845,785 (largest difference in minutes 0.0) |
| Duplicate (run, stop) rows in the view at the segment stops | 0 |
| Period table: runs, median, 95th percentile before and during, share of during runs slower than before's 95th | equal in every cell, all six segments |
| The view's own `calendar_flag` against `cta.calendar.calendar_flag` as the notebook calls it | the holiday flag agrees on all 1,518 service dates (25 holiday dates) |

## Facts confirmed

- **The first-results numbers do not depend on the notebook's shortcut.** Reading the parquets at the measured
  stops gives the same runs and times as the full view. The note's first table stands as computed. The Next specs
  can read the view for these segments and expect the same acceptance values.
- **The view rebuilds reproducibly from public inputs.** In a container with no earlier view or pattern cache, the
  two commands above give the 2026-11-15 QA exactly. That holds while the Mansueto parquets stay frozen at 2026-07-28 (ADR-007) and the raw day
  files stay unchanged.
- **The Bus Tracker API answered again later on 2026-11-20.** `getpatterns` served all 24 pids of the pid list.
  The morning's `Invalid locale parameter` outage was transient. Later that day, a made-up key got the normal
  `Invalid API access key supplied`.
- **DuckDB's `.df()` drops the zone of the view's `arrival_time`.** The column is stored as
  `timestamp[ns, tz=UTC]`. DuckDB 2.0.0 returns it as naive UTC clock time, whatever the session `TimeZone`. A
  `tz_convert` on it then raises instead of shifting the times. Playbook gotcha "DuckDB returns tz-aware view
  timestamps as naive".

## Corrections to earlier notes

- `docs/2026-11-20-routes-8-65-66-first-results.md`, "How to re-check": the view comparison it asked for is done.
  Its last paragraph now points here.

## How to re-check

Run the two commands under Measurement, then compare with the 2026-11-15 note's tables: view totals and directions
from `data/route_run_level/source=<source>/`, reasons from `qa_<source>.csv`. For the first-results table, run
the notebook's first two code cells and read the six segment pids from the view as above. Then compare per run on
(`route`, `direction`, `run_id`). A difference is a change in the parquets, the raw day files, the getpatterns
answer, or the adapters, so check each one's fetch metadata (`trips_<pid>_full.meta.json`, `<day>.meta.json`)
before the code.
