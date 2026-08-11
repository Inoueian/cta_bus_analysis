# TODO

Last updated: 2026-08-10

Active work and backlog for the CTA Bus Wait & Travel Time Explorer.

## Now

- [ ] Verify actual column names in a real `trips_<PID>_full.parquet` and map them to the run-level view schema in ADR-003
- [ ] Pick the web-app stack (Streamlit vs. Dash vs. FastAPI + React vs. Flask + templates); log the choice as an ADR in DECISIONS.md
- [ ] Decide data-access strategy: cache Mansueto parquet files locally vs. read from CloudFront on demand

## Next

- [ ] Data ingestion: build the run-level view by unioning `trips_<PID>_full.parquet` across all Patterns of each route, normalizing columns per ADR-003
- [ ] Build the stop-level view (route -> direction -> stop_id -> arrival-time list) by grouping the run-level view; this also drives the frontend route/direction/stop dropdowns
- [ ] Backend: wait-time distribution — read from the stop-level view for (route, direction, start_stop), filter by day_of_week / time_of_day
- [ ] Backend: travel-time distribution — read from the run-level view, filter to runs that visited both start_stop and end_stop, compute pairwise deltas
- [ ] Backend: time-series of average travel time by date — group the run-level view's per-run deltas by date, filter to chosen day_of_week
- [ ] Frontend flow: route dropdown -> start-stop dropdown -> destination-stop-or-direction -> optional time/day picker (default = "now")
- [ ] Frontend: histogram for wait time, histogram for travel time, line chart for average travel time over time
- [ ] Handle direction-only destination (aggregate over all downstream stops in that direction)

## Later

- [ ] Deployment target (Streamlit Cloud / Fly / Render / Vercel — depends on stack)
- [ ] Scheduled refresh from the Mansueto bucket (respecting the ~14-day upstream lag documented in the knowledge-vault note `cta-stop-watch-freshness-check`)
- [ ] Add derived metrics: excess wait vs. scheduled headway, on-time reliability score
- [ ] Community-area rollups (mirror what the Mansueto dashboard does, but interactive)
- [ ] Compare weekday-vs-weekend distributions side by side
- [ ] Persist and share URLs for a chosen route+stop+time combination

## Done

- [x] Archive initial iteration onto `legacy` branch (2026-08-10)
