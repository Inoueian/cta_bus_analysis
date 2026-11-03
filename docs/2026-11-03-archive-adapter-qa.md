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

## Pending: getpatterns fixture

`tests/fixtures/getpatterns/getpatterns_<pid>.json` for the 45 kept PIDs is not committed yet: this
session's egress policy refused `www.ctabustracker.com`. Build it with
`python scripts/build_archive_fixtures.py --getpatterns` (45 API calls at most, cached afterwards),
then the two skipped tests in `tests/test_views_archive.py` (≥ 16,000 (run, stop) rows; corridor
medians within 10% of Mansueto) run for real. Until then the view is exercised end to end only by
`test_run_level_from_synthetic_pattern_cache`.
