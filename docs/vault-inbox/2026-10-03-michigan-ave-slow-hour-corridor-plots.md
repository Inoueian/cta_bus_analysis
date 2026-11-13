---
title: "Michigan Ave slow-hour corridor speed plots"
category: projects
project: cta-bus-analysis
tags: [michigan-ave, speed-plots, speed_mph, minutes-per-mile, dlsd-leak]
created: 2026-10-03
source: cta_bus_analysis/notebooks/michigan_ave_speed_plots.ipynb
---

`notebooks/michigan_ave_speed_plots.ipynb` charts observed Mansueto **`speed_mph`** (ping-interval, not hop mph) pooled across kept routes, for the **3 slowest hours** (within `DEFAULT_PLOT_HOURS` 6–22) per day slice: **Mon–Thu**, **Friday**, **weekend**. Override via `SLOW_HOURS_OVERRIDE` in the notebook. Same hours for NB and SB.

## DLSD-leak stop exclusion

Drop from charts (not from corridor definition in **`michigan-ave-bus-lane-segment`**):

| stpid | rtdir | stop |
|-------|-------|------|
| `1097` | Southbound | Michigan & Delaware |
| `1128` | Northbound | Michigan & Delaware/Walton |
| `1127` | Northbound | Michigan & Chestnut |
| `1098` | Southbound | Michigan & Pearson |

Chicago **`1126`** (NB) stays. Helpers: `filter_dlsd_leak_stops`, `NORTHBOUND_DLSD_LEAK_STPIDS`, `SOUTHBOUND_DLSD_LEAK_STPIDS` in `notebooks/michigan_ave_segment.py`.

## Chart layout

- Input: `data/michigan_ave/segment_view.parquet` — build with `notebooks/michigan_ave_segment_view.ipynb`.
- Rows: `interpolated=False` only (`observed_speed_rows`), then **`shared_observation_window`** (720h ending at max observed time) — **`michigan-ave-shared-observation-window`**; not the full segment-view date span.
- One figure per day slice; **two panels** (Northbound, Southbound), shared y.
- X: latitude south → north; tick labels at Roosevelt, Ida B. Wells, Madison, E. Wacker, Chicago (`corridor_street_tick_positions`). Same tick lats on NB and SB: per-direction mean lat of matching stops; if both directions match, average those means (NB-only streets still label SB panel).
- Y (left): **minutes/mile** `60/speed_mph` — slow traffic = **high** min/mi at top.
- Y (right): `ax.secondary_yaxis("right", functions=(lambda t: 60/t, lambda m: 60/m))` for mph aligned to min/mi.
- Stats per stop, hours pooled: median line, IQR band (`60/q75`–`60/q25` mph quantiles), dashed **`60/q05(speed)`** = p95 minutes/mile.
- `MIN_OBS` default **10** per stop; gaps when below.

## Slow-hour pick

- `corridor_hourly_median_speed` — pooled median by hour (leak stops excluded).
- `slowest_hours(obs, day_slice, n=3)` — lowest median mph hours.

## QA / policy

- Do **not** drop backwards-`bus_stop_time` trips (~137); flag only.
- Holidays remain in weekday slices — **`cta-holiday-schedule-filtering`**.

## Related

- michigan-ave-segment-view
- michigan-ave-bus-lane-segment
- mansueto-imputed-stop-times
- dlsd-rush-express-routes
