# What set the committed change dates for routes 8 and 66: one trip each, while Bus Tracker measured 99 to 100% of pings along the path driven (measured 2026-11-23)

Tags: `kind:measurement source:bustracker source:mansueto topic:calendar topic:pattern-catalog`

`docs/2026-11-23-stop-validity-review-driving-and-corners.md` found that three of the dated changes in
`notebooks/routes_8_65_66_pids.json` (`geometry_changes`), on which the committed stop windows open, are a day or two
off the day the buses changed route. It explained the gap as Bus Tracker switching the pattern early or late, and the
playbook added that on those days `pdist` measured real positions along the wrong street. This note tests that
explanation and corrects it. The driving dates, and the 18 window moves that follow from ADR-014, stand.

## Measurement

Provenance first:
- **Ping lat/lon** is the bus's GPS fix: observed, from Bus Tracker's vehicle feed via Mansueto's raw day files.
- **Ping `pdist`** is Bus Tracker's projection of that fix onto the pattern it holds for the trip: derived, from the
  same rows.
- **`geometry_changes`** is our statistic. It is the first calendar day whose longest `pdist` fits the new pattern's
  length within 0.05 mi (`notebooks/eda_routes_8_65_66.ipynb` 6.2b).

On the four days where that date and the driving date differ, each ping's GPS position was projected onto both
candidate paths from the archived GTFS. Where the two paths' distances differ by more than 1,000 ft, the test is which
projection reproduces the reported `pdist` within 200 ft (`notebooks/corner_stops_routes_8_66.ipynb` section 1b):

| Day | Pid | Buses drove | Pings where the paths differ | `pdist` fits the path driven | Fits the other |
|---|---|---|---|---|---|
| 2025-09-27 | 6662 | old route | 888 | 100% | 0% |
| 2025-11-23 | 6665 | today's detour | 66 | 100% | 0% |
| 2025-11-23 | 9368 | today's detour | 742 | 99% | 1% |
| 2025-11-24 | 9368 | today's detour | 1,332 | 99% | 1% |

The pings whose `pdist` exceeds the shorter pattern's length by more than 0.05 mi, which are the ones that decide a
"longest `pdist`" date:

| Day | Pid | Chicago time | Vehicle | Trip | `pdist` (ft) | Fits | What the trip was |
|---|---|---|---|---|---|---|---|
| 2025-09-27 | 6662 | 23:24 | 2025 | 267694636 | 50,160 | detour | last old-route trip of the night: 13 pings on Chicago Avenue fit the old path; the final ping, at the east terminal both paths share, is on the detour pattern |
| 2025-11-23 | 6665 | 01:29 to 01:44 | 8682 | 267694801 | 49,799 to 49,819 | first detour | owl trip of service day 11-22, after midnight in the 11-23 file |
| 2025-11-23 | 9368 | 00:14 | 1287 | 267698789 | 81,065 | first detour | owl trip of service day 11-22, after midnight in the 11-23 file |
| 2025-11-24 | 9368 | 19:49 | 1286 | 267681506 | 81,548 | first detour | one trip (18:19 to 19:49) measured along the old pattern for its whole run, with no ping for 11 minutes across the detour section |

## Facts confirmed

- **Bus Tracker measured `pdist` along the path the buses drove** on every changeover day, for 99% to 100% of pings.
  It did not hold the wrong pattern for a day.
- **A day's longest `pdist` is set by single pings.** One trip set each of the three committed dates that differ from
  driving, in three ways:
  - 6662: one ping at a shared terminal already on the new pattern made 09-27 the first "new" day.
  - 6665 and 9368: owl trips of the previous service day kept 11-23 "old". The raw files are calendar days (playbook
    gotcha "Mansueto raw day files are calendar days, not service days").
  - 9368: one evening trip on the old pattern kept 11-24 "old".
- **Single trips around a change can carry the other pattern.** The 9368 trip on 2025-11-24 (vehicle 1286) was
  measured along the first detour for its whole run and went unreported where the paths differ. Arrivals imputed for
  that trip are suspect; the rest of the day's trips are not.

## Corrections to earlier notes

- `docs/2026-11-23-stop-validity-review-driving-and-corners.md` labels the committed dates "Bus Tracker pattern switch"
  and states that the pattern switched a day early on 6662 and one to two days late on 6665 and 9368. The committed
  dates are each calendar day's longest `pdist`. Bus Tracker's pattern for the day matched the driving, and one trip
  set each differing date. Its correction bullet ("it is the day Bus Tracker's pattern changed") is wrong for the same
  reason.
- ADR-014's context attributes the offsets to Bus Tracker's pattern switching early or late, and its point 1 glosses
  "the longest `pdist`" as the day the pattern switched. The mechanism is the one above. The decision (date by ping
  positions, not by a day's longest `pdist`) is unaffected.
- `docs/2026-11-13-routes-8-65-66-eda.md` and `docs/2026-11-21-stop-validity-windows.md` call `geometry_changes` the
  day the geometry changed. It is the first calendar day whose longest `pdist` fits the new pattern, which a single
  trip or an owl trip of the previous service day can move by a day.
- The playbook entries written on 2026-11-23 said that on changeover days `pdist` measured positions along the wrong
  street and that arrivals were suspect for the whole stretch past the change. They are corrected in place: only the
  single trip above is suspect.

## How to re-check

Run `notebooks/corner_stops_routes_8_66.ipynb` section 1b. It reads the four raw day files and the archived paths
already cached by sections 1 and 2.
