---
title: "CTA Bus Tracker API v3 for pattern stops and direction"
category: projects
project: cta-bus-analysis
tags: [cta, bus-tracker, getpatterns, getstops, api-v3, cta_api_key, rtdir]
created: 2026-09-23
source: notebooks/lsd_travel_time_146_147.ipynb
---

Base URL for this repo: `http://www.ctabustracker.com/bustime/api/v3/` (notebook `CTA_API_BASE`). Auth: query param `key=` from env `CTA_API_KEY` in repo-root `.env` (gitignored); template in `.env.example`.

## Endpoints used

- `getpatterns?pid={PID}&key=...&format=json` — one PID per request in practice; returns `ptr[]` with `pid`, `rtdir`, `pt[]` (`typ` `S` stop / `W` waypoint; stops have `stpid`, `stpnm`, `lat`, `lon`, `pdist`).
- `getstops?rt={route}&dir={rtdir}&key=...&format=json` — all stops for route+direction: `stpid`, `stpnm`, `lat`, `lon`.

## Live API vs Mansueto PIDs

- `getpatterns` with comma-delimited PIDs (max 10) fails entire batch if **any** PID is unknown to live Bus Tracker (`No data found for parameter`).
- Mansueto historical PIDs may exist in CloudFront parquets but not in live API — call **one PID at a time**, catch `RuntimeError`, skip and log (see `batch_pattern_stops` in LSD notebook).

## Fills Mansueto gap

- Mansueto parquet has no `direction`; `rtdir` from `getpatterns` maps to ADR-003 run-level `direction` (see `canonical-data-views`).

## Daily request cap and repo throttling

- Bus Tracker docs: default **10,000 requests per API key**; higher caps are described as **daily** limits (request a raise if needed).
- Shared module: `notebooks/cta_api.py` — all live calls via `cta_api_get`.
- **Daily counter**: `data/cta_api_cache/request_log.json`, Chicago local date; warn at **9,500**, raise at **10,000** unless `allow_over_budget=True`.
- **Burst spacing**: `CTA_API_MIN_INTERVAL_SEC` (default 0.25 s) between live calls.
- **`getpatterns` disk cache**: `data/cta_api_cache/getpatterns_{pid}.json`; cache hits do not increment daily counter. `batch_pattern_stops(..., use_cache=True)` default.
- **Retries**: HTTP 429/503 and rate-limit-like API errors — exponential backoff (3 attempts).
- **CloudFront** Mansueto HEAD: `parquet_http_status` uses `CLOUDFRONT_MIN_INTERVAL_SEC` (0.1 s), not the Bus Tracker daily cap.

## Related

- `canonical-data-views`
- `cta-stop-watch-dataset`
- `lsd-express-segment-boundaries`
