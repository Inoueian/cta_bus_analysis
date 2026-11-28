# Stop-validity review for routes 8 and 66: buses changed route on the schedule's dates, not Bus Tracker's, and did not stop at Orleans & Chicago or Wells & Chicago before their detours (measured 2026-11-23)

Tags: `kind:measurement source:mansueto source:gtfs topic:pattern-catalog topic:calendar`

Contains data from [Transitland](https://www.transit.land/terms): the paths and stop lists are read from archived CTA
GTFS versions (ADR-013).

The TODO item "Review the stop-validity windows against the archived GTFS" asked the owner to rule on the 26 windows
that `docs/2026-11-22-gtfs-history-routes-8-66.md` found disagreeing with the schedule. The owner's rules (2026-11-23,
ADR-014): (1) where pings and schedule date a change differently, the pings decide, since the actual driving is the
schedule in effect; (2) a corner served under different stop ids is one corner, served; (3) for the three corners the
schedule leaves without a stop for a while, compare the time buses take past them with and without a stop. This note
measures what (1) and (3) need. Notebook: `notebooks/corner_stops_routes_8_66.ipynb` (Findings cell). No window is
changed here.

## Measurement

Mansueto raw day files (Bus Tracker positions about every 300 s) for the four dominant pids. 31 days were read around
the changes (2025-07-29 to 2025-11-25), plus 30 sample weekdays (Tue to Thu): ten in July 2025 (old routes), ten in
October 2025 (first detours) and ten in June 2026 (today's detours). That is 59 files of 23 to 45 MB in
`data/mansueto_raw/` (two days fall in both sets). Paths and stops come from three archived GTFS versions (`78428dc4…`,
`c07e6831…`, `81c806bb…`), whose `shapes.txt` distances are clean for these pids.

**Driving.** Each day, the pings in the closure area are classed by the paths they lie on (within 100 ft), and
*section jumps* count consecutive pings of a trip on opposite sides of the closed section:

| Pattern | Change | Committed window (Bus Tracker pattern switch) | Schedule (GTFS) | Driving (ping positions) | Days unreported before it |
|---|---|---|---|---|---|
| 8 south, 8 north | first detour | 2025-08-17 | 2025-08-17 | 2025-08-17 | 2025-08-04 to 08-16 |
| 66 east (6662) | detour | 2025-09-27 | 2025-09-28 | 2025-09-28 | |
| 66 west (6665) | first detour | 2025-09-28 | 2025-09-28 | 2025-09-28 | |
| 8 north (9376) | second detour | 2025-11-23 | 2025-11-23 | 2025-11-23 | 2025-11-07 to 11-22 |
| 66 west (6665) | second detour | 2025-11-24 | 2025-11-23 | 2025-11-23 | 2025-10-31 to 11-22 |
| 8 south (9368) | second detour | 2025-11-25 | 2025-11-23 | 2025-11-23 | 2025-11-07 to 11-22 |

Evidence for the dates:
- 6662 had 147 pings on old-path-only streets on 2025-09-27 and 1 on 09-28, after midnight.
- On 2025-11-23, 100 to 109 pings a pid fell on today's-detour-only streets, against 2 to 11 the day before.
- Section jumps are 0 to 22 a day on other days and 32 to 101 on the unreported days, 10 to 20 minutes apart. On those
  days almost no ping lies on any of the three paths in the section; route 66 west has 3 to 35 a day on Wells.

**Corners.** Each ping stands for the time to the midpoints of its neighbours on the same trip (each half capped at
330 s). Summed over a stretch and divided by the trips that crossed it (pings 1,500 ft before and after), that gives the
mean seconds a trip spends there. 0 is the corner stop's position projected onto that period's path. Values are mean
seconds per trip within 150 ft of the corner, ± standard error over trips:

| Corner | Old route (Jul 2025) | First detour (Oct 2025) | Today's detour (Jun 2026) |
|---|---|---|---|
| 66 east, Orleans & Chicago (`6714`) | 24.3 ± 2.0, no stop | 58.7 ± 3.1, stop | 52.3 ± 2.9, stop |
| control: 66 west crossing Orleans, never a stop | 23.3 ± 2.0 | 27.6 ± 2.3 | |
| 66 west, Wells & Chicago (`18803`) | 7.7 ± 1.2, no stop | 4.9 ± 1.0, no stop | 41.7 ± 2.6, stop |
| 8 north, Halsted, Grand & Milwaukee (`15341`) | 17.7 ± 2.3, stop `15274` 82 ft before | 15.1 ± 2.2, no stop | 40.8 ± 3.4, stop |

The owner's stop-before-to-stop-after measure, mean seconds between the two stops (leaving out 75 ft after the first
and 175 ft before the second, where their own dwell falls):
- Wells & Chicago: LaSalle to Franklin takes 14.7 and 12.5 s with no stop at Wells, against 117.1 s for today's Clark
  to Wells & Huron, which turns onto Wells.
- Orleans & Chicago: Hudson to Franklin takes 39.7 s, but its window ends 29 ft before the corner, since Franklin is
  146 ft past it. Today's Orleans & Huron to Franklin takes 62.2 and 79.4 s.
- Halsted, Grand & Milwaukee: Hubbard to Erie takes 105.5 s, Hubbard to Grand & Union 52.2 s, and Hubbard to
  Milwaukee & Erie 93.1 s.

## Facts confirmed

- **Bus Tracker's pattern switch is not when the buses moved; the schedule's date is.** In all seven changes the buses
  changed route on the GTFS date. The pattern switched a day early on 6662, a day late on 6665 and two days late on
  9368. So the committed windows, which open on the pattern switch, are a day or two off on 18 rows. Route 8's buses
  left Halsted on 2025-08-04, 13 days before either.
- **Before three changes, Bus Tracker did not report the buses on the closed section** for 13 to 23 days. The buses
  were off the pattern it held: route 8 from the closure on 2025-08-04 to 08-16 and again from 2025-11-07 to 11-22,
  and route 66 west from 2025-10-31 to 11-22. Mansueto's arrivals at stops in those sections on those days are
  interpolated across the gap. The days between the ones read (08-06 to 08-15, 11-13 to 11-21) are assumed to be
  like their neighbours.
- **Wells & Chicago was not served before the detour reached Wells.** The pile-ups on Chicago Avenue are at LaSalle
  and Franklin, and the corner shows 5 to 8 s, against 42 s with the stop.
- **Orleans & Chicago was not served eastbound before 2025-09-28.** The 24 s at the corner is the signal: westbound
  buses at the same intersection, which never had a stop, spend 23 to 28 s there.
- **At Halsted, Grand & Milwaukee northbound, the first detour shows no dwell at the corner** (15 s, against 41 s with
  today's stop). The measure is weaker here. The old stop's pile-up sits 150 to 250 ft before the corner, the first
  detour turned right at a six-way signal, and the band does not cover the same road position in every period. The
  reading rests on that and on the schedule, which had no stop between Hubbard (338 ft before) and Grand & Union
  (346 ft after).
- **The stop-to-stop times change with the path as well as the stop**, because every corner's stop arrived with a new
  street. They agree with the corner readings but cannot settle them alone.

## Corrections to earlier notes

- `docs/2026-11-13-routes-8-65-66-eda.md` and `docs/2026-11-21-stop-validity-windows.md` call the day the longest
  `pdist` changed the day the "geometry changed"; it is the day Bus Tracker's pattern changed. The buses changed route
  on 2025-09-28 (6662) and 2025-11-23 (6665, 9368), not 09-27, 11-24 and 11-25 as `geometry_changes` in
  `notebooks/routes_8_65_66_pids.json` and the windows have it.
- `docs/2026-11-22-gtfs-history-routes-8-66.md` filed the 18 one-to-two-day differences as "the same change dated
  apart". By driving, the schedule's dates are the right ones.

## How to re-check

Run `notebooks/corner_stops_routes_8_66.ipynb` after `notebooks/gtfs_history_routes_8_66.ipynb` has cached the GTFS
versions. It fetches the raw days it lacks (about 40 MB each). Section 1's table reproduces the driving dates. Section
2's `CORNER_TABLE` reproduces the corner seconds. A raw day file whose HEAD changed makes `cta.mansueto_raw.fetch_day`
refuse; re-measure rather than replace.
