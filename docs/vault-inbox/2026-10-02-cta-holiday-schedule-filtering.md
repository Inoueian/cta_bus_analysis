---
title: "CTA holiday dates — exclude from weekday/weekend day slices"
category: projects
project: cta-bus-analysis
tags: [holiday, day-of-week, filtering, weekday, weekend, schedule]
created: 2026-10-02
source: null
---

**Do not** treat every Mon–Fri calendar date as a regular weekday for Mansueto aggregates; CTA runs **holiday / Sunday-style** service on some weekdays.

## Current behavior (gap)

- DLSD notebooks: `day_slice_mask` / slices **`weekday`** (Mon–Thu), **`friday`**, **`weekend`** (Sat–Sun), **`mon_fri`** — **no holiday exclusion**.
- Michigan Ave bus-lane work should not repeat this assumption.

## Required work

- Define a **holiday date set** per analysis window:
  - Minimum: **US federal holidays** falling on Mon–Fri in the cache date range.
  - Prefer: **CTA-published holiday schedule** if a stable source exists (verify against service anomalies in data).
- When building day slices:
  - **Exclude** holiday dates from Mon–Thu / Friday / Mon–Fri weekday buckets.
  - Decide whether holidays belong in **weekend** slice or a separate **holiday** bucket (document choice in notebook + vault).
- **Retrofit**: re-run or document bias in existing DLSD comparison plots (`dlsd_express_comparison_plots.ipynb`, `dlsd_run_quality.py` `day_slice_mask`).

## Implementation hints

- Join `bus_stop_time` → `date` → `is_holiday` before `day_slice_mask`.
- Store holiday list as repo artifact (e.g. `data/cta_holidays.csv` or JSON) with source URL and year range.

## Related

- michigan-ave-bus-lane-segment
- dlsd-express-comparison-plots (repo: `notebooks/dlsd_express_comparison_plots.ipynb`)
- dlsd-run-quality (repo: `notebooks/dlsd_run_quality.py`)
