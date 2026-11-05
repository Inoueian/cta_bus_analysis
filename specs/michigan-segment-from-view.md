# Spec: Michigan Ave segment view from the run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-05  ·  TODO item: Foundation "Move `cta.dlsd_run_quality` and `cta.michigan_ave_segment` onto the run-level view (the "later item" of `specs/mansueto-adapter.md`): both read Mansueto parquets directly today (`PARQUET_COLS`, `local_parquet_path`, `median_segment_minutes_for_pid`); make them take a run-level DataFrame so the two Michigan segment-view QA items and the DLSD calendar retro-apply run on either source, with `bracket_gap_s` NaN treated as unknown. Spec: to write." (Michigan half; the DLSD half is `specs/dlsd-runs-from-view.md`)

## Question

The Michigan Ave before-picture (TODO Michigan Now) needs corridor timing and per-stop speed on archive days, but
`build_michigan_segment_view`, `median_segment_minutes_for_pid` and `build_endpoint_coverage_summary` read Mansueto
parquets and the ping-interval `speed_mph` column that the run-level view deliberately omits (rule 6). Build the
segment view from the ADR-003 view with a stop-to-stop speed, on either source, so the two open segment-view QA
items (157 patterns 14130/14132 absent; `nonmonotone_time` counts per source) become one function call. On the
archive fixture day the 157 patterns are absent for a reason this spec fixes: their `rtdir` is Westbound/Eastbound
and the builder only knows Northbound/Southbound latitude sequences, although every one of their corridor stops lies
in one of those sequences (14130 → Southbound, 14132 → Northbound).

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Run-level view | `cta.views.run_level_from_archive` / `run_level_from_mansueto` | `cta.views.RUN_LEVEL_COLUMNS` | either source |
| Direction sequences | `cta.michigan_ave_segment.direction_stop_sequences()` | per direction: `seq_index`, `stpid`, `lat`, `stpnm` | NB 23 stops, SB 19, from `notebooks/michigan_ave_stops_snapshot.json` |
| Pattern stops | `cta.bustracker.pattern_stops_table(pids, cache_dir)` | `pid`, `stpid`, `pdist_ft`, `stop_rank` | `pdist_ft` is the hop length for speed |
| Kept patterns | `load_kept_pid_records()` | `pid`, `route`, `rtdir`, `entry_stpid`, `exit_stpid`, `median_minutes`, `n_trips` | 45 pids |
| Fixtures | `tests/fixtures/mansueto_6410_last30d.parquet`, `tests/fixtures/archive_2026-10-29_michigan.*`, `tests/fixtures/getpatterns/` | as `tests/test_views_mansueto.py` / `tests/test_views_archive.py` | legacy `build_michigan_segment_view` on the 6410 cut gives 1,320 rows, 110 trips, 330 interpolated (the 3 NB-sequence stops 18791, 1104, 1126 that 151 NB does not serve) |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Legacy column names | `cta.views.legacy_trip_columns(view) -> DataFrame` | the view with `run_id → unique_trip_vehicle_day`, `stop_id → stpid`, `arrival_time → bus_stop_time`, `pattern_id → pid`, `direction → rtdir`, `stop_sequence_index → stop_sequence`; values untouched (UTC stays UTC) | same as input |
| Corridor minutes | `cta.michigan_ave_segment.segment_minutes_from_view(view, segment_or_record) -> Series` | per run minutes entry→exit (legacy `trip_segment_minutes` on the renamed view filtered to the pid) | one value per run with both stops |
| Segment view + QA | `cta.michigan_ave_segment.segment_view_from_view(view, *, pattern_stops, sequences=None, kept=None) -> (DataFrame, DataFrame)` | legacy segment-view columns `unique_trip_vehicle_day`, `stpid`, `pid`, `route`, `rtdir`, `seq_index` int64, `lat`, `stpnm`, `bus_stop_time` (tz-aware UTC, NaT on gap rows), `speed_mph` float64, `interpolated` bool, plus `source`, `service_date`, `calendar_flag`, `speed_basis` str = `"stop_to_stop"`; QA as `cta.views.MANSUETO_QA_COLUMNS` | one row per (run, pid, `seq_index`) over the run's observed span in its direction sequence; QA rows are view rows, one stage `corridor` |

`rtdir` in the output is the chosen direction sequence (Northbound/Southbound), not the pattern's `direction`, so
`filter_dlsd_leak_stops` and the latitude charts work for 157. The legacy column names are kept on purpose: the
speed-plot helpers, `backwards_time_trip_keys`, `segment_view_report` and `data/michigan_ave/segment_view.parquet`
consumers read them. Renaming the segment-view schema to ADR-003 names is a separate item.

## Method

Prior art to copy: `cta/michigan_ave_segment.py` `build_michigan_segment_view` and `interpolate_trip_corridor` (span
and gap-row construction); `cta/views.py` `mansueto_view_from_trips` (per-pid loop, QA with `pid` in front);
`tests/test_views_mansueto.py` `test_self_consistency_6410_against_legacy_median` (the rename-then-legacy-helper idiom
this spec turns into `legacy_trip_columns`); `tests/test_michigan_ave_segment.py` `test_interpolate_trip_corridor_skipped_middle_stop`.

1. `legacy_trip_columns` is a rename; `trip_segment_minutes`, `endpoint_coverage`, `mode_last_corridor_stop_on_trip`
   then run on the view unchanged. `segment_minutes_from_view` filters `pattern_id`, renames, calls `trip_segment_minutes`.
   `tests/test_views_archive.py` and `tests/test_views_mansueto.py` switch to the helper (no assertion changes).
2. `segment_view_from_view`: `kept` defaults to `load_kept_pid_records()`; view rows whose `pattern_id` is not kept are
   dropped with reason `pattern_not_kept`. Per kept pid, the direction sequence is the one containing more of the
   pattern's distinct corridor `stop_id`s; a tie is broken by the pattern's `direction` when it names a sequence,
   otherwise (and when neither sequence contains any stop) the pid's rows are dropped with reason
   `no_direction_sequence`. Rows at stops outside the chosen sequence are dropped with reason `stop_not_in_sequence`.
3. Per run: observed rows are the remaining view rows mapped to `seq_index`; the span is `[min, max]` of observed
   `seq_index`; every sequence stop inside the span without a row is a gap row (`interpolated=True`,
   `bus_stop_time` NaT). Same shape as `interpolate_trip_corridor`; duplicates per (run, stpid) cannot occur (adapters dedup).
4. `speed_mph` on an observed row is the hop into it: (`pdist_ft[stop] − pdist_ft[previous observed stop of the run]`)
   ÷ 5280 ÷ (arrival delta in hours), NaN on the first observed row; a gap row carries the speed of the hop that
   spans it (the same value as the next observed row). A hop with arrival delta ≤ 0 or missing `pdist_ft` gives NaN
   and is counted in a `hops` summary (`nonpositive_hop_time`, `missing_pdist`) returned on the QA table as rows
   with `rows_in == rows_out` and the count (flags, not drops; stage `hops`). `speed_basis = "stop_to_stop"` on
   every row so the ping-interval view (`build_michigan_segment_view`, implicit `"ping_interval"`) is never mixed in.
5. `source`, `service_date`, `calendar_flag` copied from the run's first observed row. Output sorted as legacy
   (`pid`, `unique_trip_vehicle_day`, `seq_index`).
6. QA stage `corridor`: `rows_in` = view rows, `rows_out` = observed rows in the output; `sum(count) == rows_in − rows_out`.
   Gap rows are additions, not in the drop count; the report counts them via `interpolated`.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `SPEED_BASIS_STOP_TO_STOP` | `"stop_to_stop"` | rule 6: 6410 observed rows give median ping `speed_mph` 5.23 vs stop-to-stop 4.28 mph; they are different quantities | — |
| `DEFAULT_MIN_MEDIAN_MINUTES`, `NORTHBOUND_/SOUTHBOUND_DLSD_LEAK_STPIDS`, `TRIM_6402_STPIDS` | existing | not touched | — |

No new threshold; no exclusion beyond the three QA reasons above.

## Acceptance tests

Numbers measured 2026-11-05 on the fixtures unless marked.

- [ ] `test_legacy_trip_columns_roundtrip`: on the route 3 one-day Mansueto view, `legacy_trip_columns` renames the six
      columns, keeps every other column and dtype, and `trip_segment_minutes(legacy, "1580", "1126")` for pid 18414
      equals `segment_minutes_from_view(view, rec_18414)` exactly; the 6410 self-consistency test still passes through it.
- [ ] `test_segment_view_from_view_hand_built`: hand-built view, one kept pid on a 4-stop sequence
      (`pdist_ft` 0, 1000, 2000, 3000) with run A at stops 0, 2, 3 at 13:00, 13:10, 13:15 UTC → 4 output rows, stop 1 is a
      gap row with `speed_mph == 2000/5280/(10/60)` (≈ 2.27) equal to stop 2's, stop 3 has `1000/5280/(5/60)` (≈ 2.27),
      stop 0 NaN; run B at stops 1, 2 with equal arrivals → `nonpositive_hop_time == 1`, NaN speed; `speed_basis` is
      `"stop_to_stop"` everywhere and `bus_stop_time` is tz-aware UTC on observed rows, NaT on the gap row.
- [ ] `test_segment_view_from_view_qa_sums`: on the hand-built view with one extra non-kept pid and one kept pid with
      stops in neither sequence, stage `corridor` reasons are `pattern_not_kept`, `no_direction_sequence`,
      `stop_not_in_sequence`, and they sum to `rows_in − rows_out`; `rows_out` equals the count of `~interpolated` rows.
- [ ] `test_segment_view_6410_matches_legacy`: on the 6410 Mansueto view (`tests/fixtures/mansueto_6410_last30d.parquet`,
      getpatterns fixture), the output has 1,320 rows, 110 runs, 330 interpolated rows at exactly stops
      {18791, 1104, 1126}, `rtdir == "Northbound"`, `source == "mansueto"`, and the set of observed
      (`unique_trip_vehicle_day`, `stpid`, `bus_stop_time` in America/Chicago) equals the legacy
      `build_michigan_segment_view` output on the same file (monkeypatch `local_parquet_path` as the measurement did);
      `backwards_time_trip_keys` is empty; stop-to-stop `speed_mph` median on observed rows is 4.28 ± 0.05.
- [ ] `test_segment_view_archive_fixture_day`: on the fixture-day archive view with all 45 kept pids, 14130 appears
      with `rtdir == "Southbound"` and 14132 with `"Northbound"` (352 and 290 observed rows); the output has 15,216
      observed rows over 1,500 runs and 44 pids, ~2,213 gap rows (estimate; measure, then pin), `nonpositive_hop_time`
      ~2 (estimate; measure, then pin), `backwards_time_trip_keys` empty, `calendar_flag == ""`, and `segment_view_report`
      runs on it with `pids_missing_from_view == ["1054"]` (did not run that day).
- [ ] `test_segment_view_speed_helpers_run`: `observed_speed_rows`, `filter_dlsd_leak_stops`, `hour_stop_speed_stats`
      and `corridor_stop_min_per_mile_stats` accept the fixture-day output without error and `observed_speed_rows`
      returns exactly the `~interpolated` rows with `hour` in America/Chicago (differs from the UTC hour on every row).

## Out of scope

- Deleting `build_michigan_segment_view`, `median_segment_minutes_for_pid`, `build_pid_timing_summary`,
  `build_endpoint_coverage_summary`, `PARQUET_COLS`, `local_parquet_path`: the notebooks still call them and
  `/implement` does not edit notebooks. Deprecate in docstrings; remove in a follow-up.
- Regenerating `data/michigan_ave/segment_view.parquet`, any figure, or the speed-plot notebook; a script entry point
  (the two QA follow-ups and the before-picture item call the function from a notebook or their own thin script).
- Changing the plotting helpers' column names or signatures; renaming the segment-view schema to ADR-003 names.
- Any new gap-fill beyond the legacy span rule (no extrapolation outside the observed span, no time interpolation).
- Touching `michigan_ave_kept_pids.json` (the catalog refresh item) or the pattern-direction labels in getpatterns.
- Cross-source comparison of speeds (ADR-007 defers it; ADR-006 covers medians only).

## Open questions

1. Stop-to-stop speed is a new published quantity for the corridor charts (today they show ping-interval speed).
   Recommended: accept it, record it as an ADR ("corridor speed is stop-to-stop from arrival deltas and getpatterns
   pdist; ping-interval `speed_mph` is not plotted"), and relabel the figures when the before-picture notebook is built.
   If the owner prefers a different column name than `speed_mph` for the new quantity, the plotting helpers need a
   `speed_col` argument (out of scope here) and the acceptance items rename accordingly.
2. The direction rule brings 157's two patterns in. Is that wanted for the corridor charts (they add Michigan stops
   between Randolph and Hubbard only), or should 157 stay a Mansueto-era caveat and be dropped from the kept list?
   The rule is recommended; the QA item closes either way with the counts this spec measures.
3. Should the 6410 equality test compare `speed_mph` to the legacy flanking-mean values? Recommended no: different
   quantity (rule 6); the shape equality plus the pinned stop-to-stop median is the gate.
