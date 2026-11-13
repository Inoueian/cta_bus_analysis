# Michigan Ave bus-lane baseline scope: Roosevelt to Delaware, 19 candidate routes, patterns kept at a 5-minute median (recorded 2026-10-02)

Tags: `kind:measurement source:bustracker source:mansueto topic:thresholds topic:pattern-catalog`

Migrated 2026-11-13 from vault `michigan-ave-bus-lane-segment` (2026-10-02), the scope and method note
for the Michigan Ave side quest (TODO.md, "Michigan Ave Bus Lane Analysis"). It says what is measured,
between which stops, on which routes, and what keeps a pattern in. Counts were compared with the two
committed JSON snapshots for the migration.

## Scope

The new dedicated bus lane is northbound only, Roosevelt to Wacker. The analysis corridor is longer:
Michigan Avenue from Roosevelt to Delaware, both directions, measured before the lane opens.

| End | Northbound | Southbound |
|---|---|---|
| Roosevelt (south) | `1580` Michigan & Roosevelt | `1591` Michigan & Roosevelt |
| Delaware (north) | `1128` Michigan & Delaware/Walton | `1097` Michigan & Delaware |

The Delaware pair is also where the 14x express routes join Lake Shore Drive
(`docs/2026-09-23-dlsd-segment-boundaries-146-147.md`).

## Facts confirmed

| Fact | Value | Where |
|---|---|---|
| Candidate routes (system map) | 19: 1, 2, 3, 4, X4, 6, 7, 10, J14, 26, 28, 125, 126, 143, 146, 147, 148, 151, 157 | `notebooks/michigan_ave_stops_snapshot.json` `candidate_routes` |
| Routes serving a corridor stop | 18 (all but 10, which has no Mansueto PIDs) | same file, `stops[].routes` |
| Corridor stops | 40 | `docs/2026-10-02-michigan-ave-corridor-stops.md` |
| Patterns kept | 45, on 12 routes | `notebooks/michigan_ave_kept_pids.json` |
| Eligibility | median per-run time on the pattern's corridor span of at least 5 minutes | `cta.michigan_ave_segment.DEFAULT_MIN_MEDIAN_MINUTES` |

- The 5-minute rule removes patterns that only clip the corridor. It is also about the resolution of
  Mansueto arrivals: about 5 minutes between pings (`docs/2026-09-23-mansueto-imputation-method.md`).
- `X4` and `J14` must match the `rt` column of `rt_to_pid.csv` exactly; the discovery notebook reports a
  route with no rows.
- Statistics: median, interquartile range, and the slow tail as p95 minutes per mile
  (`60 / q05(speed)`). Day slices: Mon to Thu, Friday, Sat and Sun.

## Corrections

- The first plots used Mansueto's ping-interval `speed_mph` at each stop. ADR-010 redefines corridor
  speed on the segments between consecutive corridor stops, from run-level arrivals and `pdist`
  (`corridor_segment_speeds`, `specs/michigan-segment-from-view.md`). The scope above is unchanged.
- The primary source for new days is the archive, not the frozen Mansueto parquets (ADR-004, ADR-007).
  Route 10 can only come from the archive (TODO.md, "Route 10 / Mansueto catalog gap").
- Weekday slices include holidays (playbook gotcha "Day slices do not exclude holidays").
- The "last30d" cache for the 45 kept PIDs (`scripts/cache_dlsd_parquets.py --source michigan`) covers
  2026-06-28 to 2026-07-28.
- The vault note cited `michigan-ave-pattern-endpoint-coverage`, which is not in the repo.

## How to re-check

`notebooks/michigan_ave_stop_discovery.ipynb` rebuilds the candidate and stop lists (needs `CTA_API_KEY`);
`notebooks/michigan_ave_route_identification.ipynb` re-applies the 5-minute rule and rewrites the kept
list. The 5 minutes is a published threshold: changing it is Rule 2.
