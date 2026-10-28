# TODO

Last updated: 2026-10-03

Active work and backlog for the CTA Bus Wait & Travel Time Explorer.

## Phase 1: Routes 8, 65, & 66

Analyze three routes affected by current construction. Build the data ingestion pipeline and compute distributions via scripts and exploratory notebooks — no web app yet. Data access strategy for this phase: download and cache Mansueto parquet files locally.

### Now

- [ ] EDA notebook: explore Mansueto parquet data for routes 8, 65, & 66 — verify schema consistency across routes, check data volumes and date ranges, visualize arrival patterns and headways (`notebooks/eda_routes_8_65_66.ipynb`)
- [ ] Data ingestion for routes 8, 65, & 66: build the run-level view by unioning `trips_<PID>_full.parquet` across all Patterns of each route, normalizing Mansueto columns (`unique_trip_vehicle_day` → `run_id`, `bus_stop_time` → `arrival_time`, etc.) and joining `direction` from GTFS/pattern metadata per vault `canonical-data-views`
- [ ] Build the stop-level view for routes 8, 65, & 66 (route → direction → stop_id → arrival-time list) by grouping the run-level view

### Next

- [ ] Wait-time distribution — compute from the stop-level view for (route, direction, start_stop), filter by day_of_week / time_of_day
- [ ] Travel-time distribution — from the run-level view, filter to runs that visited both start_stop and end_stop, compute pairwise deltas
- [ ] Time-series of average travel time by date — group the run-level view's per-run deltas by date, filter to chosen day_of_week
- [ ] Handle direction-only destination (aggregate over all downstream stops in that direction)

## DLSD Express Analysis

Side-quest: Lake Shore Drive express segment timing for all-day routes 146 & 147 (`notebooks/dlsd_travel_time_146_147.ipynb`) and rush-hour-only routes 134, 135, 136, 143, and 148. Comparison plots in `notebooks/dlsd_express_comparison_plots.ipynb`. Active backlog for this side-quest is complete.

## Michigan Ave Bus Lane Analysis

Side-quest: measure current bus speed on the downtown Michigan Avenue corridor (Roosevelt to Delaware) ahead of the new northbound dedicated bus lane (Roosevelt to Wacker). This establishes a before-picture and may inform what to build in later phases. Initial v1 uses candidate routes present in Mansueto `rt_to_pid.csv` (route **10** excluded until refinement below). The corridor stop list is frozen in `notebooks/michigan_ave_stops_snapshot.json` (40 on-avenue stops after side-street exclusions). Vault: `michigan-ave-bus-lane-segment`, `michigan-ave-corridor-stops-snapshot`, `cta-holiday-schedule-filtering`.

### Now

- [ ] Segment-view QA — route **151** NB PIDs **14130** and **14132**: `last30d` cache exists but neither PID appears in `data/michigan_ave/segment_view.parquet` (no corridor stop rows). Drop from `notebooks/michigan_ave_kept_pids.json` or fix the filter (vault `michigan-ave-segment-view`).
- [ ] Segment-view QA — sample **137** trips with backwards observed `bus_stop_time` vs latitude `seq_index` (likely ~5 min imputation vs sequence order; QA flag, not auto-drop until sampled; vault `michigan-ave-segment-view`).

### Next
- [ ] Route 10 / Mansueto catalog gap (refinement): confirm route **10** is absent from CloudFront `rt_to_pid.csv` (not a `10.0` string mismatch). If missing, discover PIDs via Bus Tracker (`getpatterns` / route lookup per vault `cta-bus-tracker-api`), add route 10 to Michigan Ave analysis, and document whether Mansueto parquets exist or route 10 is API-only (`notebooks/michigan_ave_stop_discovery.ipynb`; vault `rt-to-pid-missing-parquet`). Defer until initial speed plots look reasonable.
- [ ] Holiday schedule filtering (cross-cutting): define a holiday calendar for CTA (or at minimum US federal holidays) and exclude holiday dates from weekday/weekend slices. This also applies retroactively to the DLSD analysis.

## Phase 2: Static web app for all routes

Pick a web-app stack, extend ingestion to all (or most) CTA bus routes, and deploy as a static dataset served on a webpage.

- [ ] Pick the web-app stack (Streamlit vs. Dash vs. FastAPI + React vs. Flask + templates); log the choice as an ADR in DECISIONS.md
- [ ] Extend ingestion to all (or most) routes
- [ ] Frontend flow: route dropdown → start-stop dropdown → destination-stop-or-direction → optional time/day picker (default = "now")
- [ ] Frontend: histogram for wait time, histogram for travel time, line chart for average travel time over time
- [ ] Deployment target (Streamlit Cloud / Fly / Render / Vercel — depends on stack)

## Phase 3: Scheduled refresh and extras

Scheduled data updates, richer metrics, and polish features that go beyond the initial static snapshot.

- [ ] Scheduled refresh from the Mansueto bucket (respecting the ~14-day upstream lag documented in the knowledge-vault note `cta-stop-watch-freshness-check`)
- [ ] Add derived metrics: excess wait vs. scheduled headway, on-time reliability score
- [ ] Community-area rollups (mirror what the Mansueto dashboard does, but interactive)
- [ ] Compare weekday-vs-weekend distributions side by side
- [ ] Persist and share URLs for a chosen route+stop+time combination

## Done

- [x] Archive initial iteration onto `legacy` branch (2026-08-10)
- [x] Verify Mansueto `trips_<PID>_full.parquet` columns and trip IDs (route 66 / PID 6662; mapping in knowledge-vault `canonical-data-views` and `scripts/verify_parquet.py`) (2026-09-15)
- [x] New notebook: stop discovery for routes 134, 135, 136, 143, 148 — identify DLSD boundary stops (entry/exit per pattern) via Bus Tracker API (`notebooks/dlsd_stop_discovery_rush_routes.ipynb`; 11 PIDs merged into `dlsd_boundaries_snapshot.json`) (2026-09-24)
- [x] Rush hour sample exploration + plot guard helpers (`notebooks/dlsd_rush_sample_counts.ipynb`, `valid_rush_plot_cells` / `hour_dlsd_stats` in `notebooks/dlsd_run_quality.py`; tests in `tests/test_dlsd_run_quality.py`) (2026-09-24)
- [x] Set rush plot gate: `MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY = 30` + `valid_rush_plot_cells()` (weekday targets; Friday reuses; vault `dlsd-rush-hour-min-sample`) (2026-09-24)
- [x] Build `dlsd_runs` for rush routes via extended `dlsd_boundaries_snapshot.json` + local `data/mansueto/` cache (same `build_dlsd_runs` as 146/147) (2026-09-24)
- [x] Data-availability guard: `valid_rush_plot_cells` + `hour_dlsd_stats(..., valid_cells=...)` for rush plots (wire into comparison notebook when built) (2026-09-24)
- [x] Comparison plots — three panes, one per northern exit pair: Stockton/Arlington (134 vs 143), Belmont (135 vs 146), Irving Park (136 vs 148) (`notebooks/dlsd_express_comparison_plots.ipynb`) (2026-10-02)
- [x] Solo pane for route 147 (Foster / Marine Drive northern exit) (`notebooks/dlsd_express_comparison_plots.ipynb`) (2026-10-02)
- [x] Add 95th-percentile line/band to DLSD duration-by-hour plots (worst-case alongside median and IQR) (`notebooks/dlsd_express_comparison_plots.ipynb`) (2026-10-02)
- [x] Add day-of-week views: Friday-only and weekend, alongside existing weekday (`notebooks/dlsd_express_comparison_plots.ipynb`) (2026-10-02)
- [x] Michigan Ave stop discovery: 40 on-avenue stops Roosevelt→Delaware; §4.5 side-street exclusions; `notebooks/michigan_ave_stops_snapshot.json` (`notebooks/michigan_ave_stop_discovery.ipynb`) (2026-10-02)
- [x] Michigan Ave 30-day Mansueto cache for candidate PIDs (`scripts/cache_dlsd_parquets.py --source michigan --days 30`) (2026-10-03)
- [x] Michigan Ave route identification: longest corridor segment from cached `getpatterns`; median ≥5 min filter; endpoint coverage diagnostic → **12 routes / 45 PIDs** (`notebooks/michigan_ave_route_identification.ipynb`, `notebooks/michigan_ave_segment.py`, `notebooks/michigan_ave_kept_pids.json`) (2026-10-03)
- [x] Michigan Ave 148 SB PID 6402: local `getpatterns` hand trim (four Michigan stops after Hubbard removed); Delaware→Hubbard median qualifies; added to kept list — knowledge-vault `michigan-ave-6402-pattern-trim` (2026-10-03)
- [x] Michigan Ave segment view: NB/SB latitude sequences, per-trip `(unique_trip_vehicle_day, stpid)` rows with flanking-mean `speed_mph` gap fill (`notebooks/michigan_ave_segment.py`, `notebooks/michigan_ave_segment_view.ipynb` → `data/michigan_ave/segment_view.parquet`; vault `michigan-ave-segment-view`); check passed for **6402** — zero rows at trimmed stops `1104`–`1106`, `18396` (2026-10-03)
- [x] Michigan Ave corridor speed plots: slow-hour diagnostic + latitude corridor charts (minutes/mile, dual mph axis); DLSD-leak stops excluded; Mon–Thu / Friday / weekend (`notebooks/michigan_ave_speed_plots.ipynb`, `slowest_hours` / `corridor_stop_min_per_mile_stats` in `notebooks/michigan_ave_segment.py`; vault `michigan-ave-slow-hour-corridor-plots`) (2026-10-03)
