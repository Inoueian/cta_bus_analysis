# CLAUDE.md

Guidelines for working in this repo. Bias toward caution over speed; for trivial tasks, use judgment. The behavioral sections are adapted from multica-ai/andrej-karpathy-skills.

## Project

CTA Bus Wait & Travel Time Explorer: wait-time and travel-time distributions for CTA bus routes, built on the Mansueto Institute's StopWatch parquet data. Currently Phase 1 (routes 8, 65, 66, via scripts and notebooks) plus two side quests (DLSD express timing, Michigan Ave bus-lane baseline). Phase 2 is a static web app; the stack is not chosen yet.

Read before planning: `README.md` (overview, data model), `TODO.md` (active work), `DECISIONS.md` (ADRs).

## 1. Think Before Coding

- State assumptions. If uncertain, ask.
- If multiple interpretations exist, present them; don't pick silently.
- If a simpler approach exists, say so and push back when warranted.
- If something is unclear, stop, name what's confusing, and ask.

## 2. Simplicity First

- Minimum code that solves the problem. No speculative features, abstractions for single-use code, or unrequested configurability.
- Data-validity guards are not speculative here. Mansueto data has real quirks (missing routes, non-consecutive stop sequences, implausible durations); keep checks like `analysis_ok`.
- In exploratory notebook cells, move fast; apply the strict rules to code in `notebooks/*.py` and `scripts/`.

## 3. Surgical Changes

- Touch only what the request needs. Match existing style.
- Don't refactor or reformat adjacent code. If you notice unrelated problems or dead code, mention them; don't fix them.
- Remove imports/variables that YOUR change made unused, nothing else.
- Every changed line should trace to the request.

## 4. Goal-Driven Execution

- Turn tasks into verifiable goals, then loop until verified.
- Logic in `notebooks/*.py` and `scripts/`: write or update a pytest test first (bug fix = a test that reproduces it).
- Notebook results: verify with numbers (row counts, date ranges, sanity checks), not just "it ran".
- For multi-step tasks, state a short plan with a check per step.

## Commands

    python3 -m venv env && source env/bin/activate
    pip install pandas numpy pyarrow pytest jupyterlab matplotlib python-dotenv
    pytest                      # mocked unit tests, no network
    jupyter lab notebooks/
    python scripts/<name>.py    # run from the repo root

`notebooks/cta_api.py` and `notebooks/dlsd_run_quality.py` are shared helpers imported via `sys.path` (scripts) and `tests/conftest.py` (tests).

## Data

- Source: Mansueto `trips_<PID>_full.parquet` on CloudFront (about a 14-day lag). Don't build a parallel imputation pipeline (ADR-001).
- Column mapping: `unique_trip_vehicle_day` -> `run_id`, `bus_stop_time` -> `arrival_time`, `stpid` -> `stop_id`, `stop_sequence` -> `stop_sequence_index`. `direction` is not in the parquet.
- Two canonical views, run-level and stop-level (ADR-003). Keep `trip_id`, `pattern_id`, `stop_id` as passthrough columns.
- Local parquet cache is in `data/` (gitignored). Never commit it. Cache variants: `last30d`, `last365d`.
- `*_snapshot.json` files in `notebooks/` are frozen on purpose. Don't regenerate them without being asked.

## Analysis conventions

- "weekday" means Mon-Thu; Friday is its own slice; weekend is Sat-Sun (`day_slice_mask`).
- Filter DLSD runs on `analysis_ok`. Rush-hour cells need at least 30 weekday runs (`MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY`).
- Holidays are not filtered yet (open item in `TODO.md`).
- Plots use `notebooks/cta_analysis.mplstyle`.

## Bus Tracker API

- Key is `CTA_API_KEY` in `.env` (gitignored). Never print, log, or commit it.
- Daily cap is 10,000 requests. Go through `cta_api_get` / `batch_pattern_stops` and prefer the disk cache.
- Tests never call the live API.

## Docs

- ADRs in `DECISIONS.md` are append-only, newest first. To reverse one, add a new ADR and mark the old one superseded. Log the Phase 2 stack choice as an ADR.
- ADR-002: no unreviewed LLM-written text reaches app users.
- When finishing work, update `TODO.md` (move items to Done, bump "Last updated").
- The README mentions a personal knowledge-vault; it isn't available in cloud sessions, so put durable facts in the repo.
