# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Analysis toolkit (and future web app) for empirical CTA bus wait-time and travel-time distributions, built on the Mansueto Institute's StopWatch processed parquet data. Currently in Phase 1 (scripts + notebooks for routes 8/65/66) with two notebook-driven side quests (DLSD express timing, Michigan Ave bus-lane baseline). No web-app stack has been chosen yet — don't add `backend/`/`frontend/` or assume a framework. `TODO.md` is the source of truth for status; `DECISIONS.md` holds the ADRs.

## Commands

No pinned requirements file yet:

```
python3 -m venv env && source env/bin/activate
pip install pandas numpy pytest jupyterlab matplotlib python-dotenv pyarrow
```

```
pytest                                         # all tests (mocked, no network)
pytest tests/test_cta_api.py                   # one file
pytest tests/test_dlsd_run_quality.py -k valid # one test by name
jupyter lab notebooks/

python scripts/verify_parquet.py --route 66 [--pid 6662]        # network: check Mansueto schema
python scripts/cache_dlsd_parquets.py --days 365 [--force]      # network: writes data/mansueto/trips_<PID>_last365d.parquet
python scripts/dlsd_weekday_friday_summary.py --routes rush --cache-variant last365d [--write-md out.md]
```

There is no linter/formatter configured.

## Architecture

- **Data source (ADR-001):** `https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/processed_by_pid/trips_<PID>_full.parquet`, one file per Pattern ID; `rt_to_pid.csv` in the same bucket maps routes to PIDs (some routes, e.g. 10, are missing from it). Do not build a parallel imputation pipeline. Upstream lag is ~2 weeks.
- **Verified Mansueto columns** (see `EXPECTED_MAPPING` in `scripts/verify_parquet.py`): `unique_trip_vehicle_day` → `run_id`, `rt` → route, `pid`, `stpid` → stop_id, `stop_sequence`, `bus_stop_time` → arrival_time. `direction` is **not** in the parquet and must be joined from GTFS/pattern metadata.
- **Planned derived views (ADR-003):** a run-level view (one row per stop-visit, union of all PIDs for a route) for travel-time queries, and a stop-level view (one row per stop/route/direction with ordered arrival timestamps, `pattern_id` kept per timestamp) for wait-time queries. Preserve upstream IDs as passthrough columns; don't invent new identifiers.
- **Shared modules live in `notebooks/`, not a package.** `notebooks/cta_api.py` (Bus Tracker v3 client with throttling, retries, a daily request budget tracked in `data/cta_api_cache/` keyed by America/Chicago date — cap 10,000/day — plus a disk cache for `getpatterns`; also Mansueto URL helpers) and `notebooks/dlsd_run_quality.py` (`build_dlsd_runs`, day-slice masks, `valid_rush_plot_cells` / `hour_dlsd_stats` sample-size gating with `MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY = 30`). Notebooks, scripts, and tests import them by inserting `notebooks/` into `sys.path`; `dlsd_run_quality` itself does `from cta_api import ...`. `tests/conftest.py` puts the repo root on `sys.path` so tests can `import scripts.<module>`.
- **Frozen snapshots:** `notebooks/dlsd_boundaries_snapshot.json` (DLSD entry/exit stops per PID; also drives which PIDs `cache_dlsd_parquets.py` downloads) and `notebooks/michigan_ave_stops_snapshot.json` (40 on-avenue stops Roosevelt→Delaware). These are outputs of the discovery notebooks — regenerate via those notebooks rather than hand-editing.
- **Local cache:** `data/` is gitignored. `local_parquet_path(pid, cache_variant=...)` prefers `data/mansueto/trips_<PID>_<variant>.parquet` and falls back to the CloudFront URL.
- **Plot style:** notebooks load `notebooks/cta_analysis.mplstyle`; use it for new plots.
- **Secrets:** `CTA_API_KEY` (and `CHICAGO_DATA_PORTAL_APP_TOKEN`) come from `.env` (template in `.env.example`), loaded by `cta_api.load_dotenv`.

## Conventions

- Tests must not hit the network — mock `pd.read_csv` / `pd.read_parquet` / HTTP calls.
- **ADR-002:** no LLM-generated or LLM-paraphrased text may reach app users without human review (computed numbers/plots are exempt).
- `DECISIONS.md` ADRs are append-only, newest at top; never edit past entries — supersede with a new ADR. Log the eventual web-stack choice as an ADR.
- When completing work, update `TODO.md` (move items to Done with a date) and keep README in sync, as recent commits do.
- Docs reference a personal "knowledge-vault" (notes like `canonical-data-views`, `cta-bus-tracker-api`); it is not in this repo.
