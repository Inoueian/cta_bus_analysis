# First results for routes 8, 65 and 66: the closures add 5 to 8 minutes to a median crossing and up to 21 to the 95th percentile; waits outside the area unchanged (measured 2026-11-20)

Tags: `kind:measurement source:mansueto stage:figure topic:metrics topic:pattern-catalog`

These are the first results of Phase 1 (TODO.md, "First-results notebook"), from
`notebooks/routes_8_65_66_first_results.ipynb`. Three questions: how much the Halsted (route 8) and Chicago
Avenue bridge (route 66) closures slowed the crossing of the construction area, how the travel-time distribution
by hour changed, and what a rider waits at one reference stop per direction. Everything reads only stops that
exist through the whole Mansueto history, so neither the stop-validity item nor the run-level reader can change
these numbers. The Next specs (travel time, time series, wait time) can take them as acceptance values.

## Measurement

- **Source.** The 24 `usable_mansueto` parquets of `notebooks/routes_8_65_66_pids.json`, fetched 2026-11-20
  into `data/mansueto/` (service dates 2022-06-01 to 2026-07-27).
- **Why not the run-level view.** `scripts/route_run_level.py --source mansueto --fetch` could not build the
  view. On 2026-11-20 the Bus Tracker API answered every request with `Invalid locale parameter`: `gettime`,
  `getlocalelist` and `getpatterns`, on v2 and v3, with our key and with a made-up one. An explicit `locale`
  returned HTTP 500. With no getpatterns cache, `pattern_stops_table` raises.
- **What the notebook does instead.** It reads each parquet with the projection of `cta.mansueto.read_trips`,
  plus a filter on the measured stops, and runs `cta.mansueto.clean_trips` with a pattern-stop table holding only
  those stops. The read (DST), dedup and order stages run as they do for the view. The pattern join keeps the
  measured stops, which today's patterns contain.
- **Check.** The EDA's 18 period medians (`docs/2026-11-13-routes-8-65-66-eda.md`) are reproduced to within
  0.04 minute. 845,785 dominant-pattern runs have both segment stops, of 845,811 that reach either. The read
  stage drops 30 rows as `dst_ambiguous_time`; dedup, pattern join and order drop none.
- **Segments.** The EDA's brackets (section 6.6). Runs entering 06:00 to 19:59, Mon to Thu, holidays sliced by
  `cta.calendar.calendar_flag`. Before is 2024-09-03 to 2025-08-03; during is 2025-09-29 to 2026-07-27.
- **Waits.** Every arrival at the EDA's reference stop (section 8), all patterns of the direction pooled.
  A headway is the gap between consecutive arrivals on one service day, assigned to the hour of its midpoint. For a
  rider who turns up at a random time, the mean wait is sum of h² / (2 × sum of h), and P(wait > w) is
  sum of max(h − w, 0) / sum of h. "Even" is half the mean headway.
  Windows with no retired-pid rows (`docs/2026-11-15-routes-8-65-66-run-level-qa.md`): routes 8 and 66 from
  2026-05-01 to 2026-07-27, route 65 from 2026-07-01 to 2026-07-27. A 30-run gate applies per hour cell.

Travel time across the construction area, Mon to Thu daytime, minutes, before → during:

| Route, direction, segment | Runs before / during | Median | 95th percentile | 95th minus median | During runs slower than before's 95th |
|---|---|---|---|---|---|
| 8 S, Halsted & North Ave to Lake | 15,276 / 13,758 | 12.8 → 20.7 | 18.4 → 39.3 | 5.6 → 18.5 | 69% |
| 8 N, Halsted & Lake to North Ave | 14,582 / 13,041 | 13.2 → 18.4 | 23.4 → 26.3 | 10.2 → 7.8 | 12% |
| 66 E, Chicago & Ashland to Clark | 22,649 / 21,936 | 15.1 → 21.1 | 19.1 → 32.4 | 4.0 → 11.3 | 72% |
| 66 W, Chicago & Clark to Ashland | 23,114 / 21,111 | 14.3 → 19.2 | 19.4 → 35.2 | 5.1 → 16.0 | 48% |
| 65 E, Grand & Ashland to Illinois & Clark | 9,272 / 8,204 | 13.5 → 15.0 | 17.9 → 24.3 | 4.4 → 9.4 | 23% |
| 65 W, Grand & Clark to Ashland | 8,632 / 7,970 | 12.6 → 13.6 | 21.8 → 25.2 | 9.2 → 11.6 | 9% |

The hour with the highest median during the closures:

| Route, direction | Hour of entry | Median before → during | 95th percentile before → during |
|---|---|---|---|
| 8 S | 16:00 | 14.2 → 30.8 | 20.2 → 53.0 |
| 8 N | 17:00 | 20.6 → 21.0 | 30.3 → 34.0 |
| 66 E | 08:00 | 16.3 → 27.5 | 19.8 → 47.0 |
| 66 W | 17:00 | 17.0 → 28.4 | 22.0 → 48.1 |
| 65 E | 08:00 | 14.9 → 20.9 | 18.6 → 36.0 |
| 65 W | 17:00 | 18.8 → 21.2 | 29.1 → 32.9 |

Waits during the closures, Mon to Thu, headways with midpoint 06:00 to 19:59, minutes:

| Route, direction, stop | Headways | Median headway | Even | Mean wait | Bunching penalty | 90th percentile wait | Riders waiting > 15 min | Headways < 1 min |
|---|---|---|---|---|---|---|---|---|
| 8 N, Halsted & Monroe | 4,685 | 7.8 | 4.3 | 5.9 | 38% | 12.3 | 5.1% | 3.2% |
| 8 S, Halsted & 28th Street | 5,138 | 6.9 | 3.9 | 6.1 | 55% | 13.1 | 6.3% | 10.8% |
| 66 E, Chicago & Cicero | 6,460 | 5.8 | 3.1 | 4.5 | 44% | 9.2 | 2.5% | 7.0% |
| 66 W, Chicago & Lamon | 6,410 | 4.9 | 3.1 | 5.6 | 78% | 12.2 | 5.1% | 16.2% |
| 65 E, Fullerton & Grand (July only) | 706 | 15.7 | 8.9 | 12.7 | 42% | 27.9 | 28.6% | 0.1% |
| 65 W, Grand & Cicero (July only) | 838 | 13.5 | 7.5 | 12.9 | 73% | 27.6 | 29.0% | 5.7% |

The same months a year apart, mean wait before → during (minutes): route 8 N 6.2 → 5.9 and S 6.6 → 6.1 (May to
July 2025 against 2026); route 66 E 4.1 → 4.4 and W 5.4 → 5.4 (July 2025 against July 2026). Route 65 has no clean
year-earlier window.

## Facts confirmed

- **The closures slowed the crossing at the closure dates and it has not recovered.** Route 8 southbound weekly
  medians went from 12.5 to 13.1 minutes in July 2025 to 21.5 in the week of 2025-08-04, peaked at 24.9 in
  mid-October 2025, and have been near 20 since mid-November 2025. Route 66 stepped up in the week of 2025-09-29
  (eastbound 14.7 → 21.1, westbound 14.3 → 23.4). Through July 2026, neither has moved back toward its before
  level.
- **The tail grew more than the median.** On route 8 southbound and route 66 in both directions, the gap between
  the 95th percentile and the median roughly tripled. A rider who has to arrive on time now allows 39 minutes
  where 18 used to do (route 8 southbound).
- **Route 8 northbound is different.** Its PM peak was already slow before the closure (17:00 median 20.6), so
  the closure barely moved it (21.0). The added time is midday instead, about 12 → 18 minutes from 09:00 to
  13:00.
- **Route 65's AM peak eastbound slowed** by 6 minutes at the median (14.9 → 20.9), while its daytime median moved
  1.5. The cause, such as traffic diverted from Chicago Avenue, is not established.
- **Waits away from the construction did not get worse.** The reference stops are all outside the construction
  area (the closest is Halsted & Monroe, south of Lake Street). Their mean waits a year apart moved by 0.5 minute
  or less. Waits next to the closed blocks are not measured.
- **Bunching is large everywhere.** At the reference stops, the mean wait is 38% to 78% above what the same
  buses evenly spaced would give. The share of headways under a minute (up to 16%) is an upper bound, because
  arrival times are imputed between pings about five minutes apart.
- **Route 65 has recurring hour-long gaps in Mansueto.** In July 2026, eastbound at Fullerton & Grand, a gap of
  about 64 minutes starts near 14:45 on 11 of 15 Mon to Thu days. Westbound at Grand & Cicero, gaps of 54 to 59
  minutes start near 10:00 and 11:00 on 12 of 15. Routes 8 and 66 have no daytime gap over 60 minutes in their
  windows. Either those trips did not run, or they ran under a pid with no Mansueto parquet (29292 is absent from
  `rt_to_pid.csv`). The archive can settle this from 2026-09-28.
- **Route 65 had a slow period in 2022.** Weekly medians were 15.6 to 17.3 minutes from 2022-08-15 to 2022-12-19
  eastbound and from 2022-10-10 to 2022-12-12 westbound, against about 13 before and after. The cause is not
  established.

## How to re-check

Run `notebooks/routes_8_65_66_first_results.ipynb` end to end. It needs the 24 parquets under `data/mansueto/`
(`cta.mansueto.fetch_parquet`; the notebook lists any that are missing), but no `getpatterns`. Its first check
asserts the EDA's 18 medians to 0.1 minute.

Once the Bus Tracker API answers again, build the view with `python scripts/route_run_level.py --source mansueto
--fetch` and recompute the before and during medians from `data/route_run_level/source=mansueto/`. They should
equal the first table here. If they do not, the shortcut in the notebook missed something the view does.
