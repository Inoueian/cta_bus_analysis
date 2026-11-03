# Spec: Transit Alerts archive adapter → run-level view

Status: ready
Owner: Satoru  ·  Date: 2026-11-03  ·  TODO item: Phase 1 "Data ingestion … build the run-level view" (second source)

## Question

Produce the ADR-003 run-level view (one row per run × stop with an arrival time) from the Transit
Alerts position archive, so every downstream computation (wait, travel time, drift, corridor speed)
works unchanged on ~60 s positions from 2026-09-28 onward. Validated against the Mansueto-derived
view on overlapping days.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Archive index | `https://data.chicagotransitalerts.app/positions/index.json` | `days[].files.bus.{path,rows,bytes,sha256}`, `known_gaps[]` | fetch with curl; pin a copy per run |
| Daily bus file | `positions/bus/YYYY/MM/YYYY-MM-DD.ndjson.gz` | ts, route, pid, vehicle_id, lat, lon, pdist (ft), heading, vehicle_ts, sched_start_sec, sched_start_date, destination | epoch ms; `sched_start_date` is `YYYY-MM-DD` in practice despite index saying `YYYYMMDD` |
| Pattern stops | Bus Tracker `getpatterns` (disk cache `data/cta_api_cache/getpatterns_<pid>.json`) | seq, stpid, stpnm, lat, lon, pdist, rtdir | one call per pid, cached forever; new pids appear (route 47 on Oct 17, route 49 on Oct 19) |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Clean fixes | `cta.archive.clean_fixes(day) -> DataFrame` | route, pid, vehicle_id, run_id, vehicle_ts, pdist, lat, lon | one row per (run, vehicle_ts) |
| Run-level view | `cta.views.run_level_from_archive(days, pids) -> DataFrame` | run_id, route, direction, pattern_id, stop_id, stop_sequence_index, arrival_time, bracket_gap_s, source='archive' | one row per (run, stop) |
| QA table | `cta.archive.qa(day) -> DataFrame` | stage, rows_in, rows_out, reason, count | per day |
| Local cache | `data/archive/positions.duckdb` tables `positions_raw`, `archive_ingest` | as `scripts/transit_archive.py` (MIT, MisterClean) | restartable, checksum-verified |

`run_id` = `f"{vehicle_id}-{pid}-{sched_start_date}-{sched_start_sec}"` (scorecard trip key [T0];
profiling showed all four parts are needed). `direction` comes from `getpatterns.rtdir`, not from
`destination`.

## Method

1. Ingest: port `scripts/transit_archive.py` (keep attribution). Verify bytes and SHA-256 against the
   pinned index; refuse to ingest a day whose checksum changed.
2. Clean fixes (scorecard.sql steps 1–2): dedup on (run_id, vehicle_ts) keeping min(pdist); drop
   rows with null pid/pdist/vehicle_ts.
3. Pair filters before imputation (scorecard [T3]–[T6]): drop pairs with Δvehicle_ts > 180 s,
   Δpdist < 0, Δpdist > 2 × straight-line + 1500 ft, or implied speed > 80 mph. Do **not** apply the
   terminal trim or pattern-length filter: stop-level views need every revenue pattern and the
   first/last stops.
4. Impute: for each kept pair (p0,t0)→(p1,t1) and each pattern stop with p0 ≤ stop_pdist < p1,
   `arrival_time = t0 + (t1−t0)·(stop_pdist−p0)/(p1−p0)`. Keep the earliest crossing per (run, stop).
   Record `bracket_gap_s = t1 − t0`.
5. Stops a run never crosses (partial trips, outages) are absent, not NaT. Downstream travel-time
   code already requires both stops present.
6. Service date for a run is `sched_start_date` (post-midnight trips), not the archive file date.
7. Apply `cta.calendar` exclusions (known_gaps windows, holidays) as a flag column, not a drop.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| MAX_BRACKET_GAP_S | 180 | scorecard profiling §4: gaps >180 s hide stand-stills; 0.34% of pairs | ±1% speed; for arrival times, a longer gap only widens uncertainty |
| MAX_IMPLIED_MPH | 80 | scorecard [T6]; 50 mph cap deletes real LSD driving on 146 | n/a |
| GEOMETRY_SLACK_FT | 1500 | scorecard [T5] | n/a |
| STOP_PDIST_SOURCE | getpatterns | fix-cloud projection prototype had 100 ft p50 spread and failed on low-volume pids | — |

## Acceptance tests

- [ ] Fixture `tests/fixtures/archive_2026-10-29_michigan.ndjson.gz` (only rows for the 45 kept
      Michigan pids, ~118k rows, committed) ingests with the recorded SHA-256 and row count.
- [ ] `clean_fixes` on the fixture returns 118,014 rows and 1,582 runs (prototype numbers; re-pin after porting).
- [ ] On the fixture, with the cached getpatterns for the kept pids, `run_level_from_archive` yields
      ≥ 16,000 (run, stop) rows and zero (run, stop) duplicates.
- [ ] Per-pid corridor minutes (entry→exit, from `cta.michigan.trip_segment_minutes`) have median
      within 10% of the Mansueto median in `notebooks/michigan_ave_kept_pids.json` for every pid
      with ≥ 30 runs on the fixture day (prototype: ratio p50 0.993).
- [ ] A synthetic 3-fix trip with a known stop pdist yields the analytically correct arrival time.
- [ ] A pair spanning a `known_gaps` window is dropped and counted in the QA table.
- [ ] QA table reason counts sum to rows_in − rows_out at every stage.
- [ ] No network access in tests (monkeypatch `curl` call).

## Out of scope

- Mansueto adapter changes (separate spec).
- Wait-time / travel-time computations (they consume the view).
- 30 s polling specifics after 2026-11-01 (the method is poll-rate agnostic; note it in docs).
- Web app, scheduled refresh.

## Open questions

- Where do getpatterns caches for new pids come from in CI? Proposal: commit the JSON for the
  kept pids under `tests/fixtures/getpatterns/` (small, stable).
