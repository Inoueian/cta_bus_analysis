# Spec: Michigan Ave corridor stops and segment speeds from the run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-05 (revised 2026-11-07: owner answers, segment speeds per ADR-010)  ·  TODO item: Foundation "Move `cta.dlsd_run_quality` and `cta.michigan_ave_segment` onto the run-level view (the "later item" of `specs/mansueto-adapter.md`): both read Mansueto parquets directly today (`PARQUET_COLS`, `local_parquet_path`, `median_segment_minutes_for_pid`); make them take a run-level DataFrame so the two Michigan segment-view QA items and the DLSD calendar retro-apply run on either source, with `bracket_gap_s` NaN treated as unknown. Spec: to write." (Michigan half; the DLSD half is `specs/dlsd-runs-from-view.md`)
Tags: `kind:spec source:mansueto source:archive stage:view stage:figure`

## Question

The Michigan Ave before-picture (TODO Michigan Now) needs corridor timing and speed on archive days, but
`build_michigan_segment_view`, `median_segment_minutes_for_pid` and `build_endpoint_coverage_summary` read Mansueto
parquets and the ping-interval `speed_mph` the run-level view omits (rule 6). Build corridor stop timing and
segment speeds (ADR-010) from the ADR-003 view, on any source, so the two open segment-view QA items (157 patterns
14130/14132 absent; `nonmonotone_time` counts per source) become one call. The 157 patterns were absent because their
`rtdir` is Westbound/Eastbound and the legacy builder only knows Northbound/Southbound sequences, though they run
southbound Ohio to Washington (14130) and northbound Randolph to Grand (14132) on Michigan; the owner chose to include them.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Run-level view | `cta.views.run_level_from_archive` / `run_level_from_mansueto` (later `run_level_from_mansueto_raw`) | `cta.views.RUN_LEVEL_COLUMNS` | `bracket_gap_s` NaN on Mansueto means unknown (playbook gotcha); ~300 s raw-source arrivals are excluded from speeds by figure code (ADR-009, ADR-010) |
| Direction sequences | `cta.michigan_ave_segment.direction_stop_sequences()` | `seq_index`, `stpid`, `lat`, `stpnm` | NB 23 stops (22 segments), SB 19 (18) |
| Pattern stops | `cta.bustracker.pattern_stops_table(pids, cache_dir)` | `pid`, `stpid`, `pdist_ft` | hop distance |
| Kept patterns | `load_kept_pid_records()` | `pid`, `route`, `rtdir`, `entry_stpid`, `exit_stpid`, `median_minutes`, `n_trips` | 45 pids; medians are the midsummer window (playbook gotcha) |
| Fixtures | `tests/fixtures/mansueto_6410_last30d.parquet`, `tests/fixtures/archive_2026-10-29_michigan.*`, `tests/fixtures/getpatterns/` | as the two view test files | no new fixture |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Legacy column names | `cta.views.legacy_trip_columns(view)` | `run_id → unique_trip_vehicle_day`, `stop_id → stpid`, `arrival_time → bus_stop_time`, `pattern_id → pid`, `direction → rtdir`, `stop_sequence_index → stop_sequence`; values untouched | as input |
| Corridor minutes | `cta.michigan_ave_segment.segment_minutes_from_view(view, segment_or_record) -> Series` | legacy `trip_segment_minutes` on the renamed view filtered to the pid | one per run with both stops |
| Corridor stops + QA | `corridor_stops_from_view(view, *, sequences=None, kept=None) -> (DataFrame, DataFrame)` | `unique_trip_vehicle_day`, `stpid`, `pid`, `route` str; `rtdir` (chosen sequence); `seq_index` int64; `lat`; `stpnm`; `bus_stop_time` tz-aware UTC; `interpolated` bool, always False, kept so `backwards_time_trip_keys` and `segment_view_report` run unchanged; `source`, `service_date`, `calendar_flag` str; `bracket_gap_s` float64. QA: `cta.views.MANSUETO_QA_COLUMNS`, stage `corridor` | one row per observed (run, pid, stop in the chosen sequence); no gap rows |
| Segment sequences | `direction_segment_sequences(path=None) -> dict[str, DataFrame]` | `seg_index` int64 (= the from stop's `seq_index`), `from_stpid`, `to_stpid`, `lat` (midpoint), `stpnm` (`"<from> to <to>"`) | one row per consecutive stop pair |
| Segment speeds + QA | `corridor_segment_speeds(stops, pattern_stops, *, sequences=None) -> (DataFrame, DataFrame)` | `unique_trip_vehicle_day`, `pid`, `route`, `rtdir`, `seg_index`, `from_stpid`, `to_stpid`, `lat`, `stpnm`, `bus_stop_time` (arrival at the hop's start stop, UTC; legacy name so the hour helpers bucket on it), `speed_mph` float64, `interpolated` bool (hop covers more than one segment), `hop_from_stpid`, `hop_to_stpid`, `source`, `service_date`, `calendar_flag`, `bracket_gap_s` (max of the hop's two stops, NaN if either is NaN), `speed_basis` = `"segment"`. QA stage `hops` | one row per (run, pid, `seg_index`) covered by a valid hop; QA rows are candidate hops |
| Segment stats | `corridor_segment_min_per_mile_stats(sub, segment_sequence, *, min_obs=10)` | as `corridor_stop_min_per_mile_stats`, keyed by `seg_index`, `from_stpid`, `to_stpid` | one row per segment |
| Helper changes | `observed_speed_rows`, `michigan_day_slice_mask`, `filter_dlsd_leak_stops`, `segment_view_report` | signatures unchanged; behaviour in Method steps 6–7 | — |

## Method

Prior art to copy: `cta/michigan_ave_segment.py` `build_michigan_segment_view` and `interpolate_trip_corridor`
(span logic, now on segments), `corridor_stop_min_per_mile_stats`; `cta/views.py` `mansueto_view_from_trips` (per-pid
loop, QA with `pid` in front; playbook pattern "Emit a QA table from a pipeline stage");
`tests/test_views_mansueto.py` `test_self_consistency_6410_against_legacy_median` (the rename idiom).

1. `legacy_trip_columns` is a rename; `segment_minutes_from_view` filters `pattern_id`, renames, calls
   `trip_segment_minutes`. `tests/test_views_archive.py` and `tests/test_views_mansueto.py` switch to it (no assertion changes).
2. `corridor_stops_from_view`: `kept` defaults to `load_kept_pid_records()`, pids cast to str (playbook gotcha
   "Identifiers arrive as `6410.0`"). View rows of other patterns are dropped as `pattern_not_kept`. The sequence is
   the pattern's `direction` when Northbound or Southbound (all 43 such kept pids); otherwise the sequence holding more
   of its distinct corridor stops (14130 → Southbound, 14132 → Northbound); none → `no_direction_sequence`. Rows at
   stops outside the chosen sequence → `stop_not_in_sequence`. One reason per row; QA additive.
3. Hops: within a run, consecutive observed stops in `seq_index` order. A hop is valid when both `pdist_ft` are known,
   the distance is > 0 and the time is > 0; otherwise one reason, in priority `missing_pdist`, `nonpositive_hop_distance`,
   `nonpositive_hop_time`. QA stage `hops`: `rows_in` = observed stops − runs, `rows_out` = valid hops. A run with one
   observed stop has no hop.
4. A valid hop from `seq_index` i to j covers segments i to j − 1; each gets the hop's speed, `interpolated = j − i > 1`
   (the analogue of legacy gap rows; `observed_speed_rows` keeps excluding them), and `bus_stop_time` = arrival at i.
   No row has a NaN speed.
5. `source`, `service_date`, `calendar_flag` from the hop's start row. Output sorted by (`pid`, run, `seg_index`).
6. `observed_speed_rows` and `michigan_day_slice_mask` convert a tz-aware `bus_stop_time` to America/Chicago before
   `hour` / `dayofweek`; naive frames, the legacy ones, are used as they are (playbook gotcha on naive Chicago time).
7. `filter_dlsd_leak_stops` on a frame with `from_stpid`/`to_stpid` drops segments touching a leak stop of their
   direction (ADR-010; same constants, so no exclusion changes; on stop frames it behaves as today).
   `segment_view_report` skips its null-speed checks when the frame has no `speed_mph`.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `SPEED_BASIS_SEGMENT` | `"segment"` | ADR-010; 6410: ping median 5.23 vs hop median 4.28 mph | — |
| `NORTHBOUND_/SOUTHBOUND_DLSD_LEAK_STPIDS` | existing | carried to segments touching them (ADR-010) | drops 220 of 1,210 6410 segment rows |

No new threshold. No `bracket_gap_s` bound: the raw adapter's spec and the figure code decide (ADR-009).

## Acceptance tests

Numbers measured 2026-11-07 on the committed fixtures with a prototype of steps 2–4 unless marked.

- [ ] `test_legacy_trip_columns_roundtrip`: on the route 3 one-day Mansueto view, the six columns are renamed, all
      others kept with dtypes, and `segment_minutes_from_view(view, rec_18414)` equals `trip_segment_minutes` on the
      renamed view for 1580 → 1126 exactly; the 6410 self-consistency test passes through the helper.
- [ ] `test_corridor_stops_hand_built_qa`: a hand-built view with a kept NB pid, a kept Westbound pid whose stops lie
      only in the SB sequence (→ Southbound), a non-kept pid, a kept pid with no corridor stop, and one row at a stop
      outside the chosen sequence; reasons `pattern_not_kept`, `no_direction_sequence`, `stop_not_in_sequence` sum to
      `rows_in − rows_out`; a kept record with an integer `pid` matches the string `pattern_id`.
- [ ] `test_corridor_stops_6410_matches_legacy`: on `tests/fixtures/mansueto_6410_last30d.parquet`, 990 rows, 110 runs,
      `rtdir == "Northbound"`, `source == "mansueto"`; the set of (`unique_trip_vehicle_day`, `stpid`, `bus_stop_time`
      in America/Chicago) equals the non-interpolated rows of legacy `build_michigan_segment_view` on the same file
      (monkeypatch `local_parquet_path`); `backwards_time_trip_keys` is empty.
- [ ] `test_corridor_stops_archive_fixture_day`: 15,216 rows, 1,500 runs, 44 pids; 14130 Southbound with 352 rows,
      14132 Northbound with 290; 4 runs with one observed stop; `calendar_flag == ""`; `segment_view_report` with an
      explicit `cache_status` (no `data/` read) gives `pids_missing_from_view == ["1054"]` and no null-speed issue.
- [ ] `test_corridor_segment_speeds_hand_built`: 4-stop sequence, `pdist_ft` 0, 1000, 2000, 3000. Run A at stops 0, 2,
      3 at 13:00, 13:10, 13:12 UTC gives 3 rows: segments 0 and 1 at `2000/5280/(10/60)` mph, `interpolated`, start
      13:00; segment 2 at `1000/5280/(2/60)` mph, not interpolated, start 13:10. Run B at stops 1, 2 with equal times
      gives `nonpositive_hop_time`; run C on a pid whose `pdist_ft` falls from stop 1 to 2 gives `nonpositive_hop_distance`.
      QA `hops`: `rows_in` 4, `rows_out` 2, reasons sum; no NaN `speed_mph`; `speed_basis == "segment"`.
- [ ] `test_corridor_segment_speeds_6410`: 880 candidate and 880 valid hops; 1,210 rows, 110 runs × the 11 segments
      from 1119 to 1128; 550 interpolated, the segments around stops 18791, 1104 and 1126 that 151 NB does not serve;
      median over distinct hops 4.28 ± 0.05 mph; `filter_dlsd_leak_stops` drops 220 rows.
- [ ] `test_corridor_segment_speeds_archive_fixture_day`: 13,716 candidate and 13,714 valid hops;
      `nonpositive_hop_distance == 2`, both on pid 25899, where two stops' latitude order disagrees with travel order;
      15,921 rows, 3,718 interpolated; `filter_dlsd_leak_stops` drops 1,319; max `speed_mph` 35.0 ± 0.1; rows for
      14130 and 14132 present; `bracket_gap_s <= cta.archive.MAX_BRACKET_GAP_S` everywhere.
- [ ] `test_segment_helpers_on_view_outputs`: `observed_speed_rows` on the 6410 segments keeps the 660 non-interpolated
      rows with `hour` in America/Chicago, which differs from the UTC hour on every row; `michigan_day_slice_mask`
      agrees; `corridor_segment_min_per_mile_stats` against the NB segment sequence returns 22 rows with medians on
      exactly the 6 directly observed segments and `lat` the stop midpoint; `slowest_hours` runs; the existing naive
      tests in `tests/test_michigan_ave_segment.py` pass unchanged.

## Out of scope

- Deleting the legacy builders, `PARQUET_COLS` or `local_parquet_path` (notebooks call them; deprecate, remove later).
- Re-pointing `notebooks/michigan_ave_speed_plots.ipynb` to segments, regenerating `data/michigan_ave/`, any figure;
  a script entry point; renaming the outputs to ADR-003 column names.
- Measuring whether the leak exclusion is still needed for segment speeds (the before-picture note does that).
- Pooling short segments; any `bracket_gap_s` bound; cross-source speed comparison (ADR-009 item).

## Open questions

None. Resolved by the owner 2026-11-07: speed is defined on segments between consecutive corridor stops (ADR-010);
the two route 157 patterns are included, directed by stop membership.
