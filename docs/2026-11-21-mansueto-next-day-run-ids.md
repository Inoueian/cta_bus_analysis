# Mansueto run ids carry the next day's date for 2% of runs, almost all late-evening starts (measured 2026-11-21)

Tags: `kind:measurement source:mansueto stage:clean topic:identifiers topic:calendar`

Found while building the day cuts of `specs/mansueto-stop-validity.md`: the Mansueto fixture builder's self-check (the date
at the end of `unique_trip_vehicle_day` is the Chicago date of the run's earliest row for at least 99% of runs,
post-midnight continuations excused; `specs/mansueto-adapter.md` Method 6) failed on both days. `cta.mansueto.clean_trips`
takes `service_date` from that embedded date, so the finding is about which service day a run belongs to, not only about
fixtures. It corrects the evidence behind `MIN_EMBEDDED_DATE_SHARE` in `scripts/build_mansueto_fixtures.py`.

## Measurement

DuckDB over the 24 `getpatterns_ok` parquets of `notebooks/routes_8_65_66_pids.json` (`data/mansueto/`, generated
2026-07-28): per run, the earliest `bus_stop_time` (naive Chicago wall time) against the trailing date of
`unique_trip_vehicle_day`.

| Cut | Runs | Date = earliest row's day | Previous date, start before 04:00 | Next date | Next date, earliest start |
|---|---|---|---|---|---|
| 2025-10-14 (Tuesday) | 778 | 748 | 15 | 15 | 23:05 |
| 2025-12-02 (Tuesday) | 807 | 779 | 16 | 12 | 22:17 |
| 2026-07-27 (Monday, route 3 fixture day, last before the freeze) | 778 | 763 | 15 | 0 | — |

Whole history (2022-05-31 to 2026-07-28): 997,563 runs, 20,185 (2.02%) carry the next day's date; the monthly share is
1.68% to 2.44% from 2022-06 on. Of those runs, 19,766 (97.9%) start at or after 22:00 (17,612 between 23:00 and
midnight), and they are 25.1% of the 78,593 runs that start at or after 22:00. The other 419 start earlier: 245 in the
21:00 hour, 73 in the 20:00 hour, a few as early as 08:00. No run is dated 2026-07-28.

## Facts confirmed

- **About one late-evening run in four belongs to the next service day in the view.** `clean_trips` sets `service_date`
  from the run id, so a run that starts at 23:10 on a Thursday is a Friday run: it carries Friday's `calendar_flag`, falls
  in Friday's day-type slice, and its arrivals before midnight sit in Friday's wait and travel-time distributions. Which
  late-evening runs carry the next date is not established (it is not a fixed clock time: 22:17 and 23:05 on the two
  cut days).
- **The route 3 fixture cannot show it.** Its day, 2026-07-27, is the last before the freeze, and no run dated 2026-07-28
  exists, so the 99% check was calibrated on the one day where next-day ids are absent.
- **The builder now excuses them by name.** On the owner's decision (2026-11-21), `check_embedded_service_date` counts a
  run carrying the next date whose earliest row in the cut is at or after `LATE_EVENING_HOUR` (22) as a late-evening
  start, recorded apart in the manifest (`late_evening_next_day`). Both 2025 cuts then have 0 unexplained runs. A cut
  holding one of the 419 earlier next-day runs would still fail the check.
- **The stop-validity windows barely notice.** A window compares the run's service date with `valid_from`, so a
  late-evening run on the eve of `valid_from` that carries the next date keeps its arrivals before the window opens,
  almost always from the last two hours of that evening.

## Corrections to earlier notes

- `scripts/build_mansueto_fixtures.py`, evidence of `MIN_EMBEDDED_DATE_SHARE` ("post-midnight trips are the expected
  exceptions", from `specs/mansueto-adapter.md` Method 6): true on the edge day only. On an ordinary day about 2% of runs
  carry the next date; the late-evening class is now excused beside the post-midnight one.

## How to re-check

```
WITH r AS (SELECT unique_trip_vehicle_day AS run, min(bus_stop_time) AS first FROM read_parquet(<the 24 files>) GROUP BY 1)
SELECT count(*) FILTER (WHERE CAST(regexp_extract(run, '(\d{4}-\d{2}-\d{2})$', 1) AS DATE) = CAST(first AS DATE) + INTERVAL 1 DAY), count(*) FROM r
```

`python scripts/build_mansueto_fixtures.py --stop-validity` prints the three classes per cut. The parquets are frozen
(ADR-007), so a different count means a different set of pids or a regenerated bucket.
