# Spec: Mansueto StopWatch adapter → run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-04  ·  TODO item: Foundation "Mansueto adapter → run-level view (the former Phase 1 ingestion item, now one of two adapters). Spec: `specs/mansueto-adapter.md` (to write)."

## Question

Produce the ADR-003 run-level view (one row per run × stop with an arrival time) from the Mansueto
StopWatch per-pattern parquets, with the same columns, types and identifier conventions as
`cta.views.run_level_from_archive`, so wait-time, travel-time and drift computations run unchanged
on history from ~2022 to the Mansueto data edge (ADR-001, ADR-004). As of 2026-11-04 that edge is
**2026-07-28** and the bucket has not been regenerated since (`docs/2026-11-04-mansueto-data-edge.md`,
ADR-007): there is no day in both sources, so this adapter is validated against the legacy
Mansueto pipeline's own numbers, and the cross-source check is deferred until the edge moves.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Per-pattern parquet | `cta.mansueto.parquet_url(pid)`; local copy `data/mansueto/trips_<pid>_full.parquet` | `seg_combined`, `typ`, `stop_sequence`, `bus_stop_time`, `speed_mph`, `unique_trip_vehicle_day`, `stpid`, `p_stp_id`, `vid`, `rt`, `pid` (11 columns; verified on PIDs 6662 and 18414) | 250–420 MB per busy PID, 9–15M rows, row groups not time-ordered; `bus_stop_time` tz-naive `timestamp[ns]` in America/Chicago wall time; `pid`/`stpid`/`vid`/`rt` strings (legacy code casts `pid` through float, accept both); no manifest or checksum upstream; some `rt_to_pid.csv` PIDs 404 (route 65 PIDs 7906/7907, `notebooks/eda_routes_8_65_66.ipynb` §6) |
| Route → PID catalog | `cta.mansueto.RT_TO_PID_URL` (last modified 2025-01-16) | `rt`, `pid` | read as strings; route 10 absent (TODO Michigan Next) |
| Pattern stops | `cta.bustracker.pattern_stops_table(pids, cache_dir)` | `pid`, `rtdir`, `seq`, `stpid`, `pdist_ft`, plus new `stop_rank` (dense 0-based rank of the stop within its pattern, by `seq` over `typ == 'S'` only) | direction and `stop_sequence_index`, same as the archive adapter |
| Calendar | `cta.calendar.calendar_flag(service_date, index=None)` | `holiday:<name>` flags, same as the archive side | pass `index=None`: archive `known_gaps` are Transit Alerts outages, not Mansueto outages, so `known_gap_day` is never set here |
| Legacy medians | `notebooks/michigan_ave_kept_pids.json` | per pid: `entry_stpid`, `exit_stpid`, `n_trips`, `median_minutes` | computed by `cta.michigan_ave_segment.median_segment_minutes_for_pid` on the 30 days before each file's `max(bus_stop_time)`, i.e. 2026-06-28 to 2026-07-28; the self-consistency target |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Normalized trips | `cta.mansueto.read_trips(path, *, pid, start=None, end=None) -> DataFrame` | `run_id` str, `route` str, `pid` str, `vehicle_id` str, `stpid` str, `stop_sequence` int64, `bus_stop_time` tz-aware UTC | one row per parquet row in range (no other drops) |
| Clean trips + QA | `cta.mansueto.clean_trips(trips, pattern_stops) -> (DataFrame, DataFrame)` | first: normalized columns + `seq` int64, `rtdir` str, `service_date` str; second: `stage`, `rows_in`, `rows_out`, `reason`, `count` (`cta.archive.QA_COLUMNS`) | one row per (run, stop); QA one row per (stage, reason) |
| Run-level view | `cta.views.run_level_from_mansueto(pids, *, parquet_dir, pattern_stops=None, pattern_cache_dir=None, start=None, end=None) -> DataFrame` | exactly `cta.views.RUN_LEVEL_COLUMNS`; `bracket_gap_s` NaN; `source='mansueto'` | one row per (run, stop) |
| QA table | `cta.views.mansueto_qa(...)` or returned alongside (implementer's choice, state it) | QA columns + `pid` | one row per (pid, stage, reason) |
| Data edge probe | `cta.mansueto.data_edge(pid) -> dict` (`url`, `bytes`, `last_modified`, `rows`, `min_bus_stop_time`, `max_bus_stop_time`) via HTTP range requests on the parquet footer (~200 KB, no full download) | — | per pid; the measurement behind `MANSUETO_DATA_EDGE` |
| Local copy + download metadata file | `cta.mansueto.fetch_parquet(pid, dest_dir) -> Path` writes `trips_<pid>_full.parquet` and, next to it, `trips_<pid>_full.meta.json` (the `data_edge` dict plus `fetched_at` UTC) | — | per pid; the metadata file is what the calendar freshness item will read, since the bucket has no manifest |
| Catalog helper | `cta.mansueto.pids_for_route(route, rt_to_pid) -> list[str]` where `rt_to_pid` is a DataFrame or path | — | moved from `scripts/verify_parquet.py`; the script imports it |

Column mapping (ADR-003 "ingestion will confirm and adapt"): `run_id` = `unique_trip_vehicle_day`
unchanged (ADR-003: preserve Mansueto's trip identifier); `route` = `rt`; `pattern_id` = `pid`;
`stop_id` = `stpid`; `vehicle_id` = `vid`; `arrival_time` = `bus_stop_time`; `direction` =
getpatterns `rtdir`; `stop_sequence_index` = getpatterns `stop_rank` (dense, 0 to n−1; not Mansueto
`stop_sequence`, and not the gapped `seq`, which counts waypoints: PID 18414 has 105 stops and a last
`seq` of 319). The archive adapter switches to `stop_rank` in the same change so both sources index
stops identically and the `± 1` neighbour idiom in `cta.dlsd_run_quality` keeps working on either view; `service_date` = the trailing `YYYY-MM-DD` of
`unique_trip_vehicle_day` (Mansueto's own service day, e.g. `318414.038912802023-04-24`), falling
back to the America/Chicago date of the run's earliest `arrival_time` when it does not parse. `speed_mph`, `seg_combined`, `typ`, `p_stp_id` are not carried (rule 6).

## Method

1. Read with DuckDB `read_parquet` projecting only the seven needed columns (ADR-005: files exceed
   1M rows). `start`/`end` filter on `bus_stop_time` after the read; row groups are not time-ordered,
   so no I/O is skipped and the full file is always scanned. Cast `pid` str (through int if numeric),
   `stpid`/`vid`/`rt`/`unique_trip_vehicle_day` to str.
2. Timestamps: `bus_stop_time` is tz-naive America/Chicago wall time (clock-hour profile in the
   data-edge doc; Mansueto interpolates from Bus Tracker `tmstmp`, which is local). Localize with
   `ambiguous="NaT", nonexistent="NaT"`, convert to UTC, and drop the resulting NaT rows with reason
   `dst_ambiguous_time`. If a future file is tz-aware, convert to UTC with zero drops. Stage `read`:
   also drop null `unique_trip_vehicle_day`, `stpid` or `bus_stop_time` (reason `null_key_or_time`).
3. Stage `dedup`: one row per (run_id, stpid), keeping the earliest `bus_stop_time` (what
   `cta.michigan_ave_segment.interpolate_trip_corridor` does with `.first()` after sorting); reason
   `duplicate_stop_visit`. Zero in the probed row group; keep the stage so the count is visible.
4. Stage `pattern_join`: inner join to `pattern_stops` on (`pid`, `stpid`) for `rtdir` and `stop_rank`.
   Rows whose stop is not in the current getpatterns pattern are dropped with reason
   `stop_not_in_pattern` (this is how the PID 6402 hand trim takes effect on Mansueto data too).
5. Stage `order`: within a run, sorted by `seq`, a row whose `bus_stop_time` is earlier than the
   running maximum of the preceding rows is dropped with reason `nonmonotone_time` (the "backwards
   `bus_stop_time`" quirk, TODO Michigan Now; 137 trips in the 30-day Michigan sample). Dropping,
   not flagging, was decided by the owner on 2026-11-04.
6. `service_date` per run as defined above. The fixture builder asserts the embedded date equals the
   Chicago date of the earliest arrival for at least 99% of runs (post-midnight trips are the expected
   exceptions) and prints the rest; `calendar_flag` via `cta.calendar.calendar_flag` with `index=None`. No terminal trim, no pattern-length filter, no minimum stops per run (ADR-004).
7. Assemble `RUN_LEVEL_COLUMNS` in the same sort order as the archive view; `bracket_gap_s` is NaN
   because Mansueto does not publish ping times (ping interval ~5 min; downstream code must treat
   NaN as "unknown", not 0).
8. Every stage records one reason per dropped row and asserts `sum(count) == rows_in − rows_out`
   (reuse the `_record_qa` convention from `cta.archive`, factored into a shared helper if cleaner).
9. `data_edge` reads the footer statistics over HTTP range requests with the project User-Agent and
   the proxy/CA settings of the environment; `fetch_parquet` calls it after download, refuses an empty
   file, and writes the metadata file. Neither verifies a checksum, because none is published.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `MANSUETO_DATA_EDGE` | `"2026-07-28"` | footer probe 2026-11-04, three PIDs (ADR-007, data-edge doc) | re-measure with `data_edge`; a later value reopens ADR-007 and the deferred cross-checks |
| `MANSUETO_TZ` | `America/Chicago` | clock-hour profile of PID 18414's last row group (data-edge doc) | wrong tz shifts every arrival by 5–6 h |
| `MAX_SELF_CONSISTENCY_DEVIATION` | 0.02 | unknown; expected ≈ 0 because target and adapter read the same rows and the only differences are the cleaning stages. Measure on the fixture when building and record the observed ratio in `docs/` | a value near 0.20 would mean the cleaning stages or the join change the corridor timing and must be explained |
| `MIN_RUNS_FOR_RATIO` | 30 | ADR-006; `tests/test_views_archive.py` | fewer runs make medians noisy |
| `MAX_MEDIAN_RATIO_DEVIATION` | 0.20 | ADR-006, for the deferred same-day archive check only | see ADR-006 |
| `SOURCE_MANSUETO` | `"mansueto"` | ADR-004 `source` column | — |

## Acceptance tests

Fixtures to build (none exist), by `scripts/build_mansueto_fixtures.py`, which writes
`tests/fixtures/mansueto.manifest.json` (source URLs, `data_edge` dict per pid, fetch time, bytes,
SHA-256 and rows per fixture file). The builder refuses to write if any `max_bus_stop_time` differs
from `MANSUETO_DATA_EDGE`, because the self-consistency target below assumes that window.

- `tests/fixtures/mansueto_6410_last30d.parquet`: every row of `trips_6410_full.parquet` (151 NB,
  110 runs with both corridor endpoints in the window, 43 stops, recorded median 15.9 min) with
  `bus_stop_time >= max(bus_stop_time) − 30 days`, the exact cutoff of `scripts/cache_dlsd_parquets.py`,
  all 11 columns verbatim. Estimated 5–8k rows, under 300 KB. PID 18414 was rejected for this role:
  ~3,000 runs × 105 stops at 27 bytes/row is ~8.5 MB, and a binary fixture is paid for on every rebuild.
- `tests/fixtures/mansueto_2026-07-27_route3.parquet`: rows of 18414 and 18415 whose
  `bus_stop_time` falls on 2026-07-27 Chicago, the last full day. Estimated 13k rows.
- `tests/fixtures/mansueto_rt_to_pid_route3.csv`: the two route 3 rows of `rt_to_pid.csv`.

All three PIDs already have getpatterns fixtures under `tests/fixtures/getpatterns/`.

- [ ] `read_trips` on the one-day fixture returns the manifest row count, `pid` ∈ {"18414","18415"}
      as str, `bus_stop_time` tz-aware UTC, no drops.
- [ ] `run_level_from_mansueto(["18414","18415"], parquet_dir=fixtures, pattern_stops=<fixture>)`
      has columns exactly `RUN_LEVEL_COLUMNS`, `source == "mansueto"`, `bracket_gap_s` all NaN,
      zero (run_id, stop_id) duplicates, `direction` ∈ {Northbound, Southbound}, `service_date ==
      "2026-07-27"` for every row, `calendar_flag == ""`; a run id with no parseable trailing date
      (hand-built) gets the earliest-arrival date instead.
- [ ] Analytic case: a hand-built 3-stop trip DataFrame with naive Chicago times on 2026-11-01
      01:30 (ambiguous) and 2026-11-01 03:00 yields one `dst_ambiguous_time` drop and the 03:00 row
      at 09:00 UTC; a second trip with a duplicate stop keeps the earlier time; a third with a
      backwards time at seq 3 loses exactly that row with reason `nonmonotone_time`.
- [ ] QA-table case: on the one-day fixture, for every (pid, stage), reason counts sum to
      rows_in − rows_out, and `rows_out` of each stage equals `rows_in` of the next.
- [ ] Self-consistency: on the 30-day fixture, corridor minutes from the view (renamed to the legacy
      columns, as `tests/test_views_archive.py` does) through `cta.michigan_ave_segment.trip_segment_minutes`
      with PID 6410's `entry_stpid`/`exit_stpid` have a median within
      `MAX_SELF_CONSISTENCY_DEVIATION` of its `median_minutes` in `michigan_ave_kept_pids.json`, and
      a run count within 5% of its `n_trips` (unknown; measure, then pin).
- [ ] Data edge: `data_edge` parses a committed 8 KB footer sample (`tests/fixtures/mansueto_18414_footer.bin`,
      the last bytes of the real file, cut by the builder) served by a monkeypatched range reader and
      returns `max_bus_stop_time` on `MANSUETO_DATA_EDGE`; no test touches the network.
- [ ] Deferred (skip with reason while `MANSUETO_DATA_EDGE < "2026-09-28"`): same-day archive
      comparison under `MAX_MEDIAN_RATIO_DEVIATION`, as in the archive spec.
- [ ] `pids_for_route("3", fixture_csv) == ["18414", "18415"]` and the string "3" does not match
      "30"; `fetch_parquet` is monkeypatched so no test touches the network.
- [ ] `scripts/verify_parquet.py` and `scripts/cache_dlsd_parquets.py` still import and their tests pass
      after `pids_for_route` / `parquet_url` move into `cta.mansueto`.
- [ ] Dense index on both adapters: `pattern_stops_table` on the getpatterns fixture gives `stop_rank`
      0 to n−1 with no gaps for every pid; on the one-day fixture, `stop_sequence_index` is strictly
      increasing with `arrival_time` within every run; `run_level_from_archive` on the archive fixture
      day has `max(stop_sequence_index) < 130` for every pattern (it was up to 367 with `seq`), and
      `tests/test_views_archive.py` still passes with the updated expectation.

## Out of scope

- Changing `cta.dlsd_run_quality` or `cta.michigan_ave_segment` to consume the view (later item).
- Any archive adapter change beyond swapping `seq` for `stop_rank` in `stop_sequence_index`.
- Matching individual Mansueto runs to archive runs (vehicle + time alignment); no overlap exists.
- Bridging the 2026-07-28 to 2026-09-27 hole; time series show it (ADR-007).
- Stop-level view, wait/travel-time computations, EDA notebook findings.
- Mansueto freshness policy and alerting (calendar item); this spec only measures the edge and
  writes the download metadata file the calendar module will read.
- Any imputation of missing stops, terminal trims, or minimum-stops filters (ADR-004).
- Reading `scripts/transit_archive.py`-style DuckDB caches for Mansueto; files stay plain parquet.

## Open questions

None. Resolved 2026-11-04 by the owner: `bus_stop_time` is tz-naive America/Chicago;
`nonmonotone_time` rows are dropped; `service_date` is parsed from `unique_trip_vehicle_day` with
the earliest-arrival fallback; `stop_sequence_index` is the dense getpatterns `stop_rank` on both
adapters; the 30-day self-consistency fixture is PID 6410, not 18414.
