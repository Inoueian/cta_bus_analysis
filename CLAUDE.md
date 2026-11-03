# CTA Bus Wait & Travel Time Explorer — agent guide

Read this first. It is the contract for any agent (or human) working in this repo.
Project goals are in README.md and do not change here. Backlog is TODO.md. Decisions are DECISIONS.md.

## What this project is

Empirical wait-time and travel-time distributions for CTA bus routes, from historical bus positions,
served to riders as a static web app (Phase 2) with scheduled refresh (Phase 3). Two side quests
(DLSD express, Michigan Ave bus lane) reuse the same pipeline.

## Data sources (see ADR-001, ADR-004)

| Source | What it is | Use it for |
|---|---|---|
| Mansueto StopWatch parquet (`trips_<PID>_full.parquet`) | Imputed stop arrivals from ~5 min pings, history to ~2022, ~2 week lag | Long history, drift over time |
| Transit Alerts position archive (`data.chicagotransitalerts.app/positions/`) | Raw Bus Tracker positions, ~60 s fixes (30 s from 2026-11-01), history from 2026-09-28, nightly | Everything from Oct 2026 on, stop-level imputation, incidents |
| CTA Bus Tracker API `getpatterns` | Stop list per pattern with `pdist` (feet along pattern) | Stop pdist for imputation, direction labels. Cached on disk; 10k calls/day cap |
| GTFS | Schedules | Phase 3 excess-wait / on-time metrics |

Both sources must produce the same **run-level view** (ADR-003). Downstream code never reads a
source-specific schema.

Archive access gotchas: Cloudflare returns 403 to Python's default `urllib` User-Agent. Use `curl`
(as `scripts/transit_archive.py` does) or set a non-default User-Agent. Verify every file's SHA-256
against `index.json` before ingesting.

## Layout

```
cta/            importable package: ingestion adapters, cleaning, imputation, views, QA (tested)
scripts/        CLI entry points (thin; argparse + call into cta/)
notebooks/      exploration and figures only; no logic that anything else imports
specs/          one markdown spec per unit of work (see "Working from specs")
tests/          pytest; synthetic or tiny real fixtures; no network
data/           local caches, gitignored
docs/           durable notes migrated from the knowledge vault (data quirks, thresholds)
```

This is the target layout (ADR-005). Until the Foundation items in TODO.md land, `cta/` and `docs/`
do not exist and the importable helpers are `notebooks/cta_api.py`, `dlsd_run_quality.py` and
`michigan_ave_segment.py`, imported via `sys.path` (see `tests/`). Move them into `cta/` as they are
touched. Do not add new importable code under `notebooks/`.

## Conventions

- Python 3.11+. `pip install -r requirements.txt`. DuckDB for anything over ~1M rows; return pandas
  DataFrames at function boundaries so notebooks stay pandas-native.
- Identifiers (`route`, `pid`, `stpid`, `vehicle_id`) are strings everywhere. Timestamps are tz-aware
  UTC in storage, converted to `America/Chicago` only for bucketing and display.
- Every threshold is a named module constant with a one-line comment giving the evidence
  (e.g. `MAX_BRACKET_GAP_S = 180  # scorecard profiling: longer gaps hide stand-stills`).
- Every new pipeline stage emits a QA table (rows in, rows out, reason counts). Tests assert on it.
- Figures: `notebooks/cta_analysis.mplstyle`; minutes-per-mile on the y axis for corridor speed.
- Holiday / outage exclusions live in one calendar file (`cta/calendar.py`), never inline.

## Commands

```
pytest                      # all tests; must pass before any commit
pytest tests/test_x.py -k y # one test
python scripts/<name>.py -h # every script documents itself
```

## Rules

1. **No unreviewed LLM prose reaches app users** (ADR-002). Numbers computed by our code are fine.
2. Never change a published threshold or exclusion without updating the spec, the QA table and
   DECISIONS.md if it is a decision.
3. Do not download more than one archive day in tests or CI. Fixtures live in `tests/fixtures/`.
4. Do not write to `data/` from tests. Do not commit anything under `data/`.
5. Secrets come from `.env` (gitignored). Never print `CTA_API_KEY`.
6. Mansueto `speed_mph` is a ping-interval speed, not stop-to-stop. Do not compare it with imputed speeds.

## Working from specs

Non-trivial work starts as `specs/<slug>.md` (template: `specs/TEMPLATE.md`). The spec states the
question, inputs, outputs with schemas, thresholds, acceptance tests and what is out of scope.
An agent implementing a spec:

1. Reads the spec and this file. Asks only if the spec is contradictory; otherwise states
   assumptions at the top of its summary.
2. Writes tests from the acceptance section first, then code, then runs `pytest`.
3. Updates TODO.md (move the item to Done with the date) and, if a decision was made, DECISIONS.md.
4. Reports: what changed, QA table, anything the spec got wrong.

Exploratory analysis (figuring out what the data looks like) does not need a spec. It needs a
notebook with a markdown "Findings" cell at the end, and any durable finding copied to `docs/`.
