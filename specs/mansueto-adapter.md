# Spec: Mansueto StopWatch adapter → run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-04  ·  TODO item: Foundation "Mansueto adapter → run-level view (the former Phase 1 ingestion item, now one of two adapters). Spec: `specs/mansueto-adapter.md` (to write)."

## Question

Produce the ADR-003 run-level view (one row per run × stop with an arrival time) from the Mansueto
StopWatch per-pattern parquets, with the same columns, types and identifier conventions as
`cta.views.run_level_from_archive`, so wait-time, travel-time and drift computations run unchanged
on history back to ~2022 (ADR-001) and on dates the archive does not cover (ADR-004). It also makes
the standing cross-source check on overlapping days (ADR-004, ADR-006) possible, which is where
systematic bias between the two sources will be measured.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Per-pattern parquet | `cta.mansueto.parquet_url(pid)`; local copy `data/mansueto/trips_<pid>_full.parquet` | `unique_trip_vehicle_day`, `rt`, `pid`, `stpid`, `stop_sequence`, `bus_stop_time`, `vid`, `p_stp_id`, `seg_combined`, `typ`, `speed_mph` (11 columns, verified route 66 / PID 6662, `scripts/verify_parquet.py`) | no manifest or checksum upstream; `pid` is float-typed (`cta.dlsd_run_quality.build_dlsd_runs` casts float→int→str); not every `rt_to_pid.csv` PID has a file (route 65 PIDs 7906/7907 return 404, `notebooks/eda_routes_8_65_66.ipynb` §6) |
| Route → PID catalog | `cta.mansueto.RT_TO_PID_URL` | `rt`, `pid` | read as strings; route 10 absent (TODO Michigan Next) |
| Pattern stops | `cta.bustracker.pattern_stops_table(pids, cache_dir)` | `pid`, `rtdir`, `seq`, `stpid`, `pdist_ft` | direction and `stop_sequence_index`, same as the archive adapter |
| Calendar | `cta.calendar.calendar_flag(service_date, index=None)` | `holiday:<name>` flags, same as the archive side | pass `index=None`: archive `known_gaps` are Transit Alerts outages, not Mansueto outages, so `known_gap_day` is never set here |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Normalized trips | `cta.mansueto.read_trips(path, *, pid) -> DataFrame` | `run_id` str, `route` str, `pid` str, `vehicle_id` str, `stpid` str, `stop_sequence` int64, `bus_stop_time` tz-aware UTC | one row per parquet row (no drops) |
| Clean trips + QA | `cta.mansueto.clean_trips(trips, pattern_stops) -> (DataFrame, DataFrame)` | first: normalized columns + `seq` int64, `rtdir` str, `service_date` str; second: `stage`, `rows_in`, `rows_out`, `reason`, `count` (`cta.archive.QA_COLUMNS`) | one row per (run, stop); QA one row per (stage, reason) |
| Run-level view | `cta.views.run_level_from_mansueto(pids, *, parquet_dir, pattern_stops=None, pattern_cache_dir=None, start=None, end=None) -> DataFrame` | exactly `cta.views.RUN_LEVEL_COLUMNS`; `bracket_gap_s` NaN; `source='mansueto'` | one row per (run, stop) |
| QA table | `cta.views.mansueto_qa(...)` or returned alongside (implementer's choice, state it) | QA columns + `pid` | one row per (pid, stage, reason) |
| Local copy + download metadata file | `cta.mansueto.fetch_parquet(pid, dest_dir) -> Path` writes `trips_<pid>_full.parquet` and, next to it, `trips_<pid>_full.meta.json` (`url`, `bytes`, `fetched_at` UTC, `max_bus_stop_time`) | — | per pid; the metadata file is what the calendar freshness item will read, since the bucket has no manifest |
| Catalog helper | `cta.mansueto.pids_for_route(route, rt_to_pid) -> list[str]` where `rt_to_pid` is a DataFrame or path | — | moved from `scripts/verify_parquet.py`; the script imports it |

Column mapping (ADR-003 "ingestion will confirm and adapt"): `run_id` = `unique_trip_vehicle_day`
unchanged (ADR-003: preserve Mansueto's trip identifier); `route` = `rt`; `pattern_id` = `pid`;
`stop_id` = `stpid`; `vehicle_id` = `vid`; `arrival_time` = `bus_stop_time`; `direction` =
getpatterns `rtdir`; `stop_sequence_index` = getpatterns `seq` (not Mansueto `stop_sequence`, so
both sources index stops identically); `service_date` = America/Chicago calendar date of the run's
earliest `arrival_time`. `speed_mph`, `seg_combined`, `typ`, `p_stp_id` are not carried (rule 6).

## Method

1. Read with DuckDB `read_parquet` projecting only the seven needed columns and, when `start`/`end`
   are given, pushing the `bus_stop_time` range down (ADR-005: full-history files exceed 1M rows).
   Cast `pid` float→int→str, `stpid`/`vid`/`rt`/`unique_trip_vehicle_day` to str.
2. Timestamps: if `bus_stop_time` is tz-naive it is America/Chicago wall time (Mansueto interpolates
   from Bus Tracker `tmstmp`, which is local; `notebooks/mansueto_imputation_investigation.ipynb` §1).
   Localize with `ambiguous="NaT", nonexistent="NaT"`, convert to UTC, and drop the resulting NaT rows
   with reason `dst_ambiguous_time` (fall-back hour on 2026-11-01 is inside the archive overlap).
   If it is already tz-aware, convert to UTC with zero drops. Stage `read`: also drop null
   `unique_trip_vehicle_day`, `stpid` or `bus_stop_time` (reason `null_key_or_time`).
3. Stage `dedup`: one row per (run_id, stpid), keeping the earliest `bus_stop_time` (what
   `cta.michigan_ave_segment.interpolate_trip_corridor` does with `.first()` after sorting); reason
   `duplicate_stop_visit`.
4. Stage `pattern_join`: inner join to `pattern_stops` on (`pid`, `stpid`) for `rtdir` and `seq`.
   Rows whose stop is not in the current getpatterns pattern are dropped with reason
   `stop_not_in_pattern` (this is how the PID 6402 hand trim takes effect on Mansueto data too).
5. Stage `order`: within a run, sorted by `seq`, a row whose `bus_stop_time` is earlier than the
   running maximum of the preceding rows is dropped with reason `nonmonotone_time` (the "backwards
   `bus_stop_time`" quirk, TODO Michigan Now; 137 trips in the 30-day Michigan sample). See Open
   questions for keep-and-flag instead.
6. `service_date` per run as defined above; `calendar_flag` via `cta.calendar.calendar_flag` with
   `index=None`. No terminal trim, no pattern-length filter, no minimum stops per run (ADR-004).
7. Assemble `RUN_LEVEL_COLUMNS` in the same sort order as the archive view; `bracket_gap_s` is NaN
   because Mansueto does not publish ping times (ping interval ~5 min; downstream code must treat
   NaN as "unknown", not 0).
8. Every stage records one reason per dropped row and asserts `sum(count) == rows_in − rows_out`
   (reuse the `_record_qa` convention from `cta.archive`, factored into a shared helper if cleaner).

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `MAX_MEDIAN_RATIO_DEVIATION` | 0.20 | ADR-006 (applies to "any later same-shape check such as the Mansueto adapter's") | widening hides bias; narrowing re-opens the ADR-006 discussion |
| `MIN_RUNS_FOR_RATIO` | 30 | ADR-006; `tests/test_views_archive.py` | fewer runs make one-day medians noisy |
| `MANSUETO_TZ` | `America/Chicago` | imputation notebook §1; verify on the fixture (Open questions) | wrong tz shifts every arrival by 5–6 h |
| `SOURCE_MANSUETO` | `"mansueto"` | ADR-004 `source` column | — |
| Same-day run-count ratio Mansueto/archive | unknown | measure on the fixture day and record in `docs/`; no gate | — |

## Acceptance tests

Fixture to build (none exists): `tests/fixtures/mansueto_2026-10-29_route3.parquet` = rows of
`trips_18414_full.parquet` and `trips_18415_full.parquet` (route 3 NB/SB, ~110 runs/day each,
getpatterns already under `tests/fixtures/getpatterns/`) whose `bus_stop_time` falls on
2026-10-29 America/Chicago, all 11 columns kept verbatim, plus the two `rt_to_pid.csv` rows in
`tests/fixtures/mansueto_rt_to_pid_route3.csv`. Built by `scripts/build_mansueto_fixtures.py`, which
writes `mansueto_2026-10-29_route3.manifest.json` (source URLs, fetch time, bytes, SHA-256, rows per
pid). Expected: ~13k rows (2 × 110 runs × ~60 stops); the manifest pins the exact count and the tests
read it. Mansueto's ~2-week lag means 2026-10-29 is publishable from ~2026-11-12; the builder refuses
to write a fixture with zero rows for that day.

- [ ] `read_trips` on the fixture returns the manifest row count, `pid` ∈ {"18414","18415"} as str,
      `bus_stop_time` tz-aware UTC, no drops.
- [ ] `run_level_from_mansueto(["18414","18415"], parquet_dir=fixtures, pattern_stops=<fixture>)`
      has columns exactly `RUN_LEVEL_COLUMNS`, `source == "mansueto"`, `bracket_gap_s` all NaN,
      zero (run_id, stop_id) duplicates, `direction` ∈ {Northbound, Southbound}, `service_date ==
      "2026-10-29"` for every row, `calendar_flag == ""`.
- [ ] Analytic case: a hand-built 3-stop trip DataFrame with naive Chicago times on 2026-11-01
      01:30 (ambiguous) and 2026-11-01 03:00 yields one `dst_ambiguous_time` drop and the 03:00 row
      at 09:00 UTC; a second trip with a duplicate stop keeps the earlier time; a third with a
      backwards time at seq 3 loses exactly that row with reason `nonmonotone_time`.
- [ ] QA-table case: on the fixture, for every (pid, stage), reason counts sum to rows_in − rows_out,
      and `rows_out` of each stage equals `rows_in` of the next.
- [ ] Cross-source: with `tests/fixtures/archive_2026-10-29_michigan.ndjson.gz` and the archive view
      for the same two PIDs, per-pattern corridor minutes (`cta.michigan_ave_segment.trip_segment_minutes`,
      entry/exit from `notebooks/michigan_ave_kept_pids.json`) have medians within
      `MAX_MEDIAN_RATIO_DEVIATION` for each PID with ≥ `MIN_RUNS_FOR_RATIO` runs in both; the
      run-count ratio is printed and recorded in `docs/`, not asserted.
- [ ] `pids_for_route("3", fixture_csv) == ["18414", "18415"]` and the string "3" does not match
      "30"; `fetch_parquet` is monkeypatched so no test touches the network.
- [ ] `scripts/verify_parquet.py` and `scripts/cache_dlsd_parquets.py` still import and their tests pass
      after `pids_for_route` / `parquet_url` move into `cta.mansueto`.

## Out of scope

- Changing `cta.dlsd_run_quality` or `cta.michigan_ave_segment` to consume the view (later item).
- Matching individual Mansueto runs to archive runs (vehicle + time alignment); the cross-check
  here is median-level only.
- Stop-level view, wait/travel-time computations, EDA notebook findings.
- Mansueto freshness policy and a `MANSUETO_EXPECTED_LAG_DAYS` constant (calendar item); this spec
  only writes the download metadata file the calendar module will read.
- Any imputation of missing stops, terminal trims, or minimum-stops filters (ADR-004).
- Reading `scripts/transit_archive.py`-style DuckDB caches for Mansueto; files stay plain parquet.

## Open questions

1. Is `bus_stop_time` tz-naive Chicago, naive UTC, or tz-aware in the published parquet? The method
   assumes naive Chicago. The fixture builder must print `df["bus_stop_time"].dtype` and a sample
   next to the archive's first arrival for the same vehicle so the owner can confirm before `ready`.
2. `nonmonotone_time`: drop (as specified) or keep and flag? Keeping needs a flag column the archive
   view does not have, or a second "flags" table. Recommendation: drop; the count is in the QA table.
3. `service_date` from the earliest arrival's Chicago date, or a 03:00 service-day cutoff to match
   `sched_start_date` on the archive side for post-midnight trips? Recommendation: earliest arrival
   now, revisit when the run-matching cross-check exists.
4. Should `stop_sequence_index` really be getpatterns `seq` rather than Mansueto `stop_sequence`
   (ADR-003 says preserve upstream identifiers, but also wants both sources interchangeable)?
