---
title: "Check CTA Stop Watch data freshness"
category: projects
project: cta-bus-analysis
tags: [cta, bus, stop-watch, freshness, curl, head]
created: 2026-08-10
source: https://github.com/mansueto-institute/cta-stop-watch
---

No manifest is published for the Mansueto CTA Stop Watch bucket. Probe file existence directly with HEAD.

## HEAD-walk daily CSVs (fastest check)

```bash
for d in $(seq 0 21); do
  day=$(date -j -v-${d}d +%Y-%m-%d)
  code=$(curl -sI -o /dev/null -w "%{http_code}" \
    "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/full_day_data/${day}.csv")
  echo "$day $code"
done
```

First `200` = newest raw day available. `date -j -v-Nd` is BSD/macOS syntax (Linux: `date -d "N days ago" +%Y-%m-%d`).

## Observed lag

As of 2026-08-10:
- `2026-07-27.csv` -> 200
- `2026-07-28.csv` -> 404

Raw pipeline lag ~14 days. Do not assume yesterday's data exists.

## Other freshness signals

- Processed parquet mtime:
  `curl -sI "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/processed_by_pid/trips_<PID>_full.parquet" | grep -i last-modified`
- Repo Actions runs (green = data refreshed that day): https://github.com/mansueto-institute/cta-stop-watch/actions
- Live dashboard shows an "as of" date: https://ctastopwatch.miurban-dashboards.org

## Related

- cta-stop-watch-dataset
