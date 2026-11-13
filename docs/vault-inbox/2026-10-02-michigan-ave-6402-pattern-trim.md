---
title: "Michigan Ave — 148 Southbound PID 6402 pattern trim (after Hubbard)"
category: projects
project: cta-bus-analysis
tags: [michigan-ave, 148, getpatterns, 6402, data-quality]
created: 2026-10-02
source: null
---

Hand edit to local Bus Tracker cache so **148 Southbound PID 6402** corridor timing matches published Mansueto trips. See **`michigan-ave-pattern-endpoint-coverage`** for the original Monroe mismatch.

## Edit

File: `data/cta_api_cache/getpatterns_6402.json` (under `data/`, gitignored).

Removed four **scheduled** stops (`typ == "S"`) after Michigan & Hubbard; **waypoints** (`typ == "W"`) left unchanged:

| `stpid` | Stop |
|---|---|
| `1104` | Michigan & South Water |
| `1105` | Michigan & Lake/Randolph |
| `1106` | Michigan & Washington |
| `18396` | Michigan & Monroe |

The 40-stop corridor snapshot and all other `getpatterns` caches are unchanged.

**Durable record:** If this cache file is deleted, `batch_pattern_stops` refills from the live API and restores those four stops.

## Segment after trim

`longest_corridor_run` on the edited pattern:

- **Entry:** `1097` Michigan & Delaware
- **Exit:** `1103` Michigan & Hubbard (Wrigley Bldg.)
- **7** corridor stops

## Timing (last30d parquet)

| Metric | Value |
|---|---|
| `n_trips` | 479 |
| Median Delaware → Hubbard | **7.37** min |
| p25 / p75 | 6.45 / 8.41 min |
| Share &lt; 5 min | ~9.8% |

**6402 added** to `notebooks/michigan_ave_kept_pids.json` (≥5 min rule unchanged). Route 148 is now kept on **6402 Southbound** and **6403 Northbound**.

## Related

- michigan-ave-pattern-endpoint-coverage
- michigan-ave-bus-lane-segment
- processed-parquet-verification-checklist
- mansueto-imputed-stop-times
