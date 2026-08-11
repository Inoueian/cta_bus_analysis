# CTA Bus Wait & Travel Time Explorer

A web app for exploring historical wait-time and travel-time distributions on CTA bus routes, powered by the Mansueto Institute's StopWatch dataset.

## Overview

Riders in Chicago plan trips with almost no visibility into how reliable a given bus route is at a specific time of day. This project turns the CTA Stop Watch historical dataset into an interactive tool: pick a route, a starting stop, a destination (or just a direction), and optionally a time of day and day of week, and the app returns the empirical distribution of wait times and travel times for that combination, plus a chart of how the average travel time has drifted over time on that day of week.

The primary audience is Chicago transit riders and researchers who want a distributional view of service, not just a schedule.

## Principles

- **No unreviewed LLM output reaches users.** Anything a rider sees in the app — especially written explanations — must be reviewed by a human at some point. Computed numerical output is not covered; only LLM-generated or LLM-paraphrased text. See [ADR-002](DECISIONS.md).

## Getting Started

### Prerequisites

- Python 3.11+
- Web-app stack: TBD (see the open item under "Now" in [TODO.md](TODO.md))
- Internet access to reach the CTA Stop Watch CloudFront bucket

### Install

```
# TBD once stack is chosen
```

### Run

```
# TBD once stack is chosen
```

## Project Layout

```
.
├── README.md
├── TODO.md
├── DECISIONS.md
├── .gitignore
└── env/           # local virtualenv (gitignored)
```

Additional directories (`backend/`, `frontend/`, `data/`, `notebooks/`) will be added as the app scaffolding lands.

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
