---
title: "DLSD rush routes — minimum runs per hour for plots"
category: projects
project: cta-bus-analysis
tags: [dlsd, rush-hour, min-sample, hour_dlsd_stats, plotting, valid_rush_plot_cells]
created: 2026-09-24
source: notebooks/dlsd_rush_sample_counts.ipynb
---

Rush comparison plots gate **which (route, direction, hour) cells appear** using **weekday (Mon–Thu) run counts only**, not the slice being plotted.

## Eligibility rule

- **`MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY = 30`** in `notebooks/dlsd_run_quality.py`.
- **`valid_rush_plot_cells(dlsd_runs)`** builds targets from `hour_run_counts(..., day_slice="weekday", routes=RUSH_ROUTES)` where **`n_runs >= 30`** on **`analysis_ok`** runs.
- **Weekday charts:** stats from Mon–Thu runs; `hour_dlsd_stats(..., valid_cells=valid_rush_plot_cells(...))` NaN-masks rush stats outside that set (matplotlib gaps).
- **Mon–Fri charts** (`notebooks/dlsd_express_comparison_plots.ipynb`): stats from **Mon–Fri** runs (`day_slice="mon_fri"`); **same** Mon–Thu-derived `valid_cells` for rush gating.
- **Friday charts:** stats from **Friday-only** runs; **same** `valid_cells` — **no** separate Friday ≥30 filter. A target can have few or zero Friday trips; stats reflect Friday data or NaN.
- **Weekend charts:** **`routes_for_day_slice("weekend")`** → **146 and 147 only** (rush does not run). No 30-run gate for 146/147.
- **146 / 147:** unchanged — no rush-style eligibility set.

Legacy **`MIN_RUNS_RUSH_HOUR`** remains **`None`**; use **`valid_cells`** instead of per-slice `min_runs` for rush gating.

## Day slices

| slice | mask | rush routes in view |
|-------|------|---------------------|
| weekday | Mon–Thu `day_of_week` 0–3 | 134–136, 143, 148 + pairs with 146/147 |
| mon_fri | Mon–Fri `day_of_week` 0–4 | same (comparison notebook block) |
| friday | `day_of_week == 4` | same rush routes |
| weekend | Sat–Sun `day_of_week >= 5` | **146, 147 only** |

Grain for counts: `(route, rtdir, day_slice, hour)` → `n_runs` from local Mansueto cache via `build_dlsd_runs(..., prefer_local=True)`.

## Helpers (`dlsd_run_quality.py`)

- `RUSH_ROUTES` = 134, 135, 136, 143, 148
- `valid_rush_plot_cells`, `routes_for_day_slice`, `day_slice_mask`, `hour_run_counts`, `hour_dlsd_stats(..., valid_cells=...)`
- `DEFAULT_PLOT_HOURS` = 6..22
- Tests: `tests/test_dlsd_run_quality.py`

## Observed counts (30d Mansueto cache, 2026-09-24 run)

Among cells with **`n_runs > 0`** (all rush route × direction × hour in slice):

| day_slice | cells with data | min | median | max |
|-----------|-----------------|-----|--------|-----|
| weekday | 52 | 1 | 62 | 176 |
| friday | 45 | 1 | 12 | 34 |
| weekend | sparse / often 0 | — | — | — |

Weekday peak hours often **≥30** runs; many off-peak weekday cells and most Friday cells are **below 30** — hence weekday-derived targets and Friday reuse.

## Comparison notebook usage

```python
valid = valid_rush_plot_cells(dlsd_runs)
sub = dlsd_runs.loc[day_slice_mask(dlsd_runs, day_slice) & ...]
stats = hour_dlsd_stats(
    sub,
    DEFAULT_PLOT_HOURS,
    route=...,
    rtdir=...,
    valid_cells=valid,
)
```

Do **not** apply `min_runs=30` on Friday counts for rush routes.

## Mon–Thu vs Friday report

Repeatable summary (volumes, pooled and per-route medians, valid-cell hour deltas):

```bash
env/bin/python scripts/dlsd_weekday_friday_summary.py --cache-variant last365d --routes all
env/bin/python scripts/dlsd_weekday_friday_summary.py --write-md reports/dlsd_weekday_friday_summary.md
```

Re-run after refreshing `last365d` cache (`cache_dlsd_parquets.py --days 365 --force`).

## Related

- dlsd-rush-express-routes
- dlsd-cache-last30d-semantics
