# DLSD rush-hour express routes 134, 135, 136, 143, 148: boundary pairs for 11 PIDs and the comparison panes (measured 2026-09-24)

Tags: `kind:measurement source:bustracker stage:figure topic:pattern-catalog`

Migrated 2026-11-13 from vault `2026-09-24-dlsd-rush-express-routes` (the expected-geography checklist
that `notebooks/dlsd_stop_discovery_rush_routes.ipynb` is reviewed against, and the plan behind
`notebooks/dlsd_express_comparison_plots.ipynb`). The pairs were compared with
`notebooks/dlsd_boundaries_snapshot.json` for the migration; nothing was fetched.

## Measurement

Same method as for 146 and 147 (`docs/2026-09-23-dlsd-segment-boundaries-146-147.md`): `getpatterns`,
largest consecutive hop over 10,000 ft. Run 2026-09-24 in `notebooks/dlsd_stop_discovery_rush_routes.ipynb`;
11 PIDs were merged into the snapshot, 29 with the 18 of routes 146 and 147.

| Route | Direction | Entry | Exit |
|---|---|---|---|
| 134 | Northbound | `3954` Wacker (Upper) & Columbus | `1145` Stockton & Arlington |
| 134 | Southbound | `1080` Stockton & Arlington | `14222` Wacker (Upper) & Columbus |
| 135 | Northbound | `3954` Wacker (Upper) & Columbus | `1155` Inner Lake Shore Drive & Belmont |
| 135 | Southbound | `4867` Lake Shore Drive & Belmont | `14222` Wacker (Upper) & Columbus |
| 136 | Northbound | `3954` Wacker (Upper) & Columbus | `4888` Marine Drive & Irving Park |
| 136 | Southbound | `4864` Marine Drive & Bittersweet | `14222` Wacker (Upper) & Columbus |
| 143 | Northbound | `1128` Michigan & Delaware/Walton | `1145` Stockton & Arlington |
| 143 | Southbound | `1080` Stockton & Arlington | `1097` Michigan & Delaware |
| 148 | Northbound | `1128` Michigan & Delaware/Walton | `4928` Irving Park & Marine Drive |
| 148 | Southbound | `4927` Irving Park & Marine Drive | `1097` Michigan & Delaware |

One PID per row, except 135 Southbound with two.

## Expected geography (what a rediscovery is checked against)

- 134, 135, 136, 143 and 148 run on the Drive in rush hours only; 146 and 147 run all day.
- The 13x routes (134, 135, 136) join the Drive from Wacker Drive: `3954` northbound entry, `14222`
  southbound exit. The 14x routes (143, 146, 147, 148) join further north at Michigan & Delaware:
  `1128` northbound entry, `1097` southbound exit.
- Route 136's southbound entry is Marine Drive & Bittersweet (`4864`), not the Irving Park stop its
  northbound exit uses (`4888`).

## Comparison design

Pairing a 13x route with a 14x route at the same northern exit isolates the difference between the two
downtown ends.

| Pane | Northern exit | Routes |
|---|---|---|
| Fullerton | Stockton / Arlington | 134, 143 |
| Belmont | Belmont | 135, 146 |
| Irving Park | Irving Park, or Bittersweet for 136 southbound | 136, 148 |
| Foster | Foster & Marine Drive | 147 alone |

- Metric: minutes between the two stops that bracket the Drive (`dlsd_minutes`), by hour of day:
  median line, 25 to 75% band, 95th percentile. The comparison notebook shows minutes only (13x blue,
  14x purple); `implied_dlsd_mph` is still produced by `hour_dlsd_stats`.
- Day slices: Mon to Thu, Friday, weekend. Only 146 and 147 appear on the weekend pane.
- Rush routes are drawn only at the cells that pass the Mon to Thu gate
  (`docs/2026-09-24-dlsd-rush-hour-min-sample.md`).

## Corrections

- After a snapshot change the vault says to run `scripts/cache_dlsd_parquets.py` and `build_dlsd_runs`.
  `build_dlsd_runs` is being replaced by `cta.dlsd_run_quality.dlsd_runs_from_view`
  (`specs/dlsd-runs-from-view.md`; TODO.md Foundation, first item). The module is
  `cta/dlsd_run_quality.py`, not `notebooks/dlsd_run_quality.py`.
- Day slices do not exclude holidays (playbook gotcha).

## How to re-check

Compare the table with `notebooks/dlsd_boundaries_snapshot.json`. To rediscover, run
`notebooks/dlsd_stop_discovery_rush_routes.ipynb` with `WRITE_SNAPSHOT = False` (needs `CTA_API_KEY`) and
compare its section 2 output with the geography above before writing anything.
