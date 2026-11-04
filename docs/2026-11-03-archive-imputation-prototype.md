# Archive stop-imputation prototype (2026-11-03)

Findings from a one-day prototype that produced stop arrival times from the Transit Alerts
position archive for the Michigan Ave corridor. Script: `scripts/proto_archive_imputation.py`.
This is exploratory evidence behind ADR-004 and `specs/archive-adapter.md`; the production
implementation belongs in `cta/`, not in this script.

## Setup

- Day: Thu 2026-10-29, `positions/bus/2026/10/2026-10-29.ndjson.gz`
  (SHA-256 `c0ec20986e19708f6e921765ccd0eea07a72261d2c651e314033115305577774`, 1,083,422 rows,
  1,615 vehicles, 124 routes, 678 patterns).
- Stops: the 40 corridor stops in `notebooks/michigan_ave_stops_snapshot.json`.
- Patterns: the 45 kept PIDs in `notebooks/michigan_ave_kept_pids.json`.
- Cleaning: scorecard.sql steps 1–2 only (dedup on trip key + `vehicle_ts`; trip key
  `(vehicle_id, pid, sched_start_date, sched_start_sec)`). No terminal trim, no geometry filters.
- Stop `pdist` per pattern: median `pdist` of fixes within 40 m of the stop (fallback used because
  no Bus Tracker key was available). Production must use `getpatterns` `pdist` instead.
- Arrival time: `vehicle_ts` interpolated between the bracketing fixes at the stop's `pdist`,
  bracket gap ≤ 180 s, earliest crossing kept per (run, stop).

## Feed facts on that day

| Measure | Value |
|---|---|
| Poll interval p5 / p50 / p95 | 59 / 60 / 61 s |
| Per-bus fix spacing p5 / p50 / p95 | 39 / 60 / 80 s |
| Clean fixes on the 45 kept patterns | 118,014 rows, 1,582 runs |
| Imputed arrivals | 16,740 (run, stop) rows over 1,474 runs; 0 duplicate crossings |
| Bracket gap p50 / p90 / p99 | 62 / 78 / 90 s |
| Stop-projection spread (p90 − p10 of nearby pdist) | p50 101 ft, p90 186 ft |

The Sunday 2026-11-01 file has 1.25M rows against ~1.08M on a weekday: the collector's switch to
30-second polling. Earlier files are 60-second polls.

## Validation against Mansueto

Per-pattern corridor minutes (entry stop → exit stop) on the archive day versus the Mansueto
last-30-day medians stored in `michigan_ave_kept_pids.json` (window ending ~2026-10-03):

| Pattern | Route / dir | Archive median (n) | Mansueto median (n) |
|---|---|---|---|
| 6414 | 151 NB | 11.4 (92) | 11.6 (2,875) |
| 8102 | 151 SB | 14.6 (97) | 15.6 (2,860) |
| 4524 | 147 NB | 11.7 (73) | 10.5 (2,343) |
| 4526 | 147 SB | 18.9 (66) | 19.2 (2,196) |
| 18414 | 3 NB | 19.0 (110) | 19.6 (3,018) |
| 18415 | 3 SB | 20.9 (112) | 21.4 (3,237) |
| 19378 | 4 NB | 8.2 (99) | 9.4 (3,140) |
| 19379 | 4 SB | 13.6 (104) | 13.2 (3,053) |
| 6402 | 148 SB | 7.5 (25) | 7.4 (479) |
| 14132 | 157 EB | 4.7 (58) | 5.1 (1,133) |

Across the 24 patterns with results on both sides, the median of (archive median ÷ Mansueto
median) is 0.993. The 21 patterns without an archive result were low-volume patterns (≤ 12 runs
that day) where the 40 m projection found fewer than 8 fixes near the entry or exit stop, plus
pattern 1054 which did not run. With `getpatterns` pdist this gap goes away.

## Things the resolution exposed

- **Incident.** Southbound corridor minutes for routes 147, 151, 146 and 3 roughly doubled or
  tripled for runs entering between ~10:24 and ~10:45 (e.g. 147 at 10:24: 39.4 min; 151 at
  10:26: 35.0; 3 at 10:30: 37.1), while route 4, which enters further south at South Water, was
  unaffected (12–13 min throughout). Something blocked Michigan Ave southbound north of the river
  for ~20 minutes. Five-minute pings would smear this.
- **Headways at Michigan & Chicago NB (stop 1126), 07:00–20:00.** Route 151 alone: n=67, p50 10.7
  min, p90 19.5, max 41.4. All kept NB routes pooled: n=287, p50 1.9, p90 5.9, max 25.5.
- **Catalog drift.** Patterns running on 2026-10-29 that are absent from the kept list: route 6
  PID 7107 (79th/South Shore, 100 runs), route 4 PIDs 28326–28329, route 147 PID 839. Route 10
  (PID 29277) is present in the archive although absent from Mansueto's `rt_to_pid.csv`.

## Handoff: next session

Project skills `/spec`, `/adr` and `/implement` exist under `.claude/skills/`; use them.

1. Confirm `CTA_API_KEY` is present (do not print it), then make one `getpatterns` call through
   `notebooks/cta_api.py` for PID 6414 to verify the key and the daily budget counter.
2. `specs/package-migration.md` is a draft with two open questions; once the owner marks it
   `ready`, run `/implement` on it first. It needs no key and it creates the `cta/` package that
   the archive adapter's outputs are specified to live in.
3. Then `/implement specs/archive-adapter.md` (status: ready). Start with the fixture: this day's
   file filtered to the 45 kept PIDs, plus `getpatterns` JSON for those PIDs, under
   `tests/fixtures/`. The day file's SHA-256 is in Setup above.
4. The reference pipeline this builds on is the MIT-licensed
   https://github.com/MisterClean/cta-bus-speed-scorecard (`scripts/transit_archive.py` for ingest,
   `scripts/bus-speed-scorecard/scorecard.sql` steps 1–7 for cleaning). Clone it read-only; keep
   attribution when porting.
5. Archive host: `https://data.chicagotransitalerts.app/positions/index.json`. Fetch with `curl`;
   Python `urllib` with its default User-Agent gets a 403.
