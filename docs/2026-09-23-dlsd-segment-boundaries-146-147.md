# DLSD express segment boundaries for routes 146 and 147: the one pattern hop over 10,000 ft (measured 2026-09-23)

Tags: `kind:measurement source:bustracker stage:clean topic:thresholds topic:pattern-catalog`

Migrated 2026-11-13 from vault `lsd-express-segment-boundaries` (2026-09-23, from
`notebooks/dlsd_travel_time_146_147.ipynb` section 2). It records how the DuSable Lake Shore Drive (DLSD)
segment of a pattern is found and which stop pairs bracket it for the two all-day express routes. The
pairs were compared with `notebooks/dlsd_boundaries_snapshot.json` for the migration; nothing was fetched.

## Measurement

For each pattern, `getpatterns` stops in order; the largest gap between consecutive stops is the express
segment when it exceeds 10,000 ft (about 1.9 miles). The stop before the gap is the entry, the stop after
it the exit. The result per pid is in `notebooks/dlsd_boundaries_snapshot.json` (`entry_stpid`,
`exit_stpid`, `hop_feet`, `pdist_gap_ft`, `trips`) and is read by
`cta.dlsd_run_quality.load_dlsd_boundaries`.

| Route | Direction | Entry | Exit | PIDs in snapshot | `hop_feet` |
|---|---|---|---|---|---|
| 146 | Northbound | `1128` Michigan & Delaware/Walton | `1155` Inner Lake Shore Drive & Belmont | 8 | about 15,570 |
| 146 | Southbound | `4867` Lake Shore Drive & Belmont | `1097` Michigan & Delaware | 6 | about 15,520 |
| 147 | Northbound | `1128` Michigan & Delaware/Walton | `4847` Foster & Marine Drive | 2 | about 29,150 |
| 147 | Southbound | `4846` Foster & Marine Drive | `1097` Michigan & Delaware | 2 | about 29,100 |

## Facts confirmed

- Both routes share the southern anchor at Michigan & Delaware: `1128` northbound entry, `1097`
  southbound exit. These are also the north end of the Michigan Ave corridor
  (`docs/2026-10-02-michigan-ave-corridor-stops.md`).
- Stop names say "Lake Shore Drive", never "DLSD" or "DuSable"; do not search names for the acronym.
- Not every pattern of a DLSD route uses the Drive. PID 839 (route 147 Northbound, about 9,300 trips)
  starts at Sheridan & Foster, north of the Drive; its largest hop is about 1,000 ft. It is not in the
  snapshot and takes no part in DLSD timing.
- `dlsd_minutes` is the exit arrival minus the entry arrival for the same run and pid, filtered by the
  structural `analysis_ok` flags (`docs/2026-09-23-mansueto-imputation-method.md`). `dlsd_minutes_bin`
  (5-minute floors) exists for reporting at the data's real resolution.

## Corrections

- The vault note gives the 146 segment as about 3.1 miles. The snapshot has `hop_feet` about 15,520 to
  15,570 (2.9 miles), and `pdist_gap_ft` 15,979 (3.0 miles) on PID 7445. Route 147's 5.5 miles agrees.
- The 10,000 ft threshold is written inline in the two discovery notebooks. It is not a named constant
  in `cta/`; whoever moves the discovery into the package names it there (CLAUDE.md conventions).
- The vault note names `notebooks/dlsd_run_quality.py`; it is `cta/dlsd_run_quality.py`.
- The vault note cited `pid-trip-count-skew` and `dlsd-cache-last30d-semantics`, which are not in the repo.

## How to re-check

Compare the table with `notebooks/dlsd_boundaries_snapshot.json`. To rediscover, run section 2 of
`notebooks/dlsd_travel_time_146_147.ipynb` (needs `CTA_API_KEY`, one cached `getpatterns` call per pid).
A pattern change at either end shows up as a different entry or exit stop; update the snapshot and
re-run the DLSD tests.
