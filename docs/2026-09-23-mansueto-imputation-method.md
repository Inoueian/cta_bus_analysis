# How Mansueto imputes `bus_stop_time` and `speed_mph`: linear in distance between ~5-minute pings (read 2026-09-23)

Tags: `kind:measurement source:mansueto stage:impute topic:thresholds`

Migrated 2026-11-13 from vault `mansueto-imputed-stop-times` (2026-09-23, findings of
`notebooks/mansueto_imputation_investigation.ipynb`). It is the evidence behind CLAUDE.md rule 6 and
behind every "~5 minute" caveat on Mansueto arrivals. The method was read from Mansueto's own code, in
the owner's local clone of their `cta-stop-watch` repository, which agents cannot open; nothing was
re-read for the migration.

## Measurement

Reading `report_automation/interpolation.py`, function `interpolate_stoptime`, in Mansueto's
`cta-stop-watch` repository, and comparing with the published parquets in the notebook.

1. Pattern stops (`typ == "S"`) and bus locations (`typ == "B"`) are interleaved in `seg_combined` order.
2. For each pair of consecutive pings, the route distance `ping_dist` and elapsed time `ping_time_diff`
   are computed.
3. A stop inside the pair gets
   `bus_stop_time = ping_time + ping_time_diff * (accumulated_distance / ping_dist)`.
4. A stop before the first ping or after the last one is extrapolated from the implied segment speed.
5. Only the stop rows are published. The ping rows are dropped from the CloudFront files.

| Column | Meaning |
|---|---|
| `bus_stop_time` | imputed arrival at the stop |
| `speed_mph` | speed over the ping interval that encloses the stop: `(ping_dist / 1609) / (seconds / 3600)` |
| `seg_combined` | pattern segment index, used for ordering |
| `stop_sequence` | stop index along the pattern for the trip |

## Facts confirmed

- The pings are Bus Tracker `getvehicles` fixes scraped about every 5 minutes (the Ghost Buses scrape),
  not aligned to :00 or :05. `tmstmp` is parsed as `%Y%m%d %H:%M`, so it has no seconds. The effective
  resolution of an imputed arrival is therefore about 5 minutes. The raw day CSVs show the same
  truncation directly (`docs/2026-11-10-mansueto-raw-day-profile.md`).
- `speed_mph` outside [1, 115] mph is set to NaN and then forward- and back-filled, so a published speed
  can belong to a neighbouring interval. It is never a stop-to-stop speed.
- Arrivals at the first and last stops of a trip can be extrapolations, not interpolations.
- Because no ping time is published, `bracket_gap_s` is NaN for `source == "mansueto"`.

## DLSD names and filter that rest on this

- `dlsd_minutes` is `bus_stop_time` at the DLSD exit minus the entry, same run and pid.
  `implied_dlsd_mph` is the hop distance over `dlsd_minutes`. Neither is Mansueto `speed_mph`.
- The run filter is structural, `analysis_ok` in `cta.dlsd_run_quality.add_quality_flags`: both times
  present, exit after entry, exit index equal to entry index plus one. Minute caps and posted speed
  limits are not filters; the old `[1, 120]` minute cap survives only as the informational `legacy_drop`
  flag.

## Corrections

- The vault note names `notebooks/dlsd_run_quality.py`; it is `cta/dlsd_run_quality.py`, and
  `build_dlsd_runs` is being replaced by `dlsd_runs_from_view` (`specs/dlsd-runs-from-view.md`; TODO.md
  Foundation, first item).
- The "last 30 days" cache (`scripts/cache_dlsd_parquets.py`) is anchored on `max(bus_stop_time)`, which
  has been 2026-07-28 since the freeze, so the window is 2026-06-28 to 2026-07-28
  (`docs/2026-11-04-mansueto-data-edge.md`).
- The vault note cited `dlsd-cache-last30d-semantics`, `mansueto-processed-max-bus-stop-time` and
  `cta-stop-watch-dataset`; none is in the repo or on the inbox list. `lsd-express-segment-boundaries`
  is on the list.

## How to re-check

Open `interpolate_stoptime` in Mansueto's repository and confirm the formula and the [1, 115] clamp. For
the resolution, `cta.mansueto_raw` reads the raw pings our own imputation uses; the interval between a
bus's consecutive fixes is the number to look at. If Mansueto resumes publishing (ADR-007), re-read the
method before trusting new files.
