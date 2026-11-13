# Bus Tracker API v3: `getpatterns` and `getstops` response shapes, 10,000 calls a day (recorded 2026-09-23)

Tags: `kind:measurement source:bustracker stage:fetch topic:budget topic:pattern-catalog`

Migrated 2026-11-13 from vault `cta-bus-tracker-api` (2026-09-23, written from the DLSD notebook now
named `notebooks/dlsd_travel_time_146_147.ipynb`). It records what the two endpoints return and how the
client rations calls. The limits and the batch failure are also playbook gotchas, which is where an agent
should look first. Nothing was called for the migration.

## Measurement

Live calls from the DLSD notebook with a key from `.env` (`CTA_API_KEY`, never printed; template in
`.env.example`). Base URL `cta.bustracker.CTA_API_BASE`; every call goes through
`cta.bustracker.cta_api_get` with `format=json`.

| Endpoint | Parameters | Returns |
|---|---|---|
| `getpatterns` | `pid` | `ptr[]`, each with `pid`, `rtdir` and `pt[]`. A point has `typ` (`S` stop, `W` waypoint), `seq`, `lat`, `lon`, `pdist` (feet along the pattern); stops also have `stpid` and `stpnm` |
| `getstops` | `rt`, `dir` (an `rtdir` value) | every stop for the route and direction: `stpid`, `stpnm`, `lat`, `lon` |

| Limit | Value | Where |
|---|---|---|
| Daily cap per key | 10,000 by default (Bus Tracker documentation; a raise can be requested) | `CTA_API_DAILY_MAX` |
| Warning threshold | 9,500 | `CTA_API_DAILY_WARN` |
| Spacing between live calls | 0.25 s | `CTA_API_MIN_INTERVAL_SEC` |
| Retries | 3, exponential backoff, on HTTP 429 / 503 and rate-limit-like API errors | `CTA_API_MAX_RETRIES`, `CTA_API_RETRY_BASE_SEC` |
| PIDs per `getpatterns` call | 10 accepted by the API; the client sends 1 | `batch_pattern_stops` |

## Facts confirmed

- `getpatterns` with a comma-delimited list fails the whole call (`No data found for parameter`) if any
  one pid is unknown to the live API. Mansueto has parquets for historical pids the live API no longer
  knows, so the client calls one pid at a time, catches the `RuntimeError`, skips the pid and prints the
  skipped list.
- `rtdir` from `getpatterns` is the only source of direction for Mansueto rows; the parquet has none
  (`docs/2026-08-10-mansueto-parquet-column-mapping.md`). It becomes the run-level `direction`.
- The daily counter is `data/cta_api_cache/request_log.json`, keyed by the America/Chicago date. It
  raises at the cap unless `allow_over_budget=True`.
- `getpatterns` responses are cached as `data/cta_api_cache/getpatterns_<pid>.json`; a cache hit does
  not count against the day.
- CloudFront requests for Mansueto files are a separate budget: `cta.mansueto.parquet_http_status`
  spaces them by `CLOUDFRONT_MIN_INTERVAL_SEC` (0.1 s) and they never touch the Bus Tracker counter.

## Corrections

- The vault note names the shared module `notebooks/cta_api.py`. It is `cta/bustracker.py` since
  `specs/split-cta-api.md`; the CloudFront helpers moved to `cta/mansueto.py`.
- The vault note gives the base URL with `http://`; the code uses `https://`.
- `getstops` is used only by `notebooks/dlsd_travel_time_146_147.ipynb`. Nothing in `cta/` wraps it.
- The vault note cited `cta-stop-watch-dataset`, which is not in the repo and not on the inbox list.

## How to re-check

`cta.bustracker.daily_api_request_count()` reads today's count without a call. One live
`batch_pattern_stops([pid], use_cache=False)` on a known pid confirms the response shape and costs one
call; compare with a file under `tests/fixtures/getpatterns/`. If the documented cap changes, the two
constants and the "`getpatterns` has a daily budget" gotcha move together.
