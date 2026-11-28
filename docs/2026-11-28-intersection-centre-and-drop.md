# Halsted, Grand & Milwaukee from the intersection centre: no stop there in the first detour; "drop" adds one run (measured 2026-11-28)

Tags: `kind:measurement source:mansueto source:gtfs topic:pattern-catalog topic:calendar`

Contains data from [Transitland](https://www.transit.land/terms): paths and stops are read from archived CTA GTFS
versions (ADR-013).

Two owner requests of 2026-11-28 for `specs/mansueto-stop-validity.md`:
- **Open question 1:** the band around stop `15341` used on 2026-11-27 says little, because the first detour turned
  from northbound Halsted onto eastbound Grand before reaching the stop, which stands northwest of the intersection.
  Measure instead whether buses stopped anywhere at the intersection, the question under ADR-014 rule 2.
- **Open question 2:** the owner chose to drop arrivals the pings did not observe on the unreported days. Measure what
  that removes (ADR-015).

Notebook: `notebooks/corner_stops_routes_8_66.ipynb` sections 1c and 2b, Findings 2 and 5.

## Measurement

Provenance:
- **Paths, stops and the centre** come from CTA's schedule (planned, via Transitland). The centre is where route 8's
  old path on Halsted crosses route 65's path on Grand, 178 ft southeast of stop `15341`; Milwaukee crosses Halsted
  about 60 ft north of it.
- **Time spent** is derived from GPS positions (observed, via Bus Tracker and Mansueto's raw day files): mean seconds
  per trip per 50 ft of `pdist`, around where each period's path passes the centre, over ten Tue to Thu days per
  period.

| Period | Within 150 ft of the centre (s) | Within 250 ft (s) | Largest 50 ft stretch within 100 ft (s) | Scheduled stops (ft from the centre along the path) |
|---|---|---|---|---|
| Old route (Jul 2025) | 57.2 ± 3.8 | 83.4 ± 4.4 | 26.4 | Hubbard −312, `15274` +69 |
| First detour (Oct 2025) | 19.8 ± 2.5 | 67.2 ± 4.2 | 2.7 | Hubbard −323, Grand & Union +361 |
| Today's detour (Jun 2026) | 49.3 ± 3.6 | 81.6 ± 4.4 | 25.7 | Hubbard −289, `15341` +168 |

**What "drop" removes.** For each stop of today's patterns in the closures' area: the median share of a day's trips
with a ping within 100 m (`MAX_STOP_PING_DISTANCE_FT`), on the unreported days against normal days.
- Route 8: stops with share 0 on the unreported days are today's Division and Milwaukee detour stops (9368: `15368`,
  `15369`, `17834`, `2051`, `5496`, `5500`; 9376: `15374`, `2022`, `5525`, `5527`, `5529`). They are also 0 on normal
  days in July and October, and their reviewed windows open on 2025-11-23. Every other stop keeps a normal share, the
  edge stops included: `18786` 0.26 and 0.27 against 0.26 and 0.38; `5782` 0.24 and 0.26 against 0.21 and 0.18.
- Route 66 west: the stops with share 0 are `5020`, `6613`, `6614` and `769` on Wells and Grand, also 0 in October
  and windowed from 2025-11-23. The first-detour stops keep 0.08 to 0.28, against 0.02 to 0.25 on normal days.

**Mansueto against GPS.** Mansueto's route 8 southbound arrival times on 2025-10-14, a first-detour day, against the
moment the GPS fixes cross each stop's latitude (committed fixture; 98 passes each):

| Stop | Mansueto minus GPS, median (s) | 10th to 90th percentile (s) |
|---|---|---|
| Halsted & Blackhawk (`5779`, north of the detour) | 2 | −32 to 48 |
| Halsted & Lake (`15350`, south of it) | −11 | −83 to 3 |

## Facts confirmed

- **No bus routinely stopped at Halsted, Grand & Milwaukee in the first detour, on either leg.** Within 100 ft of the
  centre, no 50 ft stretch holds more than 3 s. With a stop, one stretch holds 14 to 27 s: the old far-side stop at
  +69 ft, today's just past the centre, Hubbard, Grand & Union. The first detour's pile-ups are the queue back from
  Grand to the Hubbard stop and the approach to Grand & Union, the scheduled stops 323 and 361 ft away. A rarely used
  stop whose mean dwell is a few seconds would not show at this resolution.
- **"Drop" adds no stop-day on routes 8 and 66.** Every stop the pings skipped is a detour stop that its reviewed
  window already drops. What it adds is the one run measured along the old pattern on 2025-11-24.
- **Mansueto's arrival times past a detour follow the bus, not Bus Tracker's pattern.** South of the detour they match
  the GPS passes to within 11 s at the median, though Mansueto's stop list is today's and Bus Tracker's pattern that day
  was the first detour.

## Corrections to earlier notes

- `docs/2026-11-27-corner-map-and-unreported-days.md` read the first detour against the band around stop `15341`
  (peak 5 s). The owner judged that band uninformative here; the centre-based reading (peak 3 s within 100 ft)
  replaces it for Open question 1.

## How to re-check

Run `notebooks/corner_stops_routes_8_66.ipynb`: section 1c (`COVERAGE`, and the Mansueto against GPS table) and
section 2b (`CENTRE_TABLE` and the map).
