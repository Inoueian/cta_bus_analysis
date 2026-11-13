# Michigan Ave corridor stop list: 51 candidate stops, 11 excluded, 40 on the avenue (measured 2026-10-02)

Tags: `kind:measurement source:bustracker stage:clean topic:pattern-catalog`

Migrated 2026-11-13 from vault `michigan-ave-corridor-stops-snapshot` (2026-10-02). It records how the
frozen stop list in `notebooks/michigan_ave_stops_snapshot.json` was built, including the exclusion list,
which the JSON does not hold. Counts and the metadata quirk were checked against the JSON for the
migration; nothing was fetched.

## Measurement

`notebooks/michigan_ave_stop_discovery.ipynb`, 97 patterns fetched with `batch_pattern_stops` for the
candidate routes (`docs/2026-10-02-michigan-ave-corridor-scope.md`):

1. Deduplicate the `getpatterns` stop catalog of every candidate-route pid.
2. Keep a stop when its name contains "Michigan" (any case) and its latitude is in [41.865, 41.902],
   or when it is one of the Delaware anchors `1097`, `1128`.
3. Deduplicate by (`stpid`, `stpnm`, `lat`, `lon`); aggregate `routes`, `rtdirs`, `n_patterns`.
4. Remove the stops in the notebook's `EXCLUDE_CORRIDOR_STPIDS` (section 4.5).

| Step | Stops |
|---|---|
| After the name and latitude filter | 51 |
| Excluded in section 4.5 | 11 |
| In the snapshot | 40 |

| Excluded `stpid` | Reason given in the notebook |
|---|---|
| `1592`, `1579` | side-street stops at Michigan intersections |
| `15362`, `17084` | named for Roosevelt but off the avenue (the on-avenue stops are `1591`, `1580`) |
| `4870`, `4884`, `74`, `4725`, `14482`, `1421`, `1129` | side-street stops at Michigan intersections |

The vault adds that the notebook also drops 13th St (south of Roosevelt) and Oak (north of Delaware); it
does not say which of the eleven ids those are.

## Facts confirmed

- On-avenue anchors: Roosevelt `1591` southbound and `1580` northbound; Delaware `1097` southbound and
  `1128` northbound.
- 19 candidate routes, 18 of them on at least one snapshot stop. Route 10 has no rows in `rt_to_pid.csv`,
  so the Mansueto path has no PID for it (playbook gotcha "`rt_to_pid.csv` is stale and incomplete").
- The snapshot's `corridor.roosevelt_stpids` still lists `15362` and `17084`, two of the excluded
  side-street stops. Neither is in `stops`. Use `1591` and `1580`.
- The exclusion list is not serialized: the JSON has no `exclude_stpids`. The policy lives only in
  section 4.5 of the notebook and in the table above.

## Corrections

- The vault note says the notebook fetches patterns "via `cta_api`"; the module is `cta.bustracker`.
- The stop list is a published exclusion set. Changing which stops are in it is Rule 2, and
  `corridor_stops_from_view` and `direction_stop_sequences` read it.

## How to re-check

Load the JSON: 40 `stops`, `patterns_fetched` 97, latitude band in `corridor`. To rebuild, run the
discovery notebook with `WRITE_SNAPSHOT=False` and compare (needs `CTA_API_KEY`; cached patterns cost no
calls). A stop CTA adds or moves shows up as a row outside the 40.
