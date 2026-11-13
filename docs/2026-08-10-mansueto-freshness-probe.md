# Mansueto bucket freshness probe: newest raw day 2026-07-27 on 2026-08-10 (measured 2026-08-10)

Tags: `kind:measurement source:mansueto stage:fetch topic:calendar`

Migrated 2026-11-13 from vault `cta-stop-watch-freshness-check` (2026-08-10), the note ADR-001 cites for
"freshness must be probed manually". It is the earliest dated observation of the Mansueto stall, and it
agrees with the lower edge of the hole that later notes found. Nothing was probed for the migration.

## Measurement

The bucket publishes no manifest, so existence was probed with HEAD requests, newest day first, over the
previous three weeks:

```bash
for d in $(seq 0 21); do
  day=$(date -d "$d days ago" +%Y-%m-%d)   # macOS: date -j -v-${d}d +%Y-%m-%d
  code=$(curl -sI -o /dev/null -w "%{http_code}" \
    "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/full_day_data/${day}.csv")
  echo "$day $code"
done
```

| Probed on | `full_day_data/2026-07-27.csv` | `full_day_data/2026-07-28.csv` |
|---|---|---|
| 2026-08-10 | 200 | 404 |

## Facts confirmed

- The first 200 in the walk is the newest raw day. Yesterday's file cannot be assumed to exist.
- Other signals the vault note lists: the parquet's `Last-Modified` header
  (`processed_by_pid/trips_<PID>_full.parquet`), the Actions runs of Mansueto's `cta-stop-watch`
  repository on GitHub, and the "as of" date on their dashboard (`ctastopwatch.miurban-dashboards.org`).

## Corrections

- The vault note read the result as "raw pipeline lag about 14 days". It was a stall, not a lag: the
  parquets were last regenerated on 2026-07-28 (`docs/2026-11-04-mansueto-data-edge.md`, ADR-007), raw
  day files resume on 2026-08-13 and stop again after 2026-10-27
  (`docs/2026-11-06-mansueto-raw-positions.md`, ADR-009). The 404 for 2026-07-28 seen here is the start
  of the 2026-07-28 to 2026-08-12 hole that `cta.calendar.source_coverage` declares.
- The vault note cited `cta-stop-watch-dataset`, which is not in the repo.

## How to re-check

Without the network: `cta.calendar.source_freshness()` reads the download metadata and says `moved` or
`not_moved`. With it: `cta.mansueto.data_edge(pid)` for a parquet, `cta.mansueto.http_head(url)` or the
loop above for day files. If anything moved past `MANSUETO_DATA_EDGE` or `MANSUETO_RAW_EDGE`, reopen
ADR-007 / ADR-009; the constants change only through Rule 2.
