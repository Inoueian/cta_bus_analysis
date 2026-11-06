# Mansueto raw daily positions: 71 day files from 2026-08-13 to 2026-10-27, none since (measured 2026-11-06)

Tags: `kind:measurement source:mansueto source:archive stage:fetch topic:calendar`

Measured while reviewing the Mansueto `cta-stop-watch` repository for reusable prior art. The
per-pattern parquets are frozen at 2026-07-28 (ADR-007), but the scraper that feeds them is a separate
cloud function (`ghostbus-cta-scrape/` in that repository) and publishes one raw-position CSV per
service day at `https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/full_day_data/YYYY-MM-DD.csv`.
Those files kept appearing after the processed data stopped. This corrects the coverage statement in
ADR-007 and `docs/2026-11-04-mansueto-data-edge.md` and bears on the calendar and cross-source TODO
items; it does not decide whether the files become a source (that is an ADR).

## Measurement

One `curl -I` per day from 2026-07-28 to 2026-11-05 (100 HEAD requests, nothing downloaded), then one
full day (2026-09-15, 44.3 MB, inside the coverage hole) read with DuckDB in a scratch directory
(not `data/`, not a fixture). The metrics parquet was probed by HTTP range requests with pyarrow
(122 requests, 33 MB read of 356 MB). The DigitalOcean Spaces archives the upstream README links
(`patterns_raw.zip`, `processed_by_pid.zip`, `clean_timetables.zip`, `rt_to_pid.parquet` on
`cta-stop-watch-bucket-do.nyc3.cdn.digitaloceanspaces.com`) were not probed: this environment's
network proxy refuses that host, so their state is unknown.

| Window | Day files | Note |
|---|---|---|
| 2026-07-27 | present | `Last-Modified` 2026-07-28 10:05 UTC, the last day the parquets also include |
| 2026-07-28 to 2026-08-12 | absent (16 days) | covered by no source |
| 2026-08-13 to 2026-09-27 | 46 of 46 present | the only positions for these days; the archive starts 2026-09-28 |
| 2026-09-28 to 2026-10-27 | 25 of 30 present | missing 09-30, 10-02, 10-03, 10-16, 10-17; the archive has all 30 |
| 2026-10-28 to 2026-11-05 | absent (9 days) | last file written 2026-10-28 10:02 UTC |

Files are written at about 10:02 UTC on the following day. Sizes: weekdays 42 to 45 MB, Saturdays
about 31 MB, Sundays about 26 MB.

Other endpoints on the same bucket, re-probed the same day:

| File | `Last-Modified` | Fact |
|---|---|---|
| `processed_by_pid/trips_6410_full.parquet` | 2026-07-28 10:19 UTC | still frozen (ADR-007 holds for imputed arrivals) |
| `rt_to_pid.csv` | 2025-01-16 | unchanged (playbook gotcha) |
| `metrics/stop_metrics_df_latest.parquet` | 2026-11-05 10:02 UTC | 10,210,272 rows, 38 columns; `month_abs` rows with actual-service medians end 2026-07, schedule-only rows continue to 2026-09 |

So upstream the scraper, the GTFS download and the monthly metrics job still run; only the stop-time
imputation step (`report_automation/calculate_stop_time.py`) stopped after 2026-07-28, and the scraper
itself has been down since 2026-10-28.

## Profile of 2026-09-15

| Quantity | Value |
|---|---|
| Rows | 214,831 |
| Vehicles / patterns / routes | 1,609 / 667 / 122 |
| Scrape files (`scrape_file`) | 288, one per poll |
| Poll spacing p10 / p50 / p90 / max | 283 / 300 / 316 / 348 s |
| Per-vehicle ping gap p10 / p50 / p90 / p99 | 240 / 300 / 360 / 1,260 s |
| Null `pdist`, `pid`, `tatripid`, `origtatripno` | 0 / 0 / 0 / 0 |
| Trip keys `(rt, pid, tatripid, vid, data_date)` | 16,836; pings per key p10 / p50 / p90 = 4 / 11 / 21 |
| Route 3 / 146 / 151 rows | 4,276 / 2,810 / 3,702 |

Columns: `vid, tmstmp, lat, lon, hdg, pid, rt, des, pdist, dly, tatripid, origtatripno, tablockid,
zone, scrape_file, data_time, data_hour, data_date`.

## Facts confirmed

- `pdist` is feet along the pattern, the same quantity the archive carries (route 3 PID 18414 advances
  about 7,000 ft per 5-minute ping), so `cta.archive.impute_arrivals`-style interpolation against the
  getpatterns stop table applies without a spatial join.
- `tmstmp` has minute resolution (`20260915 05:40`); the poll second is only in `scrape_file`. The
  archive's `vehicle_ts` is finer. Within a 300 s cadence this is a 10% timing uncertainty per ping.
- There is no `sched_start_date` / `sched_start_sec` (Bus Tracker v2 `getvehicles`), so
  `cta.archive.RUN_ID_SQL` cannot key runs here; the natural key is `vid, pid, origtatripno, data_date`
  (upstream uses `CONCAT(rt, pid, tatripid, vid, data_date)`).
- Ping gaps are about 300 s, so `cta.archive.MAX_BRACKET_GAP_S = 180` would drop every pair of this
  source. A 5-minute source needs its own named gap constant in its own spec (Rule 2); the run-level
  view's `bracket_gap_s` column already records the gap for downstream filters.
- The upstream scraper lost 2026-10-16 and 2026-10-17 entirely but has full days for 2026-10-12 to
  2026-10-15, when the archive lost its afternoons to the Bus Tracker daily limit (`known_gaps`); the
  two collectors use different API keys and fail independently.

## Corrections to earlier notes

- ADR-007 and `docs/2026-11-04-mansueto-data-edge.md`: "2026-07-28 to 2026-09-27 is covered by
  neither" is now "2026-07-28 to 2026-08-12 is covered by neither; 2026-08-13 to 2026-09-27 has raw
  5-minute positions from Mansueto, with no imputed arrivals". The parquet data edge itself is
  unchanged.
- `docs/playbook.md` gotcha "Mansueto history stops at 2026-07-28 and never overlaps the archive":
  25 raw-position days (2026-09-28 to 2026-10-27) overlap the archive; the imputed parquets still do not.

## How to re-check

```bash
for d in 2026-08-12 2026-08-13 2026-10-27 2026-10-28 $(date -d yesterday +%F); do
  printf '%s ' "$d"; curl -sS -I -A "cta-bus-analysis/0.1" \
    "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/full_day_data/$d.csv" | grep -E '^HTTP/2|last-modified' | tr '\n' ' '; echo
done
```

If yesterday's file exists the scraper has resumed and the overlap window is growing: the
cross-source items in TODO.md (Phase 3 "cross-source check", the calendar module's coverage hole) can
use it. If 2026-08-13 returns 404 the files were retired and this note is history.
