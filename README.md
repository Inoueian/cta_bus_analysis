# CTA Bus Wait & Travel Time Explorer

A web app for exploring historical wait-time and travel-time distributions on CTA bus routes, powered by the Mansueto Institute's StopWatch dataset.

## Overview

Riders in Chicago plan trips with almost no visibility into how reliable a given bus route is at a specific time of day. This project turns the CTA Stop Watch historical dataset into an interactive tool: pick a route, a starting stop, a destination (or just a direction), and optionally a time of day and day of week, and the app returns the empirical distribution of wait times and travel times for that combination, plus a chart of how the average travel time has drifted over time on that day of week.

The primary audience is Chicago transit riders and researchers who want a distributional view of service, not just a schedule.

## Roadmap

1. **Phase 1 — Routes 8, 65, & 66.** Build the data ingestion pipeline and compute wait-time and travel-time distributions for three routes affected by current construction, using scripts and exploratory notebooks.
2. **Phase 2 — Static web app for all routes.** Extend ingestion to all (or most) CTA bus routes, pick a web-app stack, and deploy as a static dataset served on a webpage.
3. **Phase 3 — Scheduled refresh and extras.** Add automated data updates from the Mansueto bucket, derived metrics (excess wait, reliability scores), community-area rollups, and shareable URLs.

See [TODO.md](TODO.md) for the detailed breakdown of each phase.

**Side quests (notebook-driven):** DLSD express timing and Michigan Avenue bus-lane baseline analysis are in progress alongside Phase 1. They use the same Mansueto data and Bus Tracker helpers as the main pipeline; see [TODO.md](TODO.md) for status.

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
pip install pandas numpy pytest jupyterlab matplotlib python-dotenv
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
│   ├── cache_dlsd_parquets.py
│   └── dlsd_weekday_friday_summary.py
├── notebooks/     # exploratory analysis and side-quest notebooks
│   ├── cta_api.py                  # shared Bus Tracker + Mansueto URL helpers
│   ├── dlsd_run_quality.py         # DLSD rush plot guards and stats
│   ├── *_snapshot.json             # frozen stop/boundary lists (e.g. Michigan Ave, DLSD)
│   └── …
├── data/          # local Mansueto parquet and API cache (gitignored)
├── tests/         # pytest unit tests (mocked, no network)
├── .gitignore
└── env/           # local virtualenv (gitignored)
```

Additional directories (`backend/`, `frontend/`) will be added once the web-app stack is chosen.

## Data Source

Historical bus arrival data comes from the Mansueto Institute's StopWatch project. See [github.com/mansueto-institute/cta-stop-watch](https://github.com/mansueto-institute/cta-stop-watch). The prior iteration of this project (which read the older Ghost Bus daily-CSV bucket) is preserved on the `legacy` branch.

### Data Model

The app queries two derived views built from the Mansueto data:

- **Run-level** — one row per stop-visit within a bus run (route, direction, pattern, stop, arrival time). Used for travel-time and time-series queries.
- **Stop-level** — one row per (stop, route, direction) with the ordered list of arrival timestamps. Used for wait-time queries.

Upstream identifiers from Mansueto (`trip_id`, `pattern_id`, `stop_id`) are preserved as passthrough columns. See [ADR-003](DECISIONS.md).

## Documentation

- [TODO.md](TODO.md) — active work and backlog
- [DECISIONS.md](DECISIONS.md) — architecture decision log
- Personal **knowledge-vault** project `cta-bus-analysis` — durable notes on API limits, segment boundaries, and dataset quirks (complements these repo docs)
