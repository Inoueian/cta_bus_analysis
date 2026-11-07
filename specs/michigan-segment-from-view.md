# Spec: Michigan Ave corridor stops and segment speeds from the run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-05 (revised 2026-11-07: owner answers, segment speeds per ADR-010, multi-segment hops included, detour hops dropped)  ·  TODO item: Foundation "Move `cta.dlsd_run_quality` and `cta.michigan_ave_segment` onto the run-level view (the "later item" of `specs/mansueto-adapter.md`): both read Mansueto parquets directly today (`PARQUET_COLS`, `local_parquet_path`, `median_segment_minutes_for_pid`); make them take a run-level DataFrame so the two Michigan segment-view QA items and the DLSD calendar retro-apply run on either source, with `bracket_gap_s` NaN treated as unknown. Spec: to write." (Michigan half; the DLSD half is `specs/dlsd-runs-from-view.md`)
Tags: `kind:spec source:mansueto source:archive stage:view stage:figure`

## Question

The Michigan Ave before-picture needs corridor timing and speed on archive days; the legacy builders read Mansueto
parquets and their ping-interval `speed_mph` (rule 6). Build stop timing and segment speeds (ADR-010) from the ADR-003
view, on any source, so both open segment-view QA items become one call. Route 157's patterns 14130/14132, labelled
Westbound/Eastbound, run south Ohio to Washington and north Randolph to Grand on Michigan; the legacy builder knew only NB/SB.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Run-level view | `cta.views.run_level_from_archive` / `run_level_from_mansueto` (later `run_level_from_mansueto_raw`) | `cta.views.RUN_LEVEL_COLUMNS` | `bracket_gap_s` NaN on Mansueto means unknown (playbook gotcha); ~300 s raw-source arrivals are excluded from speeds by figure code (ADR-009, ADR-010) |
| Direction sequences | `cta.michigan_ave_segment.direction_stop_sequences()` | `seq_index`, `stpid`, `lat`, `stpnm`, plus `lon` (additive, from the same snapshot) | NB 23 stops (22 segments), SB 19 (18); `lat`/`lon` give the straight-line hop distance |
| Pattern stops | `cta.bustracker.pattern_stops_table(pids, cache_dir)` | `pid`, `stpid`, `pdist_ft` | hop distance |
| Kept patterns | `load_kept_pid_records()` | `pid`, `route`, `rtdir`, `entry_stpid`, `exit_stpid`, `median_minutes`, `n_trips` | 45 pids; medians are the midsummer window (playbook gotcha) |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Legacy column names | `cta.views.legacy_trip_columns(view)` | `run_id → unique_trip_vehicle_day`, `stop_id → stpid`, `arrival_time → bus_stop_time`, `pattern_id → pid`, `direction → rtdir`, `stop_sequence_index → stop_sequence`; values untouched | as input |
| Corridor minutes | `cta.michigan_ave_segment.segment_minutes_from_view(view, segment_or_record) -> Series` | legacy `trip_segment_minutes` on the renamed view filtered to the pid | one per run with both stops |
| Corridor stops + QA | `corridor_stops_from_view(view, *, sequences=None, kept=None) -> (DataFrame, DataFrame)` | `unique_trip_vehicle_day`, `stpid`, `pid`, `route` str; `rtdir` (chosen sequence); `seq_index` int64; `lat`; `stpnm`; `bus_stop_time` tz-aware UTC; `interpolated` bool, always False, kept so `backwards_time_trip_keys` and `segment_view_report` run unchanged; `source`, `service_date`, `calendar_flag` str; `bracket_gap_s` float64. QA: `cta.views.MANSUETO_QA_COLUMNS`, stage `corridor` | one row per observed (run, pid, stop in the chosen sequence); no gap rows |
| Segment sequences | `direction_segment_sequences(path=None) -> dict[str, DataFrame]` | `seg_index` int64 (= the from stop's `seq_index`), `from_stpid`, `to_stpid`, `lat` (midpoint), `stpnm` (`"<from> to <to>"`) | one row per consecutive stop pair |
| Segment speeds + QA | `corridor_segment_speeds(stops, pattern_stops, *, sequences=None) -> (DataFrame, DataFrame)` | `unique_trip_vehicle_day`, `pid`, `route`, `rtdir`, `seg_index`, `from_stpid`, `to_stpid`, `lat`, `stpnm`, `bus_stop_time` (arrival at the hop's start stop, UTC; legacy name so the hour helpers bucket on it), `speed_mph` float64, `hop_n_segments` int64 (segments the hop covers; 1 = exactly this one), `hop_from_stpid`, `hop_to_stpid`, `source`, `service_date`, `calendar_flag`, `bracket_gap_s` (max of the hop's two stops, NaN if either is NaN), `speed_basis` = `"segment"`. QA stage `hops` | one row per (run, pid, `seg_index`) covered by a valid hop; QA rows are candidate hops |
| Segment stats | `corridor_segment_min_per_mile_stats(sub, segment_sequence, *, min_obs=10)` | as `corridor_stop_min_per_mile_stats`, keyed by `seg_index`, `from_stpid`, `to_stpid` | one row per segment |
| Helper changes | `direction_stop_sequences` (gains `lon`), `observed_speed_rows`, `michigan_day_slice_mask`, `filter_dlsd_leak_stops`, `segment_view_report` | signatures unchanged; behaviour in Method steps 4, 6, 7 | — |
| Distance | `straight_line_feet(lat1, lon1, lat2, lon2) -> float` in `cta.michigan_ave_segment` | haversine, feet; the ratio test tolerates small earth-radius differences | one pair of points |

## Method

Prior art to copy: `cta/michigan_ave_segment.py` `interpolate_trip_corridor` (span logic) and `corridor_stop_min_per_mile_stats`;
`cta/views.py` `mansueto_view_from_trips` (per-pid QA, playbook pattern "Emit a QA table from a pipeline stage");
`tests/test_views_mansueto.py` `test_self_consistency_6410_against_legacy_median` (the rename idiom).

1. `legacy_trip_columns` is a rename; `segment_minutes_from_view` filters `pattern_id`, renames, calls
   `trip_segment_minutes`. `tests/test_views_archive.py` and `tests/test_views_mansueto.py` switch to it (no assertion changes).
2. `corridor_stops_from_view`: `kept` defaults to `load_kept_pid_records()`, pids cast to str (playbook gotcha
   "Identifiers arrive as `6410.0`"). View rows of other patterns are dropped as `pattern_not_kept`. The sequence is
   the pattern's `direction` when Northbound or Southbound (all 43 such kept pids); otherwise the sequence holding more
   of its distinct corridor stops (14130 → Southbound, 14132 → Northbound); none → `no_direction_sequence`. Rows at
   stops outside the chosen sequence → `stop_not_in_sequence`. One reason per row; QA additive.
3. Hops: within a run, consecutive observed stops in `seq_index` order. A hop is valid when both `pdist_ft` are known,
   the distance is > 0, it is at most `MAX_HOP_DETOUR_RATIO` × the straight-line distance between the two stops (a hop
   that leaves Michigan is not a speed on Michigan) and the time is > 0; otherwise one reason, in priority
   `missing_pdist`, `nonpositive_hop_distance`, `detour_hop`, `nonpositive_hop_time`. QA stage `hops`: `rows_in` =
   observed stops − runs, `rows_out` = valid hops.
4. A valid hop from `seq_index` i to j covers segments i to j − 1; each gets the hop's speed, `hop_n_segments = j − i`
   and `bus_stop_time` = arrival at i. Every row is used (owner, 2026-11-07): stop times are imputed from positions on
   every source, and a multi-segment hop mostly reflects pattern coverage (1,510 of 1,513 on the archive fixture day,
   all 220 on the 6410 cut, skip only stops their pattern lacks, and every kept hop is within 1.036× straight line).
   The frame has no `interpolated` column;
   `observed_speed_rows` treats a frame without one as all observed. Pooled statistics weight a hop by the segments it
   covers (`hop_n_segments == 1` gives the comparison). No row has a NaN speed.
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
| `MAX_HOP_DETOUR_RATIO` | 1.5 | archive fixture day: 13,712 of 13,714 positive hops within 1.036× straight line (multi-segment median 1.00); the other 2, 5.32× (5,166 route ft against 971 straight-line ft, Madison to Lake/Randolph), are PID 25899's loop off Michigan; owner 2026-11-07 | any value from 1.04 to 5.3 drops the same 2 hops on the fixture |
| `NORTHBOUND_/SOUTHBOUND_DLSD_LEAK_STPIDS` | existing | carried to segments touching them (ADR-010) | drops 220 of 1,210 6410 segment rows |

One new threshold, `MAX_HOP_DETOUR_RATIO`; no `bracket_gap_s` bound (the raw adapter's spec and the figure code decide, ADR-009).

## Acceptance tests

Fixtures: `tests/fixtures/mansueto_6410_last30d.parquet`, `archive_2026-10-29_michigan.*`, `getpatterns/` (no new
fixture). Numbers measured 2026-11-07 with a prototype of steps 2–4.

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
      14132 Northbound with 290; 4 runs with one observed stop; `calendar_flag == ""`; `backwards_time_trip_keys`
      returns exactly 2 trips, both pid 25899, whose pattern loops off Michigan (north to Randolph, east on Randolph, north on Columbus, west on Wacker, back south on Michigan) and so serves Lake/Randolph after South Water; `segment_view_report` with an explicit `cache_status` (no `data/` read) gives
      `pids_missing_from_view == ["1054"]` and no null-speed issue.
- [ ] `test_corridor_segment_speeds_hand_built`: 4-stop sequence, `pdist_ft` 0, 1000, 2000, 3000. Run A at stops 0, 2,
      3 at 13:00, 13:10, 13:12 UTC gives 3 rows: segments 0 and 1 at `2000/5280/(10/60)` mph, `hop_n_segments` 2,
      start 13:00; segment 2 at `1000/5280/(2/60)` mph, `hop_n_segments` 1, start 13:10 (stops 1000 ft apart along a
      meridian, so `straight_line_feet` between them is 1000 ± 5). Run B at stops 1, 2 with equal times gives `nonpositive_hop_time`; run C on a pid whose `pdist_ft`
      falls from stop 1 to 2 gives `nonpositive_hop_distance`; run D on a pid whose `pdist_ft` step from stop 1 to 2 is
      3000 gives `detour_hop`. QA `hops`: `rows_in` 5, `rows_out` 2, reasons sum; no NaN `speed_mph`; `speed_basis == "segment"`.
- [ ] `test_corridor_segment_speeds_6410`: 880 candidate and 880 valid hops; 1,210 rows, 110 runs × the 11 segments
      from 1119 to 1128; 550 with `hop_n_segments > 1`, the segments around stops 18791, 1104 and 1126 that 151 NB lacks;
      median over distinct hops 4.28 ± 0.05 mph; `filter_dlsd_leak_stops` drops 220 rows.
- [ ] `test_corridor_segment_speeds_archive_fixture_day`: 13,716 candidate and 13,712 valid hops;
      `nonpositive_hop_distance == 2` and `detour_hop == 2`, all on pid 25899 and its loop off Michigan (the detours are
      Madison to Lake/Randolph, 5.32× straight line); 15,919 rows, 3,718 with `hop_n_segments > 1`; all 40 segments
      have rows, 7 of them only from multi-segment hops, Madison to Lake/Randolph among them; `filter_dlsd_leak_stops`
      drops 1,319; max `speed_mph` 35.0 ± 0.1; rows for 14130 and 14132 present;
      `bracket_gap_s <= cta.archive.MAX_BRACKET_GAP_S` everywhere.
- [ ] `test_segment_helpers_on_view_outputs`: `direction_stop_sequences` has a `lon` column; `direction_segment_sequences` gives 22 NB and 18 SB rows, the
      first NB one `"Michigan & Roosevelt to Michigan & 11th Street"`; `observed_speed_rows` on the 6410 segments keeps all 1,210 rows with
      `hour` in America/Chicago, which differs from the UTC hour on every row; `michigan_day_slice_mask` agrees;
      `corridor_segment_min_per_mile_stats` against the NB segment sequence returns 22 rows with medians on exactly the
      11 segments from 1119 to 1128 and `lat` the stop midpoint; `slowest_hours` runs; the existing naive tests in
      `tests/test_michigan_ave_segment.py` pass unchanged.

## Out of scope

- Deleting the legacy builders, `PARQUET_COLS` or `local_parquet_path` (deprecate now; the notebooks still call them).
- Re-pointing the speed-plot notebook (a Michigan Next item), regenerating `data/michigan_ave/`, figures, a script, ADR-003
  column names, the leak-exclusion measurement, pooling short segments, a `bracket_gap_s` bound, cross-source speeds,
  and passing times at stops a pattern lacks, by projecting them onto it.

## Open questions

None. Resolved by the owner 2026-11-07: segment speeds (ADR-010); multi-segment hops used; hops that leave Michigan
dropped at `MAX_HOP_DETOUR_RATIO = 1.5`; route 157's two patterns included, directed by stop membership.
