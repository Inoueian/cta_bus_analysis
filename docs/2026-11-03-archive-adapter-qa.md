# Archive adapter: fixture QA and conventions (2026-11-03)

Implementation notes for `specs/archive-adapter.md` (package `cta/`: `archive.py`, `patterns.py`,
`calendar.py`, `views.py`). Durable facts a later session should not have to rediscover.

## Fixture

`tests/fixtures/archive_2026-10-29_michigan.ndjson.gz` is the archive bus day 2026-10-29 (index
SHA-256 `c0ec2098…7774`, 1,083,422 rows) filtered to the 45 kept Michigan Ave PIDs, lines kept
verbatim and in order, gzip with mtime 0. Its manifest `archive_2026-10-29_michigan.index.json` has
the same shape as the archive `index.json` (`days[].files.bus.{path,rows,bytes,sha256}` plus
`known_gaps`), so `cta.archive.ingest_day` verifies it the same way it verifies a real day.
Built by `scripts/build_archive_fixtures.py --day-file`.

| Fixture fact | Value |
|---|---|
| Raw rows (45 PIDs) | 118,995 |
| Null `pid`, `pdist`, `vehicle_ts`, `sched_start_date`, `sched_start_sec` in the full day | 0 |
| `sched_start_date` format | `YYYY-MM-DD` (all 1,083,422 rows), spanning 2026-10-28 and 2026-10-29 |
| Fixture bytes / SHA-256 | 3,786,483 / `db3caae6…0e0e` |

## QA table on the fixture day

`cta.archive.qa(con, "2026-10-29")` after `clean_fixes` and `fix_pairs` with the archive's
`known_gaps`:

| stage | rows_in | rows_out | reason | count |
|---|---|---|---|---|
| ingest | 118,995 | 118,995 | — | 0 |
| clean | 118,995 | 118,014 | duplicate_fix | 981 |
| pairs | 116,432 | 115,898 | gap_over_max | 355 |
| pairs | | | backward_pdist | 117 |
| pairs | | | geometry_unsupported | 61 |
| pairs | | | speed_over_max | 1 |

1,582 runs; pairs rows_in = fixes − runs. Bracket gap on kept pairs p50 / p90 / p99 = 60 / 75 / 90 s,
matching the prototype. The imputation stage is pending the getpatterns fixture (see below).

## Conventions the code fixes

- **One reason per dropped row.** Pair filters are evaluated in `PAIR_REASON_PRIORITY` order
  (`spans_known_gap`, `gap_over_max`, `backward_pdist`, `geometry_unsupported`, `speed_over_max`) and
  the first failing rule is the reason. Unlike the scorecard's overlapping flags, counts are
  additive: `_record_qa` asserts `sum(count) == rows_in − rows_out` for every stage.
- **Known gaps drop pairs, flag days.** A pair whose `(t0, t1)` overlaps a bus `known_gaps` window is
  dropped (no arrival can be interpolated across it). The run-level view additionally carries
  `calendar_flag` (`known_gap_day`, `holiday:<name>`, `;`-joined, `''` otherwise) and never drops rows.
- **Null drop includes the trip key.** `clean_fixes` drops rows missing `pid`, `pdist`, `vehicle_ts`,
  `sched_start_date` or `sched_start_sec` (reason `null_run_key_or_pdist`); the spec listed the first
  three, but a run_id built from a null key is junk. Zero rows affected on the fixture day.
- **Stop on the first fix is crossed.** `p0 <= stop_pdist < p1`, so a stop exactly at a fix's pdist is
  attributed to the pair starting there (arrival = t0), never double-counted by the previous pair.
- **Timestamps.** `vehicle_ts` and `arrival_time` are tz-aware UTC at every boundary; `service_date`
  is the `sched_start_date` string (post-midnight trips keep the scheduled date).

## Validation against Mansueto (getpatterns fixture, fetched 2026-11-03)

`tests/fixtures/getpatterns/` holds the raw `getpatterns` response for the 45 kept PIDs (1.1 MB).
With it, `run_level_from_archive` on the fixture day gives **103,364 (run, stop) rows over 1,562 runs
and 44 patterns, zero duplicates** (impute stage: 103,379 crossings, 15 `later_crossing`). Per-pattern
corridor minutes (entry → exit, legacy `trip_segment_minutes`) against the Mansueto 30-day medians
in `michigan_ave_kept_pids.json`, patterns with ≥ 30 runs on the day:

| PID | Route / dir | n | Archive median | Mansueto median | Ratio |
|---|---|---|---|---|---|
| 8085 | 1 NB | 30 | 4.9 | 5.2 | 0.945 |
| 6582 | 146 NB | 58 | 9.9 | 9.5 | 1.046 |
| 7451 | 146 SB | 62 | 8.5 | 8.4 | 1.006 |
| **4524** | **147 NB** | 71 | 11.7 | 10.5 | **1.121** |
| 4526 | 147 SB | 71 | 18.9 | 19.2 | 0.987 |
| 6414 | 151 NB | 90 | 11.3 | 11.6 | 0.978 |
| 8102 | 151 SB | 97 | 14.5 | 15.6 | 0.927 |
| 14132 | 157 EB | 58 | 4.6 | 5.1 | 0.908 |
| 14130 | 157 WB | 58 | 6.8 | 7.5 | 0.909 |
| **8119** | **26 SB** | 33 | 16.4 | 19.1 | **0.856** |
| 18414 | 3 NB | 110 | 19.0 | 19.6 | 0.970 |
| 18415 | 3 SB | 112 | 20.9 | 21.4 | 0.975 |
| **19378** | **4 NB** | 99 | 8.2 | 9.4 | **0.881** |
| 19379 | 4 SB | 103 | 13.6 | 13.2 | 1.030 |
| 14134 | 6 NB | 70 | 8.3 | 9.1 | 0.911 |
| 19372 | X4 NB | 32 | 8.7 | 9.4 | 0.916 |
| 19374 | X4 SB | 33 | 13.9 | 13.5 | 1.029 |

Median ratio 0.970 over these 17, 0.985 over all 43 patterns with a result. Three patterns are
outside the spec's 10% bound; 4524 and 19378 were already at 1.11 and 0.87 in the prototype table
the spec cites, so the bound was set too tight for one day against a 30-day median taken a month
earlier (Mansueto window ended ~2026-10-03). The owner widened the bound to 20% the same day
(ADR-006); `test_corridor_minutes_match_mansueto_medians` passes with every pattern inside it. A
same-day archive vs Mansueto comparison, once the Mansueto adapter exists, is the place to look for
systematic bias that a 20% bound would not catch.

Two patterns have view rows but no run with both corridor endpoints: 4512 (143 SB, 0 of its runs)
and 1054 (3 NB, did not run). Worth a look when the catalog refresh item runs.
