# Mansueto raw day 2026-10-22 through the archive stages: 420 s keeps 98.3% of pairs, `tmstmp` is truncated (measured 2026-11-10)

Tags: `kind:measurement source:mansueto source:archive stage:impute topic:thresholds`

Measured while drafting `specs/mansueto-raw-adapter.md` (ADR-009, TODO Foundation "Mansueto raw-positions
adapter"). It is the evidence for that spec's gap threshold, timestamp offset, run key caveats and fixture
estimates, and it answers the TODO item's "verify with a HEAD" about history before 2026-08-13. It adds to
`docs/2026-11-06-mansueto-raw-positions.md` (one day, 2026-09-15, profiled without the pair stages).

## Measurement

`full_day_data/2026-10-22.csv` (43,877,441 bytes, `Last-Modified` 2026-10-23 10:02:16 UTC) and the archive
bus day 2026-10-22 (38,199,698 bytes) were downloaded to a scratch directory (not `data/`, not a fixture)
and read with DuckDB. The CSV rows of the 45 Michigan kept PIDs (`notebooks/michigan_ave_kept_pids.json`)
were keyed by `vid-pid-origtatripno-data_date`, deduplicated on (run, `tmstmp`) keeping min `pdist`, and
passed to `cta.archive.fix_pairs` and `cta.archive.impute_arrivals` with the committed getpatterns files
and `MAX_BRACKET_GAP_S` overridden in memory. Ten HEAD requests probed other day files.

| Quantity (2026-10-22) | Full day | 45 kept PIDs |
|---|---|---|
| Rows | 212,797 | 23,453 (44 PIDs present; 1054 absent) |
| Vehicles / patterns / routes / polls | 1,618 / 668 / 122 / 288 | 388 vehicles |
| Null `origtatripno` | 3,265, all route 47 (3,265 of its 3,295 rows; `tatripid` never null) | 0 |
| Rows with `data_date` 2026-10-21 | 4 (`tmstmp` 23:55 to 23:58) | 0 |
| Fixes after dedup / runs | | 23,393 / 1,559 |
| Consecutive-fix pairs | | 21,834 |
| Pair gap 240 / 300 / 360 s | 19.0% / 57.6% / 18.8% | 19.4% / 58.5% / 19.2% |
| Pairs over 360 / 420 / 660 / 900 s | | 447 / 334 / 85 / 51 |
| Stand-still pairs (Δpdist = 0, gap ≤ 420 s) | | 1,169 |
| Gzip of header plus kept lines (level 9, mtime 0) | | 728,627 bytes (4,897,441 raw) |

Pair and imputation stages on the kept PIDs, by gap cap:

| Gap cap | Pairs kept | `gap_over_max` | `backward_pdist` | `geometry_unsupported` | `speed_over_max` | Crossings | Arrivals | Runs with an arrival |
|---|---|---|---|---|---|---|---|---|
| 180 s (archive constant) | 190 | 21,640 | 1 | 3 | 0 | 398 | 398 | 140 |
| 420 s | 21,454 | 334 | 26 | 20 | 0 | 95,930 | 95,925 | 1,531 |
| 660 s | 21,696 | 85 | 30 | 23 | 0 | 97,668 | 97,663 | 1,532 |

At 420 s: zero (run, stop) duplicates, `bracket_gap_s` p10 / p50 / p90 / max = 240 / 300 / 360 / 420 s,
5 `later_crossing`, runs per PID p50 16.5 (max 117).

## Facts confirmed

- **Gaps are multiples of 60 s clustered at 240, 300 and 360** (97% of pairs), because the poll is ~300 s
  and `tmstmp` has minute resolution. A second cluster at 540 to 660 s is one missed poll. 420 s (the
  largest poll spacing seen, 348 s, plus a minute of rounding) keeps every single-poll pair and drops
  1.5% of pairs; 660 s would add 1.8% more arrivals, each bracketed by ten minutes.
- **`tmstmp` is truncated to the minute, not rounded.** Matching CSV fixes to archive fixes on
  (vehicle, pid, `pdist`) where that `pdist` occurs once per vehicle on each side: 10,145 of 10,933 matches
  have archive `vehicle_ts` minus CSV `tmstmp` in [0, 60) s (1,130 in [−30, 30)); within the minute the
  mean is 45.8 s and the median 49 s, because archive `vehicle_ts` seconds pile up at :51 to :57. Unshifted
  CSV times are therefore about 46 s early on average.
- **`tmstmp` is America/Chicago wall time**; the day file holds local 00:00 to 23:55.
- **The file is a calendar day, not a service day.** 23 of 1,559 kept runs have their first fix by 00:05
  and 31 their last at 23:50 or later; with `data_date` in the key such runs are split across two files.
  1,394 arrivals (29 runs) fall before 04:00 Chicago and carry the calendar date, where the archive's
  `sched_start_date` would give the previous day.
- **`origtatripno` is null for route 47** on this day (zero nulls on 2026-09-15); a run key built from it
  drops that route.
- **The route 47 nulls are all on six patterns, 502450 to 502455**; its pattern 3449 has none. Routes 8,
  65 and 66 have zero null `origtatripno` on this day. `tatripid` is coarser than `origtatripno`
  (16,380 against 18,286 run keys over the non-null rows; route 65: 167 against 185), so it cannot replace it.
- **Fixes before 04:00 Chicago**: route 66 239 of 5,184, route 8 123 of 5,020, route 65 5 of 2,375.
- **No pid carries a `.0` suffix** in the CSV (0 of 212,797 rows).
- **History exists before the ADR-009 window.** HEAD 200 for 2022-05-19 (1.06 MB, a partial first day),
  2022-05-20 (28.3 MB), 2023-06-15 (31.1 MB), 2025-03-12 (43.1 MB) and 2026-07-27; 404 for 2026-10-28 and
  2026-11-09. Four sampled days, not a sweep: coverage between them is unmeasured.

## Corrections to earlier notes

- `docs/2026-11-06-mansueto-raw-positions.md` reports zero null `origtatripno` from 2026-09-15; that does
  not hold on every day (route 47 above).
- TODO.md Foundation item: "verify with a HEAD before planning on history" is answered: files exist from
  2022-05-19, sampled. The scraper is still stopped at 2026-10-27.

## How to re-check

```bash
curl -sS -I -A "cta-bus-analysis/0.1" https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/full_day_data/2026-10-22.csv
```

`bytes` or `Last-Modified` other than the values above means the day was rewritten and every number here
needs re-measuring. Once `specs/mansueto-raw-adapter.md` is implemented its fixture pins the kept-PID
column; `cta.mansueto_raw.qa` on that fixture reproduces the 420 s row.
