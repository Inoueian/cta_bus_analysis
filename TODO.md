# TODO

Last updated: 2026-11-04

Active work and backlog for the CTA Bus Wait & Travel Time Explorer. Non-trivial items get a spec in `specs/` (template: `specs/TEMPLATE.md`) before implementation; see [CLAUDE.md](CLAUDE.md).

## Foundation

Unblocks spec-driven, agent-implemented work. See [ADR-004](DECISIONS.md) (two data sources) and [ADR-005](DECISIONS.md) (package + DuckDB).

- [ ] Mansueto adapter → run-level view (the former Phase 1 ingestion item, now one of two adapters). Mansueto is frozen at 2026-07-28 (ADR-007, `docs/2026-11-04-mansueto-data-edge.md`), so validation is same-source self-consistency, not a same-day archive comparison. Spec: `specs/mansueto-adapter.md` (draft).
- [ ] Calendar module (`cta/calendar.py`): CTA holidays, archive `known_gaps` windows, Mansueto freshness; one place, flag rows rather than drop them. Started 2026-11-03 with the archive adapter (six Sunday-schedule holidays, `known_gaps`, `calendar_flag`); Mansueto freshness (read `MANSUETO_DATA_EDGE` and the per-pid `trips_<pid>_full.meta.json` the adapter spec defines; the source-coverage hole 2026-07-28 to 2026-09-27 belongs here too, ADR-007) and the vault note migration remain. Absorbs the former "Holiday schedule filtering (cross-cutting)" item; applies retroactively to the DLSD analysis.
- [ ] Fixtures under `tests/fixtures/`: ~~one archive day filtered to the Michigan kept PIDs~~ (done 2026-11-03: `archive_2026-10-29_michigan.ndjson.gz` + manifest), ~~`getpatterns` JSON for those PIDs~~ (done 2026-11-03: `tests/fixtures/getpatterns/`, 45 files), one small Mansueto parquet (PID 6410 last-30-day window, under 300 KB, plus one day of route 3 PIDs 18414/18415; plan in `specs/mansueto-adapter.md`).
- [ ] Migrate the durable knowledge-vault notes cited in README/TODO into `docs/` (agents cannot read the vault). Start with: `canonical-data-views`, `cta-bus-tracker-api`, `cta-holiday-schedule-filtering`, `michigan-ave-segment-view`, `mansueto-imputed-stop-times`.

## Phase 1: Routes 8, 65, & 66

Analyze three routes affected by current construction. Build the data ingestion pipeline and compute distributions via scripts and exploratory notebooks — no web app yet. Data access strategy for this phase: local caches of Mansueto parquets and archive day files (ADR-004).

### Now

- [ ] EDA notebook: explore Mansueto parquet data for routes 8, 65, & 66 — verify schema consistency across routes, check data volumes and date ranges, visualize arrival patterns and headways (`notebooks/eda_routes_8_65_66.ipynb`). Expect every file to end 2026-07-28 (ADR-007); the fall-2026 construction period is archive-only.
- [ ] Run-level view for routes 8, 65, & 66 from both adapters (Foundation items above): Mansueto for ~2022 to 2026-07-28, archive from 2026-09-28; the cross-check on overlapping days is deferred until Mansueto's data edge passes 2026-09-28 (ADR-007). Routes 8 and 66 had fall-2026 construction detours (route 8 on Division near Halsted per the cta-bus-speed-scorecard study): record detour dates in `docs/` so they can be flagged.
- [ ] Build the stop-level view for routes 8, 65, & 66 (route → direction → stop_id → arrival-time list) by grouping the run-level view

### Next

Each item gets a spec with acceptance tests on the fixture day before implementation.

- [ ] Wait-time distribution — compute from the stop-level view for (route, direction, start_stop), filter by day_of_week / time_of_day
- [ ] Travel-time distribution — from the run-level view, filter to runs that visited both start_stop and end_stop, compute pairwise deltas
- [ ] Time-series of average travel time by date — group the run-level view's per-run deltas by date, filter to chosen day_of_week
- [ ] Handle direction-only destination (aggregate over all downstream stops in that direction)

## DLSD Express Analysis

Side-quest: Lake Shore Drive express segment timing for all-day routes 146 & 147 (`notebooks/dlsd_travel_time_146_147.ipynb`) and rush-hour-only routes 134, 135, 136, 143, and 148. Comparison plots in `notebooks/dlsd_express_comparison_plots.ipynb`. Active backlog for this side-quest is complete.

## Michigan Ave Bus Lane Analysis

Side-quest: measure current bus speed on the downtown Michigan Avenue corridor (Roosevelt to Delaware) ahead of the new northbound dedicated bus lane (Roosevelt to Wacker). This establishes a before-picture and may inform what to build in later phases. Initial v1 uses candidate routes present in Mansueto `rt_to_pid.csv` (route **10** excluded until refinement below). The corridor stop list is frozen in `notebooks/michigan_ave_stops_snapshot.json` (40 on-avenue stops after side-street exclusions). Vault: `michigan-ave-bus-lane-segment`, `michigan-ave-corridor-stops-snapshot`, `cta-holiday-schedule-filtering`.

### Now

- [ ] Before-picture dataset: run-level view for the kept PIDs over every archive day before the NB lane opens (archive adapter, Foundation), stored as parquet with its QA table. A one-day prototype (2026-10-29) reproduced the Mansueto corridor medians within 1% and resolved a ~20-minute southbound incident north of the river around 10:25 AM.
- [ ] Pattern catalog refresh against the archive: the Oct-3 kept list misses patterns running daily in late October (route **6** PID **7107** to 79th/South Shore, ~100 trips/day; four route **4** PIDs 28326–28329; route **147** PID **839**). Re-run route identification on archive days and update `notebooks/michigan_ave_kept_pids.json`.
- [ ] Segment-view QA — route **151** NB PIDs **14130** and **14132**: `last30d` cache exists but neither PID appears in `data/michigan_ave/segment_view.parquet` (no corridor stop rows). Re-run the segment view on the archive adapter first; if the PIDs appear there, close this as a Mansueto-only caveat, otherwise drop from `notebooks/michigan_ave_kept_pids.json` or fix the filter (vault `michigan-ave-segment-view`).
- [ ] Segment-view QA — sample **137** trips with backwards observed `bus_stop_time` vs latitude `seq_index` (likely ~5 min imputation vs sequence order). Re-run on the archive adapter first; expected to disappear by construction (arrival times are interpolated along monotone `pdist`). Keep as a Mansueto-only QA flag if so (vault `michigan-ave-segment-view`).

### Next
- [ ] Route 10 / Mansueto catalog gap (refinement): confirm route **10** is absent from CloudFront `rt_to_pid.csv` (not a `10.0` string mismatch). If missing, discover PIDs via Bus Tracker (`getpatterns` / route lookup per vault `cta-bus-tracker-api`), add route 10 to Michigan Ave analysis, and document whether Mansueto parquets exist or route 10 is API-only (`notebooks/michigan_ave_stop_discovery.ipynb`; vault `rt-to-pid-missing-parquet`). Route 10 is present in the archive (pattern 29277 seen 2026-10-29). Defer until initial speed plots look reasonable.
- [ ] Holiday schedule filtering: moved to the Foundation calendar module.

## Phase 2: Static web app for all routes

Pick a web-app stack, extend ingestion to all (or most) CTA bus routes, and deploy as a static dataset served on a webpage.

- [ ] Pick the web-app stack (Streamlit vs. Dash vs. FastAPI + React vs. Flask + templates); log the choice as an ADR in DECISIONS.md
- [ ] Extend ingestion to all (or most) routes
- [ ] Frontend flow: route dropdown → start-stop dropdown → destination-stop-or-direction → optional time/day picker (default = "now")
- [ ] Frontend: histogram for wait time, histogram for travel time, line chart for average travel time over time
- [ ] Deployment target (Streamlit Cloud / Fly / Render / Vercel — depends on stack)

## Phase 3: Scheduled refresh and extras

Scheduled data updates, richer metrics, and polish features that go beyond the initial static snapshot.

- [ ] Scheduled refresh: nightly ingest of new archive days (checksum-verified, `known_gaps` recorded). Mansueto backfill is deferred: the bucket has been frozen at 2026-07-28 since at least 2026-11-04 (ADR-007); the refresh job should re-measure `cta.mansueto.data_edge` periodically and raise a flag if it moves (the archive exports nightly)
- [ ] Add derived metrics: excess wait vs. scheduled headway, on-time reliability score. Handle: join GTFS trips on (`sched_start_date`, `sched_start_sec`, `pid` → shape/direction), which the archive carries on every row
- [ ] Community-area rollups (mirror what the Mansueto dashboard does, but interactive)
- [ ] Compare weekday-vs-weekend distributions side by side
- [ ] Persist and share URLs for a chosen route+stop+time combination

## Done

- [x] Split `cta.cta_api` into `cta.bustracker` (API client, daily budget, throttle, `getpatterns` fetch and disk cache, with the former `cta/patterns.py` reader folded in so the cache format has one owner) and `cta.mansueto` (`BASE`, `RT_TO_PID_URL`, `parquet_url`, `parquet_http_status`); clean removal, no shim; every public name kept; importers, notebook import cells, CLAUDE.md and README.md updated (`specs/split-cta-api.md`) (2026-11-04)
- [x] Package + tests + CI (ADR-005): moved `cta_api.py`, `dlsd_run_quality.py`, `michigan_ave_segment.py` from `notebooks/` to `cta/` with every public name unchanged; notebooks, scripts and tests import `cta.<module>`; `pyproject.toml` (`pip install -e .`), `.github/workflows/ci.yml` (pytest, no network), `tests/test_package_layout.py` (`specs/package-migration.md`) (2026-11-04)
- [x] Archive adapter → run-level view (ADR-004): `cta/archive.py`, `cta/patterns.py`, `cta/calendar.py`, `cta/views.py`, `scripts/archive_run_level.py`, fixtures for 2026-10-29 and the 45 kept PIDs; validation tolerance set by ADR-006 (`specs/archive-adapter.md`, `docs/2026-11-03-archive-adapter-qa.md`) (2026-11-03)
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
