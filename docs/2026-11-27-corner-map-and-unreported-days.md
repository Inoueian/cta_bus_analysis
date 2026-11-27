# Halsted, Grand & Milwaukee on a map: the first detour shows no dwell at the corner (peak 5 s against 14 and 27 s with a stop); the unreported periods hold on every day (measured 2026-11-27)

Tags: `kind:measurement source:mansueto source:gtfs topic:pattern-catalog topic:calendar`

Contains data from [Transitland](https://www.transit.land/terms): paths and stops are read from archived CTA GTFS
versions (ADR-013).

Two follow-ups to `docs/2026-11-23-stop-validity-review-driving-and-corners.md`, asked for by the owner on 2026-11-27
while deciding the review's open questions (`specs/mansueto-stop-validity.md`, Open questions 1 and 2). The first is
a map of the Halsted, Grand & Milwaukee corner, where route 8 northbound's first detour may or may not have served
stop `15341`. The second checks every day of the periods when Bus Tracker did not report buses on the closed section;
19 days had been skipped. Notebook: `notebooks/corner_stops_routes_8_66.ipynb` sections 1 and 2b, Findings 2 and 5.

## Measurement

Provenance of each layer:
- **Paths and stops** come from CTA's schedule (planned, via Transitland).
- **Time spent** is derived from GPS positions (observed, via Bus Tracker and Mansueto's raw day files). Each ping is
  weighted by the time to the midpoints of its neighbours. Summed per 50 ft of `pdist` and divided by the trips that
  crossed, that gives the mean seconds per trip, over ten Tue to Thu days per period (method in the 2026-11-23 note).

On the map, positions are in feet from stop `15341`. Grand Avenue crosses Halsted about 130 ft south of the stop.

| Period | Stop at the corner | Seconds in the ±150 ft band | Largest 50 ft stretch in the band | Where the other pile-ups are |
|---|---|---|---|---|
| Old route (Jul 2025) | `15274`, far side, ~130 ft north of Grand | 17.7 ± 2.3 | 13.9 s, at the stop | 40 s queue 90 to 125 ft south of Grand (the signal); Hubbard stop |
| First detour (Oct 2025) | none | 15.1 ± 2.2 | 5.4 s | queue from the Hubbard stop up to Grand; 50 s approaching Grand & Union |
| Today's detour (Jun 2026) | `15341` | 40.8 ± 3.4 | 26.8 s, just past the intersection; 10.6 s at the stop | queue south of Grand; Milwaukee & Erie |

The same peak measure at the other two corners:

| Corner | No stop | With a stop | Signal-only control |
|---|---|---|---|
| Wells & Chicago (`18803`) | 3.9, 1.9 | 27.9 | — |
| Orleans & Chicago (`6714`) | 13.8 | 19.1, 19.6 | 18.1, 22.9 (westbound at Orleans) |

Section jumps, the consecutive ping pairs of one trip on opposite sides of the closed section, on the 19 days skipped
on 2026-11-23:

| Days | 9368 | 9376 | 6665 |
|---|---|---|---|
| 2025-08-06 to 08-15 | 54 to 95 | 49 to 99 | 0 (old route, section not on its path) |
| 2025-11-13 to 11-21 | 68 to 102 | 68 to 94 | 44 to 73 |

## Facts confirmed

- **The first detour shows no dwell at the corner.** A stop concentrates its dwell in one or two 50 ft stretches:
  14 s at the old far-side stop and 27 s at today's. In the first detour no stretch in the band holds more than
  5 s; the 15 s is spread over the right turn onto Grand.
- **A band total mixes a dwell with queues and turns. The largest stretch separates them where no signal sits at the
  stop:** Wells & Chicago (2 to 4 s against 28) and Halsted, Grand & Milwaukee (5 against 14 and 27). At Orleans &
  Chicago the signal piles up as much as the stop does (18 to 23 s westbound, with no stop), so the band total against
  the westbound control decides there.
- **The unreported periods are continuous**: route 8 from 2025-08-04 to 08-16 (13 days) and from 2025-11-07 to 11-22
  (16 days), and route 66 west from 2025-10-31 to 11-22 (23 days). Every day has 32 to 102 section jumps, against 0 to
  22 on the other days read.

## Corrections to earlier notes

- `docs/2026-11-23-stop-validity-review-driving-and-corners.md` says the old route's stop (`15274`) piled up 150 to
  250 ft before the corner, outside the band. That pile-up is the signal queue south of Grand. `15274` is a far-side
  stop, and its 14 s dwell sits inside the band. This makes the first-detour reading stronger than that note said.
- The same note assumed the skipped days were like their neighbours; all 19 are now read.

## How to re-check

Run `notebooks/corner_stops_routes_8_66.ipynb`. It fetches any of the 50 raw days of section 1 and the 30 of section 2
it lacks. `CORNER_TABLE` holds `corner_s` and `corner_peak_s`, section 1's table the section jumps, and section 2b
draws the map.
