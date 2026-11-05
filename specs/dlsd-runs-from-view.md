# Spec: DLSD runs from the run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-05  ·  TODO item: Foundation "Move `cta.dlsd_run_quality` and `cta.michigan_ave_segment` onto the run-level view (the "later item" of `specs/mansueto-adapter.md`): both read Mansueto parquets directly today (`PARQUET_COLS`, `local_parquet_path`, `median_segment_minutes_for_pid`); make them take a run-level DataFrame so the two Michigan segment-view QA items and the DLSD calendar retro-apply run on either source, with `bracket_gap_s` NaN treated as unknown. Spec: to write." (DLSD half; the Michigan half is `specs/michigan-segment-from-view.md`)

## Question

The DLSD express figures (`notebooks/dlsd_express_comparison_plots.ipynb`) are built from `cta.dlsd_run_quality.build_dlsd_runs`,
which reads Mansueto parquets and so stops at 2026-07-28 (ADR-007) and can never show an archive day. Build the same
one-row-per-run table from the ADR-003 run-level view instead, so the DLSD timing runs on either source, carries
`calendar_flag` for the holiday retro-apply (TODO Foundation, calendar item), and is the shape Phase 1 travel-time
computation will reuse. The ± 1 neighbour idiom this helper relies on is exactly why ADR-008 made `stop_sequence_index` dense.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Run-level view | `cta.views.run_level_from_archive` / `run_level_from_mansueto` | `cta.views.RUN_LEVEL_COLUMNS` | either source; `bracket_gap_s` NaN on Mansueto means unknown, not 0 |
| DLSD boundaries | `notebooks/dlsd_boundaries_snapshot.json` via `load_dlsd_boundaries` | per pid: `route`, `rtdir`, `entry_stpid`, `exit_stpid`, `hop_feet` | 29 pids; `hop_feet` is the straight-line (haversine) entry→exit distance from `notebooks/dlsd_stop_discovery_rush_routes.ipynb` |
| Archive fixture | `tests/fixtures/archive_2026-10-29_michigan.*` + `tests/fixtures/getpatterns/` | as `tests/test_views_archive.py` | holds 22 of the 29 DLSD pids (routes 143, 146, 147, 148); the rush pids of 134/135/136 are absent |

On the getpatterns fixture every one of the 22 pids has `stop_rank(exit) − stop_rank(entry) == 1`, so the dense index
reproduces the legacy `exit_sequence == entry_sequence + 1` check. getpatterns `pdist` for the hop is 3–14% longer than
`hop_feet` (e.g. 4511: 12,041 vs 10,554 ft; 146 NB: 16,385 vs 15,566 ft); the spec keeps `hop_feet` (see Open questions).

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| DLSD runs | `cta.dlsd_run_quality.dlsd_runs_from_view(view, boundaries=None) -> (DataFrame, DataFrame)` | `run_id` str, `pid` str, `route` str, `rtdir` str, `source` str, `service_date` str, `calendar_flag` str, `entry_time` / `exit_time` tz-aware UTC, `entry_sequence` / `exit_sequence` int64 (= `stop_sequence_index`), `entry_bracket_gap_s` / `exit_bracket_gap_s` float64 (NaN = unknown), `pre_dlsd_time` / `post_dlsd_time` tz-aware UTC or NaT, `bracket_minutes` float64, `hop_feet`, `dlsd_miles`, `dlsd_minutes`, `implied_dlsd_mph`, `dlsd_minutes_bin` float64, `hour` int64, `day_of_week` int64, `is_weekday` bool (hour and weekday in America/Chicago), `ok_times_present`, `ok_time_order`, `ok_consecutive`, `analysis_ok`, `legacy_drop` bool | one row per (`run_id`, `pid`) whose run has both the entry and the exit stop in the view |
| QA table | second element of the tuple | `pid`, `stage`, `rows_in`, `rows_out`, `reason`, `count` (`cta.views.MANSUETO_QA_COLUMNS`) | one row per (pid, reason); rows are runs (distinct `run_id` of the pid), one stage `endpoints` |

Dropped relative to `build_dlsd_runs`: `entry_speed_mph`, `exit_speed_mph`, `entry_seg`, `exit_seg`,
`same_ping_interval_proxy` (Mansueto ping fields; rule 6 and not in the view); `unique_trip_vehicle_day` becomes
`run_id`. Every column the downstream helpers read (`day_slice_mask`, `hour_run_counts`, `valid_rush_plot_cells`,
`hour_dlsd_stats`: `route`, `rtdir`, `hour`, `day_of_week`, `entry_time`, `dlsd_minutes`, `implied_dlsd_mph`,
`analysis_ok`) keeps its name and meaning, so they run on the new table unchanged.

## Method

Prior art to copy: `cta/dlsd_run_quality.py` `build_dlsd_runs` and `add_quality_flags` (the per-pid entry/exit
aggregation, bracket lookup and flag columns, re-expressed on view columns); `cta/views.py` `mansueto_view_from_trips`
(per-pid loop with a `pid` column in front of the QA rows, pids with no rows still listed);
`tests/test_views_archive.py` `test_corridor_minutes_match_mansueto_medians` (fixture-day loop over kept pids).

1. `boundaries` defaults to `load_dlsd_boundaries()`; keys and stop ids are cast to str. Only `pattern_id` values that
   are boundary pids are considered; other patterns in the view are ignored (not a QA drop: the table is per DLSD pid).
2. Per pid: `entry_time` = min `arrival_time` at `entry_stpid`, `entry_sequence` = min `stop_sequence_index` there,
   `entry_bracket_gap_s` = `bracket_gap_s` of that row; `exit_*` the same with max at `exit_stpid` (legacy
   aggregation). Inner-join on `run_id`. Runs of the pid lacking one stop are counted with reason `missing_entry_stop`
   or, if the entry is present, `missing_exit_stop` (one reason per run). A boundary pid with no rows in the view gets
   `rows_in = rows_out = 0`, count 0, so the QA table always has 29 pids.
3. Bracket: `pre_dlsd_time` = `arrival_time` of the row at `entry_sequence − 1`, `post_dlsd_time` at
   `exit_sequence + 1`, NaT when absent; `bracket_minutes` as legacy.
4. Derived columns as legacy from `hop_feet`: `dlsd_miles`, `dlsd_minutes`, `implied_dlsd_mph`, `dlsd_minutes_bin`
   (5-minute floor). `hour`, `day_of_week`, `is_weekday` from `entry_time` converted to `America/Chicago` (legacy
   `bus_stop_time` was naive Chicago wall time, so the values agree; on UTC they would be off by 5–6 h on every row).
5. Flags via `add_quality_flags` unchanged: `ok_consecutive` is `exit_sequence == entry_sequence + 1` on the dense
   index; `legacy_drop` bounds become the named constants below. `bracket_gap_s` is carried, never used in a flag:
   NaN is unknown, and a gap filter already ran upstream (`cta.archive.MAX_BRACKET_GAP_S`).
6. `source`, `service_date`, `calendar_flag` are copied from the entry row. Nothing is dropped for a calendar flag;
   the retro-apply is a notebook filter on `calendar_flag`.
7. Output sorted by (`pid`, `entry_time`); `cta.mansueto.qa_rows` builds the QA rows (the shared helper of the `/qa`
   item may replace it later; the columns do not change).

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `LEGACY_DROP_MIN_MINUTES` | 1.0 | legacy inline `dlsd_minutes < 1` (`notebooks/mansueto_imputation_investigation.ipynb`); unchanged, now named | none: the flag is informational |
| `LEGACY_DROP_MAX_MINUTES` | 120.0 | legacy inline `dlsd_minutes > 120`; unchanged, now named | none |
| `MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY` | 30 | existing; not touched | — |

No new threshold. `hop_feet` stays the published distance (rule 2).

## Acceptance tests

Fixture: `tests/fixtures/archive_2026-10-29_michigan.*` with `tests/fixtures/getpatterns/`, built into the view by
the `run_level` fixture of `tests/test_views_archive.py` (reuse it via a shared conftest fixture or copy the three
lines). Counts below were measured on 2026-11-05 with the kept-pid view (`103,364` rows, `1,562` runs).

- [ ] `test_dlsd_runs_from_view_hand_built`: a hand-built view (columns exactly `RUN_LEVEL_COLUMNS`) with pattern
      `p1` (`entry_stpid` `e`, `exit_stpid` `x`) and four runs: A has stops at indices 4, 5 (`e`), 6 (`x`), 7 with
      arrivals 2026-07-07 13:00/13:10/13:20/13:30 UTC → `dlsd_minutes == 10.0`, `hour == 8`, `day_of_week == 1`,
      `is_weekday`, `bracket_minutes == 30.0`, `analysis_ok`; B lacks `x` → absent from the output; C has `x` at index
      7 with a stop between → `ok_consecutive` False, `analysis_ok` False; D is `source == "mansueto"` with
      `bracket_gap_s` NaN → `entry_bracket_gap_s` NaN and `analysis_ok` True. `entry_time` is tz-aware UTC and
      `hop_feet` comes from the hand-built boundaries dict.
- [ ] `test_dlsd_runs_from_view_qa_sums`: on the hand-built view, QA has one stage `endpoints`, `rows_in == 4`,
      `rows_out == 3`, reasons `{missing_exit_stop: 1}`, and `sum(count) == rows_in − rows_out`; a second boundary pid
      absent from the view appears with `rows_in == rows_out == 0`.
- [ ] `test_dlsd_runs_from_view_archive_fixture_day`: on the fixture-day view with the real boundaries, the output has
      445 rows over the 22 fixture pids (per route: 143 → 32, 146 → 203, 147 → 168, 148 → 42), `analysis_ok` on
      every row, `ok_consecutive` on every row, `entry_bracket_gap_s <= cta.archive.MAX_BRACKET_GAP_S` everywhere,
      `source == "archive"`, `calendar_flag == ""`, and `dlsd_minutes` medians 9.99 ± 0.05 for pid 4524 and
      6.86 ± 0.05 for pid 6582. The QA table lists all 29 pids; the 7 rush pids have `rows_in == 0`.
- [ ] `test_dlsd_runs_from_view_legacy_helpers_run`: `valid_rush_plot_cells`, `hour_run_counts(..., day_slice="weekday")`
      and `hour_dlsd_stats(sub, DEFAULT_PLOT_HOURS, route="146", rtdir="Northbound")` accept the fixture-day output
      without error; `hour_run_counts` sums to the number of `analysis_ok` rows of the routes asked for.
- [ ] `test_dlsd_hours_are_chicago`: on the fixture-day output, `hour` equals `entry_time.dt.tz_convert("America/Chicago").dt.hour`
      on every row and differs from the UTC hour on every row.

## Out of scope

- Deleting or rewriting `build_dlsd_runs`, `PARQUET_COLS`, `local_parquet_path`: the notebooks and
  `scripts/dlsd_weekday_friday_summary.py` still call them, and `/implement` does not edit notebooks. Mark them
  deprecated in the docstring; removal is a follow-up once the notebooks are re-pointed (Open questions).
- Re-running the DLSD notebooks or regenerating any figure; the calendar retro-apply itself.
- Replacing `hop_feet` with getpatterns `pdist`; any change to `implied_dlsd_mph` (published; rule 2).
- Any speed proxy from `bracket_gap_s` (NaN = unknown is the only rule this spec sets).
- A Mansueto-side fixture for DLSD: the committed cuts (6410, route 3) hold no DLSD pid; the hand-built case covers
  the NaN path. Building `trips_<dlsd pid>` cuts is a `/fixture` job if the owner wants one.
- Michigan Ave helpers (the sibling spec).

## Open questions

1. `hop_feet` (haversine) vs getpatterns `pdist` for `dlsd_miles`: pdist follows the road and is 3–14% longer, so
   `implied_dlsd_mph` would rise by that much. Keep `hop_feet` now (recommended, rule 2) and open a separate item?
2. Should `build_dlsd_runs` become a thin wrapper (`read_trips` → `mansueto_view_from_trips` → `dlsd_runs_from_view`)
   in this change, dropping the five Mansueto-only columns from its output? Recommended: no; deprecate and remove
   after the owner re-points the three notebooks and the script (a TODO line to add when this closes).
