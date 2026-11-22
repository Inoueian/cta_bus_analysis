# Stop validity windows for routes 8 and 66: 29 of 38 detour stops get a window at 100 m (measured 2026-11-21)

Tags: `kind:qa source:mansueto stage:clean topic:pattern-catalog topic:thresholds`

The QA note of `specs/stop-validity-measurement.md`. The Mansueto parquet has arrivals at today's route 8 and 66 detour
stops from 2024-09-03, though the buses reached those streets only in late 2025 (`docs/2026-11-15-routes-8-65-66-run-level-qa.md`;
playbook gotcha "Mansueto stop lists do not follow the route the bus took"). This note records, per detour stop, the
first geometry period in which raw pings pass it, now committed as `notebooks/routes_8_65_66_stop_validity.json`
(ADR-011, point 3). No view changes yet: `specs/mansueto-stop-validity.md` has the Mansueto adapter drop the earlier
arrivals. The first run stopped, as the spec asked, on 11 distances near the spec's first threshold rule; the owner then
set the threshold to 100 m, and the spec's Thresholds table was amended the same day.

## Measurement

In a cloud container with no earlier `data/`:

```
python scripts/route_run_level.py --source mansueto --fetch                 # 41 parquets, 24 getpatterns calls; the view
python scripts/route_run_level.py --source mansueto --write-validity        # the four raw sample days fetched beforehand
```

The rebuilt view reproduced the 2026-11-15 detour counts exactly (6662 636,909; 6665 884,215; 9368 354,954; 9376
251,013 arrivals at the added stops before today's geometry). The raw day CSVs of the four sample days are 43 to 44 MB
each, with 1,851 to 2,653 fixes per pid dated that day; each file also holds a few previous-day fixes (12 to 17 rows for
the four pids, none on 2026-09-15), which the measurement ignores by keeping `data_date` equal to the sample day.

`nearest_ping_ft` is the haversine distance from a stop's getpatterns position to the nearest fix of its pattern dated
the sample day. Where the distances fall, in feet:

| Distances | 0–100 | 100–214 | 214–486 | 486–1,000 | over 1,000 |
|---|---|---|---|---|---|
| Every stop of 6662, 6665, 9368, 9376 on 2026-09-15, today's geometry (350) | 345 | 4 | 1 | 0 | 0 |
| The 38 candidate stops, today's geometry | 38 | 0 | 0 | 0 | 0 |
| The 38 candidate stops, earlier periods (65 distances) | 16 | 5 | 0 | 12 | 32 |

Served candidate distances reach 214 ft (9376, Milwaukee & Grand/Halsted, 2025-10-14); unserved ones start at 486 ft
(6665, Milwaukee & Carpenter, 2025-09-16). The one stop of today's patterns between them is Halsted & 54th Street
(9368, `5835`, 448 ft), not a candidate. The spec's first rule (the largest distance over every stop of the four
patterns, rounded up to the next 100 ft) gave 500 ft from that one stop, inside the unserved group: it split Milwaukee &
Carpenter by direction (eastbound 549 ft not served, westbound 486 ft served) and put 11 distances in its 500 to 1,000 ft
stop-and-report band. At 100 m (328 ft), the gap's log-scale middle (323 ft), the nearest distances on either side are
1.53× and 1.48× away, and none lies within the 1.25× margin (262 to 410 ft). Any threshold from 215 to 485 ft gives the
same windows.

Per stop, distance to the nearest ping in each period, in feet, and the window (sample days: 6662 2025-09-16 /
2026-09-15; 6665 2025-09-16 / 2025-10-14 / 2026-09-15; 9368 and 9376 2025-07-15 / 2025-10-14 / 2026-09-15):

| Pid | Stop | Name | Distances (ft) | Valid from |
|---|---|---|---|---|
| 6662 | 18720 | Chicago & Menard | 1 / 1 | — |
| 6662 | 18721 | Chicago & Waller | 54 / 0 | — |
| 6662 | 17834 | Milwaukee & Carpenter | 549 / 1 | 2025-09-27 |
| 6662 | 5500 | Milwaukee & Erie | 1,018 / 0 | 2025-09-27 |
| 6662 | 739 | Grand & Union | 1,930 / 1 | 2025-09-27 |
| 6662 | 741 | 530 W Grand | 1,925 / 7 | 2025-09-27 |
| 6662 | 742 | Grand & Kingsbury | 1,844 / 9 | 2025-09-27 |
| 6662 | 14762 | Orleans & Grand | 1,681 / 17 | 2025-09-27 |
| 6662 | 6712 | Orleans & Erie | 982 / 4 | 2025-09-27 |
| 6662 | 6713 | Orleans & Huron | 701 / 26 | 2025-09-27 |
| 6662 | 6714 | Orleans & Chicago | 88 / 2 | — |
| 6665 | 18803 | Wells & Chicago | 155 / 172 / 1 | — |
| 6665 | 6613 | Wells & Huron | 624 / 629 / 22 | 2025-11-24 |
| 6665 | 6614 | Wells & Ontario | 1,193 / 1,196 / 0 | 2025-11-24 |
| 6665 | 5020 | Wells & Grand | 1,766 / 1,553 / 9 | 2025-11-24 |
| 6665 | 769 | Grand & Franklin | 1,810 / 1,224 / 1 | 2025-11-24 |
| 6665 | 771 | Grand & Kingsbury | 1,801 / 46 / 1 | 2025-09-28 |
| 6665 | 772 | 530 W Grand | 1,880 / 11 / 43 | 2025-09-28 |
| 6665 | 15672 | Grand & Desplaines | 1,881 / 0 / 4 | 2025-09-28 |
| 6665 | 15341 | Milwaukee & Grand/Halsted (Blue Line) | 1,773 / 17 / 30 | 2025-09-28 |
| 6665 | 5525 | Milwaukee & Erie | 1,002 / 27 / 29 | 2025-09-28 |
| 6665 | 5527 | Milwaukee & Carpenter | 486 / 14 / 0 | 2025-09-28 |
| 6665 | 18794 | Chicago & Milwaukee (Blue Line) | 96 / 0 / 13 | — |
| 6665 | 18802 | Chicago & Noble | 15 / 76 / 20 | — |
| 9368 | 5782 | Halsted & Division | 56 / 28 / 0 | — |
| 9368 | 15368 | Division & Hooker | 881 / 890 / 59 | 2025-11-25 |
| 9368 | 2051 | Division & Cherry | 1,587 / 1,600 / 1 | 2025-11-25 |
| 9368 | 15369 | Division & North Branch | 2,118 / 2,133 / 10 | 2025-11-25 |
| 9368 | 5496 | Milwaukee & Chicago | 2,164 / 2,944 / 1 | 2025-11-25 |
| 9368 | 17834 | Milwaukee & Carpenter | 1,483 / 2,027 / 9 | 2025-11-25 |
| 9368 | 5500 | Milwaukee & Erie | 990 / 1,331 / 37 | 2025-11-25 |
| 9368 | 18786 | Halsted & Grand/Milwaukee (Blue Line) | 198 / 1 / 5 | — |
| 9376 | 15341 | Milwaukee & Grand/Halsted (Blue Line) | 110 / 214 / 20 | — |
| 9376 | 5525 | Milwaukee & Erie | 944 / 1,334 / 37 | 2025-11-23 |
| 9376 | 5527 | Milwaukee & Carpenter | 1,557 / 2,141 / 8 | 2025-11-23 |
| 9376 | 5529 | Milwaukee & Chicago | 2,163 / 2,952 / 11 | 2025-11-23 |
| 9376 | 2022 | Division & Cherry | 1,691 / 1,698 / 0 | 2025-11-23 |
| 9376 | 15374 | Division & Hooker | 824 / 836 / 41 | 2025-11-23 |

## Facts confirmed

- **29 of the 38 candidate stops have a window**: 6662, 8 from 2025-09-27; 6665, 6 from 2025-09-28 (Grand and
  Milwaukee) and 4 from 2025-11-24 (Wells and Grand & Franklin); 9368, 6 from 2025-11-25; 9376, 5 from 2025-11-23. Every
  window opens on one of the pid's `geometry_changes`.
- **Route 8's detour stops were not served during the first detour.** Every 9368 and 9376 window opens on the second
  change (late November 2025): the stops of today's Division and Milwaukee detour are 824 ft or more from every ping on
  2025-07-15 and 2025-10-14.
- **Nine candidates have no window**: they lie within 214 ft of a ping in every period. Eight are on or beside the older
  routes: four on Chicago Avenue, which route 66 always served (Chicago & Menard and Chicago & Waller, the stop-id swaps
  the spec names, and Chicago & Noble and Chicago & Milwaukee), Orleans & Chicago, Halsted & Division and the two Blue Line
  stops at Halsted, Grand and Milwaukee. The ninth is Wells & Chicago (below).
- **No stop is served, then not, then served again**, and every candidate's first arrival is 2024-09-03, the day
  Mansueto's stop lists switched.
- **The method cannot see a detour stop at a corner of the old route.** Wells & Chicago (6665, `18803`) is 155 and 172 ft
  from the pings of the old route, so it reads as served and keeps its arrivals from before 2025-11-24, though it is
  probably a detour stop like the other three on Wells. Accepted by the owner as a documented limit (spec, Decisions).

## Corrections to earlier notes

- `specs/stop-validity-measurement.md` estimated ~30 to 36 windows; 29 were measured. It expected Wells & Chicago from
  2025-11-24; it has no window, for the reason above. Its first threshold rule is replaced (Thresholds, amended
  2026-11-21).

## How to re-check

Build the view without windows (`python scripts/route_run_level.py --source mansueto --fetch`; with `--no-validity` once
`specs/mansueto-stop-validity.md` lands), then run `python scripts/route_run_level.py --source mansueto --write-validity
--fetch`. It prints the stops of today's patterns farther than the threshold (here only `5835`, 448 ft) and stops if any
candidate distance falls within 1.25× of it. `python -m pytest tests/test_stop_validity.py` checks the committed JSON. A
different JSON means the parquets, a raw day file or a getpatterns answer changed; check each one's `.meta.json` and the
pattern cache before the code.
