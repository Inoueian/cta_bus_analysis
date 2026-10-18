# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Analysis toolkit (and future web app) for empirical CTA bus wait-time and travel-time distributions, built on the Mansueto Institute's StopWatch processed parquet data. Currently in Phase 1 (scripts + notebooks for routes 8/65/66) with two notebook-driven side quests (DLSD express timing, Michigan Ave bus-lane baseline). No web-app stack has been chosen yet — don't add `backend/`/`frontend/` or assume a framework. `TODO.md` is the source of truth for status; `DECISIONS.md` holds the ADRs.

## Commands

```
python3 -m venv env && source env/bin/activate
pip install -e ".[dev]"                        # cta_bus package + pytest/jupyterlab (deps in pyproject.toml)

pytest                                         # all tests (mocked, no network)
pytest tests/test_bustracker.py                # one file
pytest tests/test_dlsd.py -k valid             # one test by name
jupyter lab notebooks/

python scripts/verify_parquet.py --route 66 [--pid 6662]        # network: check Mansueto schema
python scripts/cache_dlsd_parquets.py --days 365 [--force]      # network: writes data/mansueto/trips_<PID>_last365d.parquet
python scripts/dlsd_weekday_friday_summary.py --routes rush --cache-variant last365d [--write-md out.md]
```

There is no linter/formatter configured.

## Architecture

- **All shared code is the `cta_bus` package in `src/cta_bus/`**, installed editable. Notebooks, scripts and tests just `import cta_bus...`; never add `sys.path` hacks or copy constants into scripts/notebooks.
  - `paths.py` — `repo_root()`, `DATA_DIR`, `MANSUETO_CACHE_DIR`, `API_CACHE_DIR`, `REFERENCE_DIR`, `PLOT_STYLE`. Paths resolve relative to the source tree, so this relies on the editable install.
  - `mansueto.py` — the single home of the CloudFront `BASE`/`RT_TO_PID_URL`, `PARQUET_COLS`, `parquet_url`, `parquet_http_status` (throttled), and `local_parquet_path` (prefers `data/mansueto/trips_<PID>_<variant>.parquet`, falls back to the URL).
  - `bustracker.py` — Bus Tracker v3 client: throttling, retries, a daily request budget tracked in `data/cta_api_cache/` keyed by America/Chicago date (cap 10,000/day), disk cache for `getpatterns`, and `load_dotenv` for `CTA_API_KEY` from `.env`.
  - `analysis/dlsd.py` — `build_dlsd_runs`, day-slice masks, `valid_rush_plot_cells` / `hour_dlsd_stats` sample-size gating (`MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY = 30`). Put side-quest-specific logic in `analysis/`, and generic Mansueto/Bus Tracker logic in the top-level modules.
- **Data source (ADR-001):** `trips_<PID>_full.parquet` per Pattern ID; `rt_to_pid.csv` maps routes to PIDs (some routes, e.g. 10, are missing from it). Do not build a parallel imputation pipeline. Upstream lag is ~2 weeks.
- **Verified Mansueto columns** (see `EXPECTED_MAPPING` in `scripts/verify_parquet.py`): `unique_trip_vehicle_day` → `run_id`, `rt` → route, `pid`, `stpid` → stop_id, `stop_sequence`, `bus_stop_time` → arrival_time. `direction` is **not** in the parquet and must be joined from GTFS/pattern metadata.
- **Planned derived views (ADR-003):** a run-level view (one row per stop-visit, union of all PIDs for a route) for travel-time queries, and a stop-level view (one row per stop/route/direction with ordered arrival timestamps, `pattern_id` kept per timestamp) for wait-time queries. Preserve upstream IDs as passthrough columns; don't invent new identifiers.
- **Reference snapshots in `reference/`:** `dlsd_boundaries_snapshot.json` (DLSD entry/exit stops per PID; also drives which PIDs `cache_dlsd_parquets.py` downloads) and `michigan_ave_stops_snapshot.json` (40 on-avenue stops Roosevelt→Delaware). They are written by the discovery notebooks (`WRITE_SNAPSHOT` flag); regenerate there rather than hand-editing.
- **Local cache:** `data/` is gitignored (Mansueto parquets + API cache).
- **Plot style:** notebooks call `plt.style.use(PLOT_STYLE)`; use it for new plots.
- `pyproject.toml` sets `pythonpath = ["."]` for pytest so tests can `import scripts.<module>`.

## Conventions

- Tests must not hit the network — mock `pd.read_csv` / `pd.read_parquet` / HTTP calls.
- Notebooks are committed with outputs. When editing notebook code programmatically, round-trip the JSON with `json.dumps(nb, indent=1, ensure_ascii=False) + "\n"` to avoid formatting churn.
- **ADR-002:** no LLM-generated or LLM-paraphrased text may reach app users without human review (computed numbers/plots are exempt).
- `DECISIONS.md` ADRs are append-only, newest at top; never edit past entries — supersede with a new ADR. Log the eventual web-stack choice as an ADR.
- When completing work, update `TODO.md` (move items to Done with a date) and keep README in sync.
- Docs reference a personal "knowledge-vault" (notes like `canonical-data-views`, `cta-bus-tracker-api`); it is not in this repo.
