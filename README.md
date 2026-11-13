# CTA Bus Wait & Travel Time Explorer

A web app for exploring historical wait-time and travel-time distributions on CTA bus routes, powered by the Mansueto Institute's StopWatch dataset.

## Overview

Riders in Chicago plan trips with almost no visibility into how reliable a given bus route is at a specific time of day. This project turns the CTA Stop Watch historical dataset into an interactive tool: pick a route, a starting stop, a destination (or just a direction), and optionally a time of day and day of week, and the app returns the empirical distribution of wait times and travel times for that combination, plus a chart of how the average travel time has drifted over time on that day of week.

The primary audience is Chicago transit riders and researchers who want a distributional view of service, not just a schedule.

## Roadmap

1. **Phase 1 — Routes 8, 65, & 66.** Build the data ingestion pipeline and compute wait-time and travel-time distributions for three routes affected by current construction, using scripts and exploratory notebooks.
2. **Phase 2 — Static web app for all routes.** Extend ingestion to all (or most) CTA bus routes, pick a web-app stack, and deploy as a static dataset served on a webpage.
3. **Phase 3 — Scheduled refresh and extras.** Add automated data updates from the Transit Alerts archive (Mansueto backfill only if that bucket resumes; see ADR-007), derived metrics (excess wait, reliability scores), community-area rollups, and shareable URLs.

See [TODO.md](TODO.md) for the detailed breakdown of each phase.

**Side quests (notebook-driven):** DLSD express comparison plots are largely complete. Michigan Avenue bus-lane baseline work has finished stop discovery, route identification (**45** kept patterns in `notebooks/michigan_ave_kept_pids.json`), and the segment view (`notebooks/michigan_ave_segment_view.ipynb` → `data/michigan_ave/segment_view.parquet`). Open Michigan work: segment-view QA (route 151 PIDs 14130/14132, backwards-time sampling) and speed plots — see [TODO.md](TODO.md). Both side quests use the same Mansueto data and Bus Tracker helpers as the main pipeline.

## Principles

- **No unreviewed LLM output reaches users.** Anything a rider sees in the app — especially written explanations — must be reviewed by a human at some point. Computed numerical output is not covered; only LLM-generated or LLM-paraphrased text. See [ADR-002](DECISIONS.md).

## Getting Started

### Prerequisites

- Python 3.11+
- Web-app stack: TBD (see **Phase 2** in [TODO.md](TODO.md))
- Internet access to reach the CTA Stop Watch CloudFront bucket
- For notebooks that call the CTA Bus Tracker API: copy `.env.example` to `.env` and set your API key (`.env` is gitignored)

### Install

For exploratory notebooks and tests today (no pinned `requirements.txt` yet):

```
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
pip install -e .   # makes `import cta` work from anywhere (notebooks, scripts)
```

### Run

```
source env/bin/activate
jupyter lab notebooks/
pytest
```

The static web app install and run commands are still TBD until Phase 2 stack is chosen.

## Project Layout

```
.
├── README.md
├── TODO.md
├── DECISIONS.md
├── .env.example   # Bus Tracker API key template (copy to .env)
├── scripts/       # data verification, caching, summaries
│   ├── verify_parquet.py
│   ├── cache_dlsd_parquets.py      # DLSD or Michigan PID parquets (--source michigan)
│   └── dlsd_weekday_friday_summary.py
├── cta/           # importable package (ADR-005): adapters, cleaning, imputation, views
│   ├── bustracker.py               # Bus Tracker API client, daily budget, getpatterns cache (one owner)
│   ├── mansueto.py                 # Mansueto StopWatch CloudFront URL helpers
│   ├── archive.py, calendar.py, views.py  # Transit Alerts archive adapter → run-level view
│   ├── dlsd_run_quality.py         # DLSD rush plot guards and stats
│   └── michigan_ave_segment.py     # Michigan corridor segment + timing helpers
├── notebooks/     # exploratory analysis and side-quest notebooks
│   ├── michigan_ave_route_identification.ipynb
│   ├── michigan_ave_kept_pids.json # patterns with median corridor time ≥ 5 min
│   ├── *_snapshot.json             # frozen stop/boundary lists (e.g. Michigan Ave, DLSD)
│   └── …
├── data/          # local Mansueto parquet and API cache (gitignored)
├── tests/         # pytest unit tests (mocked, no network)
├── .gitignore
└── env/           # local virtualenv (gitignored)
```

Additional directories (`backend/`, `frontend/`) will be added once the web-app stack is chosen.

## Data Source

Historical bus arrival data comes from the Mansueto Institute's StopWatch project. See [github.com/mansueto-institute/cta-stop-watch](https://github.com/mansueto-institute/cta-stop-watch). Its published parquets run from ~2022 to 2026-07-28 and have not been updated since (measured 2026-11-04, [ADR-007](DECISIONS.md), `docs/2026-11-04-mansueto-data-edge.md`). The same bucket's raw 5-minute position CSVs continued to 2026-10-27 and are read through our own imputation as a bounded third source covering 2026-08-13 onward ([ADR-009](DECISIONS.md), `docs/2026-11-06-mansueto-raw-positions.md`). From 2026-09-28 onward, raw ~60-second bus positions come from the Chicago Transit Alerts archive collected by [chicago-transit-insights](https://github.com/cailinpitt/chicago-transit-insights); see [ADR-004](DECISIONS.md). The prior iteration of this project (which read the older Ghost Bus daily-CSV bucket) is preserved on the `legacy` branch.

### Data Model

The app queries two derived views built from both sources (ADR-004):

- **Run-level** — one row per stop-visit within a bus run (route, direction, pattern, stop, arrival time). Used for travel-time and time-series queries.
- **Stop-level** — one row per (stop, route, direction) with the ordered list of arrival timestamps. Used for wait-time queries.

Upstream identifiers from Mansueto (`trip_id`, `pattern_id`, `stop_id`) are preserved as passthrough columns. See [ADR-003](DECISIONS.md).

## Documentation

- [CLAUDE.md](CLAUDE.md) — agent and contributor guide: conventions, rules, how to work from specs
- [specs/](specs/) — one spec per unit of work (`specs/TEMPLATE.md`)
- [TODO.md](TODO.md) — active work and backlog
- [DECISIONS.md](DECISIONS.md) — architecture decision log
- [docs/playbook.md](docs/playbook.md) — tag vocabulary, index of dated `docs/` notes, gotchas and patterns to copy; every note and spec carries a `Tags:` line (`kind:`, `source:`, `stage:`, `topic:`) so `grep -n 'Tags:.*source:mansueto' docs/*.md specs/*.md` finds everything about one source
- Personal **knowledge-vault** project `cta-bus-analysis` — older notes on segment boundaries and dataset quirks, being migrated into `docs/` because agents cannot read the vault ([docs/vault-inbox/](docs/vault-inbox/) lists what is left). Migrated so far: the legacy segment view and its check ([docs/2026-10-02-michigan-ave-legacy-segment-view-check.md](docs/2026-10-02-michigan-ave-legacy-segment-view-check.md)), the Bus Tracker API notes, the Mansueto column mapping and imputation method (index in the playbook). Still vault-only: Michigan bus-lane scope and methodology (`michigan-ave-bus-lane-segment`); **148 SB PID 6402** local pattern hand trim (`michigan-ave-6402-pattern-trim`).
