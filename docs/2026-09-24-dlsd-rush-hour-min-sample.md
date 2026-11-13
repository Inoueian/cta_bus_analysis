# DLSD rush plots: cells gated at 30 Mon to Thu runs; Friday median 12 runs per cell (measured 2026-09-24)

Tags: `kind:measurement source:mansueto stage:figure topic:thresholds`

Migrated 2026-11-13 from vault `dlsd-rush-hour-min-sample` (2026-09-24, from
`notebooks/dlsd_rush_sample_counts.ipynb`). It is the evidence for
`cta.dlsd_run_quality.MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY = 30` and for gating every rush plot on Mon to
Thu counts. Nothing was re-counted for the migration.

## Measurement

`hour_run_counts` on `analysis_ok` runs of the rush routes, per (`route`, `rtdir`, day slice, hour), from
the local 30-day Mansueto cache through `build_dlsd_runs(..., prefer_local=True)`, run 2026-09-24. Among
cells with at least one run:

| Day slice | Cells with data | Min | Median | Max |
|---|---|---|---|---|
| weekday (Mon to Thu) | 52 | 1 | 62 | 176 |
| friday | 45 | 1 | 12 | 34 |
| weekend | sparse, often 0 | | | |

Peak weekday hours usually reach 30 runs; many off-peak weekday cells and most Friday cells do not.

## The rule

- `valid_rush_plot_cells(dlsd_runs)` returns the (`route`, `rtdir`, `hour`) cells of `RUSH_ROUTES`
  (134, 135, 136, 143, 148) with `n_runs >= 30` on Mon to Thu `analysis_ok` runs.
- Every slice uses that one set. `hour_dlsd_stats(..., valid_cells=...)` blanks rush statistics outside
  it, which matplotlib draws as gaps.

| Chart | Statistics from | Rush gate |
|---|---|---|
| weekday | Mon to Thu runs | the Mon to Thu set |
| mon_fri | Mon to Fri runs | the same set |
| friday | Friday runs only | the same set; no Friday count is required, so a cell can rest on few or no Friday runs |
| weekend | Sat and Sun runs | none: `routes_for_day_slice("weekend")` is 146 and 147 only |

- Routes 146 and 147 are never gated.
- `MIN_RUNS_RUSH_HOUR` stays `None` and is deprecated. Do not pass `min_runs=30` per slice for rush
  routes: on Friday it would remove almost every cell.
- `DEFAULT_PLOT_HOURS` is 6 to 22. Tests: `tests/test_dlsd_run_quality.py`.

## Corrections

- The "30-day cache" is the 30 days before `max(bus_stop_time)`. On 2026-09-24 that was already
  2026-06-28 to 2026-07-28 (`docs/2026-11-04-mansueto-data-edge.md`), so the counts describe midsummer.
- The module is `cta/dlsd_run_quality.py`, not `notebooks/dlsd_run_quality.py`.
- The vault's commands use `env/bin/python`; any interpreter with `requirements.txt` installed works.
- Day slices do not exclude holidays (playbook gotcha), so a few counted days ran holiday service.

## How to re-check

Run `notebooks/dlsd_rush_sample_counts.ipynb` for the table. For the Mon to Thu against Friday report:

```bash
python scripts/dlsd_weekday_friday_summary.py --cache-variant last365d --routes all
```

after `python scripts/cache_dlsd_parquets.py --days 365 --force` (see each script's `-h`). The 30 is a
published threshold: changing it is Rule 2.
