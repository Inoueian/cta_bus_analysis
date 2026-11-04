# Mansueto adapter: QA and self-consistency on the committed fixtures (2026-11-04)

Durable findings from implementing `specs/mansueto-adapter.md` (`cta.mansueto`, `cta.views.run_level_from_mansueto`).
Fixtures are cut from the public CloudFront files by `scripts/build_mansueto_fixtures.py`; the manifest
`tests/fixtures/mansueto.manifest.json` records source bytes, footer `data_edge`, SHA-256 and rows per file.

## Self-consistency (acceptance gate, ADR-007)

PID 6410 (151 NB), every row in the 30 days before the file's own `max(bus_stop_time)`, the window
`scripts/cache_dlsd_parquets.py` used for `notebooks/michigan_ave_kept_pids.json`:

| Quantity | Adapter view | Legacy (`michigan_ave_kept_pids.json`) |
|---|---|---|
| Runs with both corridor endpoints (1119 → 1128) | 110 | 110 |
| Median corridor minutes | 15.9110 | 15.9110 |
| Ratio | 1.0000 | tolerance `MAX_SELF_CONSISTENCY_DEVIATION = 0.02` |

Nothing was dropped at any stage on this file, so the adapter and the legacy pipeline see the same
rows and the ratio is exactly 1. The 2% tolerance is therefore untested by this fixture; a ratio away
from 1 on another pattern would come from `stop_not_in_pattern` or `nonmonotone_time` drops and must
be explained before the tolerance is touched.

## QA tables

PID 6410, 30-day window (4,730 rows): rows in = rows out at every stage.

Route 3, 2026-07-27 (the last full day; 23,888 rows, 230 runs):

| pid | stage | rows_in | rows_out | reason | count |
|---|---|---|---|---|---|
| 18414 | read | 11,445 | 11,445 | | 0 |
| 18414 | dedup | 11,445 | 11,445 | | 0 |
| 18414 | pattern_join | 11,445 | 11,337 | stop_not_in_pattern | 108 |
| 18414 | order | 11,337 | 11,337 | | 0 |
| 18415 | read | 12,443 | 12,443 | | 0 |
| 18415 | dedup | 12,443 | 12,443 | | 0 |
| 18415 | pattern_join | 12,443 | 12,330 | stop_not_in_pattern | 113 |
| 18415 | order | 12,330 | 12,330 | | 0 |

- `stop_not_in_pattern` is about 1% of route 3 rows: stops Mansueto imputed in July 2026 that the
  getpatterns fixture (fetched 2026-11-03) no longer lists. Patterns drift; a view over years of
  history should expect this reason to grow with the age of the data.
- No duplicate (run, stop) visits and no backwards times on either fixture. The 137 backwards-time
  trips of the Michigan segment-view QA were over 30 days and 45 patterns, so one day of one route is
  too small to see them; the stage stays, with its count visible.
- One-day corridor medians (18.14 min NB, 21.05 min SB) sit at 0.93 and 0.98 of the 30-day legacy
  medians. Not an acceptance check (ADR-006 is for cross-source comparisons), recorded for scale.

## Data facts that corrected the spec

- **A pattern's last row can precede the bucket edge.** `MANSUETO_DATA_EDGE` (2026-07-28) is the
  generation date of every file (`Last-Modified` 2026-07-28 10:11–10:19 UTC). PID 6410's last row is
  2026-07-27 18:19 because 151 NB ends service before midnight; 18414/18415 run to 00:05 and 02:04.
  The fixture builder checks `Last-Modified` on the edge date and the last row within one day of it,
  not equality.
- **Service date and day cuts.** 5 of the 230 runs on 2026-07-27 embed 2026-07-26 in
  `unique_trip_vehicle_day`: trips that started before midnight and whose first stops after 00:00
  fall in the cut. The adapter keeps Mansueto's own service day for them (rows carry
  `service_date = 2026-07-26`), which is the behaviour the spec's service-date rule asks for; the
  spec's "every row on 2026-07-27" acceptance was wrong for a row-by-date cut. The 99% check in the
  builder counts these post-midnight continuations as the expected exceptions (0 unexplained).
- **Footer size.** The parquet footer of PID 18414 is 131,444 bytes (121 row groups × 11 columns),
  not 8 KB; the committed sample is the whole footer plus trailer (131,452 bytes). `data_edge` reads
  it in two range requests (8-byte trailer, then the footer) and never touches the row groups.
- **Route 3 catalog.** `rt_to_pid.csv` lists nine route 3 PIDs (18416, 18412, 18414, 18415, 18417,
  1054, 7770, 18413, 19388), not two.
- **Fixture sizes.** 30-day PID 6410: 4,730 rows, 62 KB (spec estimate 5–8k rows). One day of route 3:
  23,888 rows, 263 KB (spec estimate 13k). `null bus_stop_time` and null keys: 0 in all three source files.

## Dense stop index

`stop_sequence_index` is now the getpatterns `stop_rank` (0 to n−1 over stop points) on both adapters
(ADR-008). On the archive fixture day the maximum per pattern dropped from 367 (`seq`, which counts
waypoints) to under 130; route 3's patterns have 105 and 107 stops (max index 104 and 106).
