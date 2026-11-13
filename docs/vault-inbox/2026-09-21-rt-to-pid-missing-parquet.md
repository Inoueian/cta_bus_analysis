---
title: "rt_to_pid.csv lists PIDs with no processed parquet (404)"
category: projects
project: cta-bus-analysis
tags: [rt_to_pid, 404, cloudfront, mansueto, route-65, route-10]
created: 2026-09-21
source: notebooks/eda_routes_8_65_66.ipynb section 3
---

`rt_to_pid.csv` is not an authoritative list of published files — some PIDs map to routes but `trips_<PID>_full.parquet` returns **HTTP 404** on CloudFront.

## Verified (2026-09-21)

Route **65** in CSV includes PIDs **7906**, **7907** — both 404:

```bash
curl -sI "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/processed_by_pid/trips_7906_full.parquet" | head -1
curl -sI "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/processed_by_pid/trips_7907_full.parquet" | head -1
```

Other route 65 PIDs in the same CSV (e.g. **7905**, **3213**, **6652**) return **200**.

## Routes absent from CSV (verified 2026-10-02)

Some candidate routes have **zero rows** in `rt_to_pid.csv` — not the same failure mode as PID-in-CSV → **404**.

| Route | Observation | Michigan Ave v1 |
|---|---|---|
| **10** | `notebooks/michigan_ave_stop_discovery.ipynb` §1 prints `No rows in rt_to_pid.csv for: ['10']` (not a `10.0` string mismatch) | Excluded from Mansueto parquet path; Bus Tracker `getpatterns` only until PIDs resolved — see **`michigan-ave-corridor-stops-snapshot`** |

No `trips_<PID>_full.parquet` URL exists without a PID row. Do not treat as 404-on-probe; discover PID via Bus Tracker or alternate catalog first.

## Ingestion / EDA rule

- Before `pd.read_parquet(URL)`: probe with **HEAD** or handle `HTTPError 404`.
- Union run-level data only over PIDs with status **200** (or cached local copies).
- Log skipped PIDs with route + HTTP status; do not fail the whole pipeline on one missing PID.

## URL pattern

`https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/processed_by_pid/trips_{pid}_full.parquet`

PID list: `{BASE}/rt_to_pid.csv` — see `cta-stop-watch-dataset`.

## Related

- `eda-notebook-routes-8-65-66` — notebook uses `parquet_http_status` / skip rows in volume table
- `parquet-verification-results` — schema on an **existing** PID (6662), not catalog completeness
- `michigan-ave-corridor-stops-snapshot` — route **10** missing from CSV during stop discovery
