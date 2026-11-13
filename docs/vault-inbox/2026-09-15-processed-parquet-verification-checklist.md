---
title: "Verify Mansueto trips_<PID>_full.parquet before ingestion"
category: projects
project: cta-bus-analysis
tags: [parquet, verification, schema, trip-id, column-names, mansueto]
created: 2026-09-15
source: cta_bus_analysis/TODO.md
---

Before hardcoding ingestion or ADR-003 column names, run this checklist on at least one real `trips_<PID>_full.parquet` from CloudFront.

## Target URL

```
https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/processed_by_pid/trips_<PID>_full.parquet
```

Replace `<PID>` with a pattern ID for a route you care about (Mansueto repo README links PID lists by route).

## Prerequisites

- `pandas`, `pyarrow` (parquet engine).
- Network access to CloudFront (no auth).

```python
import pandas as pd

URL = "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/processed_by_pid/trips_<PID>_full.parquet"
df = pd.read_parquet(URL)
```

For large files, use `columns=` or read a row group sample if memory is tight; column/dtype checks still need a representative slice.

## Checklist

### 1. Column names

```python
df.columns.tolist()
```

Reconcile with assumed names in `canonical-data-views` (expected passthrough: `trip_id`, `pattern_id`, `stop_id`; plus route/direction, sequence, arrival time). Map Mansueto names to `run_id` only in our derived views — do not rename in source reads without documenting.

### 2. Trip ID column and nulls

- Identify the trip identifier column (likely `trip_id`; confirm in step 1).
- `df["trip_id"].isna().sum()` — should be 0 or explainable fraction.
- `df["trip_id"].head(10).tolist()` — sanity-check Mansueto `(vehicle, route, pattern, date/time)` style IDs.

If column name differs, update `canonical-data-views` and ingestion mapping; do not guess silently.

### 3. One row per (trip, stop)

```python
dup = df.groupby(["trip_id", "stop_id"]).size()
dup[dup > 1].head()
```

Expect no duplicates (or document Mansueto duplicates and dedupe rule). Per trip, stop count should match pattern length order of magnitude:

```python
df.groupby("trip_id")["stop_id"].nunique().describe()
```

### 4. Date range (empirical coverage for this PID)

Use the actual arrival-time column name from step 1 (assumed `arrival_time`):

```python
df["arrival_time"].min(), df["arrival_time"].max()
```

Record min/max in vault or project docs when verified — processed range may differ from raw HEAD-walk newest day (`cta-stop-watch-freshness-check`).

### 5. Stop coverage gaps

Without GTFS stop count for the pattern, use relative checks:

```python
stops_per_trip = df.groupby("trip_id")["stop_id"].nunique()
stops_per_trip.describe()
```

Optional: join Mansueto/GTFS pattern stop list and compare `nunique(stop_id)` per `trip_id` to expected stop count; quantify share of trips with missing stops. Policy: missing stops do not get fabricated timestamps (`canonical-data-views`).

### 6. dtypes

```python
df.dtypes
```

- `arrival_time` must be datetime64 (not object/string) — if object, parse explicitly and document.
- IDs and sequence indices numeric or string consistently; fix in ingestion if mixed.

## After verification

- Update the "Exact Mansueto column names not yet verified" constraint in `canonical-data-views` with verified names and any renames.
- Close TODO in `cta_bus_analysis/TODO.md`: "Verify actual column names in a real `trips_<PID>_full.parquet`…"
- If trip_id is reliable for grouping stop visits, proceed with run-level / stop-level materialization per ADR-003 without raw pipeline.

## Related

- `canonical-data-views`
- `cta-stop-watch-dataset`
- `raw-vs-processed-pipeline`
