# Run-level view for routes 8, 65 and 66 from the Mansueto parquets and raw day CSVs: 71.5M and 3.6M rows, QA equal to the EDA (measured 2026-11-15)

Tags: `kind:qa source:mansueto stage:view topic:qa-table topic:pattern-catalog`

QA record for the TODO.md Phase 1 item "Run-level view for routes 8, 65, & 66 from the Mansueto parquet and
the raw day CSVs". `scripts/route_run_level.py` applies the existing views
(`cta.views.run_level_from_mansueto_with_qa`, `run_level_from_mansueto_raw_with_qa`) to the pids in
`notebooks/routes_8_65_66_pids.json`; no threshold, exclusion or schema was added. It confirms the cleaning
numbers of `docs/2026-11-13-routes-8-65-66-eda.md`, measures the retired-pid share by month for the
wait-time spec, and corrects that note on the pids of fall 2026. The archive half is a separate TODO item.

## Measurement

```
python scripts/route_run_level.py --source mansueto --fetch       # 41 parquets (2.0 GB), 24 getpatterns calls
python scripts/route_run_level.py --source mansueto_raw --fetch   # 71 day files (2.6 GB)
```

Output under `data/route_run_level/` (gitignored): `source=mansueto/pid=<pid>/year=<YYYY>.parquet` (600 MB),
`source=mansueto_raw/<day>.parquet` (35 MB) and the QA tables as CSV. The Mansueto half cleans one pid and
one year at a time, with runs assigned whole to the year of their first arrival, so the QA sums equal one
call per pid (`tests/test_route_run_level.py`).

| Source | Pids | Service dates | Runs | View rows | Stops | `bracket_gap_s` |
|---|---|---|---|---|---|---|
| `mansueto` | 24 | 1,518 (2022-06-01 to 2026-07-27) | 997,561 | 71,524,187 | 489 | NaN on every row |
| `mansueto_raw` | 24 | 71 (2026-08-13 to 2026-10-27) | 55,154 | 3,631,433 | 491 | median 300 s, 95th percentile 360 s, never NaN |

Mansueto half, per route (stages `read`, `dedup`, `pattern_join`, `order`; a reason not shown is 0):

| Route | Rows in | `dst_ambiguous_time` | `stop_not_in_pattern` | `nonmonotone_time` | Rows out |
|---|---|---|---|---|---|
| 8 | 31,029,179 | 1,336 | 1,441,269 | 1 | 29,586,573 |
| 65 | 13,134,074 | 0 | 48,621 | 0 | 13,085,453 |
| 66 | 30,629,634 | 1,534 | 1,775,939 | 0 | 28,852,161 |

Raw half, all 71 days:

| Stage | Rows in | Rows out | Reasons |
|---|---|---|---|
| `read` | 806,950 | 806,950 | |
| `clean` | 806,950 | 805,583 | `duplicate_fix` 1,118; `other_data_date` 229; `null_run_key_or_pdist` 20 |
| `pairs` | 748,386 | 745,317 | `gap_over_max` 2,235; `backward_pdist` 692; `geometry_unsupported` 142 |
| `impute` | 3,631,598 | 3,631,433 | `later_crossing` 165 |

Per route and direction:

| Route | Direction | Mansueto pids | Mansueto runs | Mansueto rows | Raw pids | Raw runs | Raw rows |
|---|---|---|---|---|---|---|---|
| 8 | Northbound | 4 | 151,147 | 14,134,029 | 4 | 7,881 | 681,193 |
| 8 | Southbound | 5 | 160,214 | 15,452,544 | 5 | 8,412 | 750,349 |
| 65 | Eastbound | 3 | 100,910 | 6,761,855 | 3 | 6,367 | 364,129 |
| 65 | Westbound | 4 | 91,961 | 6,323,598 | 4 | 5,806 | 353,134 |
| 66 | Eastbound | 4 | 246,000 | 14,320,303 | 4 | 13,084 | 731,410 |
| 66 | Westbound | 4 | 247,329 | 14,531,858 | 4 | 13,604 | 751,218 |

## Facts confirmed

- **The cleaning numbers equal the EDA's** row for row: 74,792,887 rows in, 71,524,187 out, 3,265,829
  `stop_not_in_pattern`, 2,870 `dst_ambiguous_time`, 1 `nonmonotone_time`, 0 duplicates.
- **Arrivals at detour stops the bus was not serving: 2,127,091**, the EDA's number, now reproduced from the
  view (`detour_stop_arrivals.csv`). They stay in the view; nothing flags them.

  | Pattern | Stops added on 2024-09-03 | Today's geometry from | Arrivals at them before that | Share of the pattern's rows in the period |
  |---|---|---|---|---|
  | 66 east (6662) | 11 | 2025-09-27 | 636,909 | 15.94% |
  | 66 west (6665) | 13 | 2025-11-24 | 884,215 | 18.57% |
  | 8 south (9368) | 8 | 2025-11-25 | 354,954 | 7.55% |
  | 8 north (9376) | 6 | 2025-11-23 | 251,013 | 5.88% |

  The EDA note counts thirteen added stops on 6665 and eight on 9368, as here; 6662 and 9376 were not
  counted there.
- **The retired pids' share is steady, then ends** (`mansueto_rows_by_month.csv`; rows under the 17 pids
  that have a parquet and no pattern, as a share of the route's published rows in the month):

  | Route | Whole history | Monthly range while present | Last month with any | Zero from |
  |---|---|---|---|---|
  | 8 | 0.26% | 0.16% to 0.44% | 2025-12 (0.25%) | 2026-01 |
  | 65 | 6.25% | 5.08% to 7.50%, then 1.55% in 2026-06 | 2026-06 | 2026-07 |
  | 66 | 1.59% | 2.02% to 3.00%, then 0.97% in 2025-06 | 2025-06 | 2025-07 |

  On route 65 two pids hold most of it: 7908 (448,050 rows) and 2095 (312,021), both to 2026-06. So the
  view is missing about one run-stop row in sixteen on route 65 for all but the last month of the history,
  and a wait computed there is too long by an amount nobody has measured.
- **Service dates.** The view's first `service_date` is 2022-06-01, not 2022-05-31: the two runs of 9368 that
  start at 23:25 on 2022-05-31 carry 2022-06-01 in their run id, which is what `clean_trips` reads. The EDA's
  1,519 days count first arrivals by calendar day.
- **Holidays**: 892,794 Mansueto rows on 25 service dates and 37,222 raw rows on one (Labor Day) carry a
  `holiday:` flag. No row carries `coverage_gap`.
- **The raw half fits today's patterns on every day.** Longest `pdist` per pid and day against the cached
  pattern length, 1,441 pid-days (`raw_pattern_length.csv`): none is longer than the pattern by more than
  0.05 miles (largest difference 0.000). The six dominant patterns are within 0.006 to 0.037 miles short on
  all 71 days. Minor patterns with few pings can be up to 2.84 miles short on a day, which says nothing
  about geometry.
- **Five raw days have no file** (2026-09-30, 2026-10-02, 2026-10-03, 2026-10-16, 2026-10-17), the days
  `cta.calendar.MANSUETO_RAW_MISSING_DAYS` declares. They are QA rows with stage `coverage`.

## Pids the raw half does not have

Fixes of routes 8, 65 and 66 in the 71 day files by pid: 806,950 under the 24 pids read, 3,260 under six
others (0.4%).

| Route | Pid | Fixes | Days | getpatterns | What it is |
|---|---|---|---|---|---|
| 8 | 502231, 502242 | 1,393 | 2026-10-11 only | 502231 not served | temporary pids, about 07:30 to 18:55 |
| 66 | 502354, 502357 | 1,012 | 2026-10-11 only | not asked | temporary pids, about 07:24 to 16:20 |
| 65 | 502367, 502369 | 658 | 2026-10-11 only | not asked | temporary pids, about 07:20 to 16:05 |
| 65 | 29292 | 141 | 20 days, 2026-08-15 to 2026-10-25 | served: Eastbound, 32 stops, Grand & Nordica to Grand & Pulaski | not in `rt_to_pid.csv` or the pid list |
| 65 | 28316 | 56 | 7 days, 2026-08-13 to 2026-08-21 | not served | not in `rt_to_pid.csv` |

- **Sunday 2026-10-11 is half missing.** 56.6% of route 8's fixes, 48.0% of route 65's and 32.6% of route
  66's are under temporary pids, so the view has 327 runs against 521 to 570 on the other ten Sundays. The date is
  the Chicago Marathon (confirmed by the owner, 2026-11-15). `calendar_flag` is empty on that day.
- **On 28 other days route 65 has 0.6% to 1.8% of its fixes outside the list**, all under 29292 and 28316.
  Routes 8 and 66 have none outside 2026-10-11.
- **Pid 6653 (65 west) is in the view** although the pid list marks it `usable_archive: false`: it has 469
  fixes on 28 raw days (2,085 view rows, 119 runs), none on the four days the EDA sampled. The script reads
  every pid with `getpatterns_ok`, 24, for that reason.

## Corrections to earlier notes

- `docs/2026-11-13-routes-8-65-66-eda.md` says fall 2026 "needs no pid outside the catalog" and that the
  same 23 pids appear every day. That holds for its four sampled days. Over the 71 raw days route 65 also
  runs under 6653 (listed), 29292 and 28316 (unlisted), and on 2026-10-11 all three routes run under
  temporary pids.
- The same note's "runs start on each of the 1,519 days from 2022-05-31" is by calendar day of first
  arrival; by `service_date` the view has 1,518 dates from 2022-06-01.

## How to re-check

Re-run the two commands above and compare
the printed stage totals with the tables here. If a Mansueto total moves, the parquets changed: check
`cta.calendar.source_freshness` before anything else (ADR-007). For the unlisted pids, count fixes by `rt`
and `pid` in a day file and compare with the pid list; a route-day with more than a few percent outside the
list is an event day and its headways are not usable.
