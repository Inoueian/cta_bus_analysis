# Transit Alerts position archive keeps every published day: 52 of 52 bus days listed, days and manifests immutable (measured 2026-11-20)

Tags: `kind:measurement source:archive stage:fetch topic:calendar topic:fixtures`

Measured to settle whether archive days are perishable. TODO.md put the Michigan Ave section ahead of Phase 1
because "every archive day before the northbound lane opens is one that cannot be re-collected". This note
records what the publisher says about retention and what the live manifest shows. It is the evidence for
reordering TODO.md on 2026-11-20 and for the Foundation mirror item. It also bears on the fixture decision in
the Foundation item "Archive adapter reads the v2 manifest".

## Measurement

On 2026-11-20:

- Read the "Use the data" section of `https://chicagotransitalerts.app/subscribe/#use-the-data`. The page is a
  JavaScript app, so `curl` returns an empty shell; it was rendered in headless Chromium.
- Read the data changelog that section links to, `https://chicagotransitalerts.app/data/CHANGELOG.md` (plain
  markdown), entries 2026-10-31 and 2026-11-03.
- Fetched `positions/index.json` and the manifest it points at. Sent HEAD requests to five other paths. No day
  file was downloaded.

The manifest:

| Field | Value |
|---|---|
| Path | `positions/manifests/74385d25be7c5b3a8ce528ef1a2b8052401233eb59454f76e685025822505cd9.json`, 180,919 bytes |
| `generated_at` | 2026-11-19T08:40:02Z |
| `coverage` | first 2026-09-28, latest 2026-11-18, 52 days |
| Bus files | 52, 766.1 MB in total |
| First day, 2026-09-28 | 13,275,510 bytes, 1,056,712 rows, 1,438 polls |
| Latest day, 2026-11-18 | 24,642,750 bytes, 2,166,312 rows, 2,872 polls |
| `known_gaps` | 13 entries |
| `previous_manifest` | `positions/manifests/2f7bfe0fdef3b91a7c5c14ca51f9d2225dcad2557b40cff4465e27f14b1752c8.json` |

The HEAD requests:

| Path | Status | Bytes | Last-Modified (UTC) | Cache-Control |
|---|---|---|---|---|
| `positions/index.json` | 200 | | | `public, max-age=300` |
| previous manifest (`2f7bfe…c8.json`) | 200 | 177,600 | 2026-11-18 08:41 | `public, max-age=31536000, immutable` |
| `positions/bus/2026/09/2026-09-28.1f90c07c….parquet` | 200 | 13,275,510 | 2026-11-03 21:35 | `public, max-age=31536000, immutable` |
| `positions/bus/2026/09/2026-09-28.ndjson.gz` (v1) | 200 | 38,351,377 | 2026-10-31 15:11 | `public, max-age=86400` |
| `positions/bus/2026/10/2026-10-29.ndjson.gz` (v1) | 200 | 39,299,129 | 2026-10-31 15:33 | `public, max-age=86400` |

## What the publisher states

- The subscribe page: "Every CTA bus, CTA train, and Metra position the bots poll, as one file per mode per day
  starting September 28, 2026. A new day appears each night." The manifest "lists every published day". "Pin
  a manifest URL for repeatable analysis." "Everything behind this site is published as open files. No sign-up
  or API key, just reasonable polling."
- Changelog, 2026-10-31: "A new file appears each night for the previous day; published days never change."
- Changelog, 2026-11-03: `index.json` is "a small latest pointer (short cache) to an immutable manifest".
  "Manifests never change; pin one for repeatable analysis." "A correction gets a new path; old ones stay
  available." "Days, fields and rows are unchanged; every existing day is converted." "The `.ndjson.gz` files
  are no longer produced and will be removed later."
- The changelog's header: "If you build on this data, watch this file before pinning to the format."
- Nothing on the page or in the changelog states a retention period or a commitment to keep running. The footer
  reads "Unofficial — not affiliated with, endorsed by, or sponsored by the Chicago Transit Authority or Metra"
  and "Built by Cailin".

## Facts confirmed

- **No day has been removed.** The manifest lists every calendar day from the archive's first, 2026-09-28, to
  2026-11-18: 52 of 52.
- **Days and manifests are immutable and addressed by checksum.** Day parquets and manifests are served
  `immutable` with a one-year max-age. Only the pointer `index.json` is short-lived (300 s). The previous
  manifest is still served, so a pinned manifest keeps resolving.
- **Every pre-v2 day was converted, not dropped.** The 2026-09-28 parquet was written 2026-11-03 21:35 UTC, the
  date of the format change.
- **The v1 NDJSON files still resolve but are going away.** On 2026-11-20, 2026-10-29 is still served at
  39,299,129 bytes, the size recorded in `tests/fixtures/archive_2026-10-29_michigan.index.json` `source_day`.
  The v1 index that listed them is already gone, because `index.json` is now the v2 pointer.
- **The risk is the project stopping, not pruning.** The terms promise that published days do not change and
  that corrected paths stay available. They do not promise the site will keep running: it is an unofficial
  project with one named builder. The Mansueto bucket stopped the same way (ADR-007, ADR-009).
- **A full local copy is small.** 52 bus days are 766.1 MB. A day at 30 s polling is about 25 MB (2026-11-18:
  24.6 MB), about 9 GB a year at that rate.

Consequences:

- The days before the Michigan Ave northbound lane opens stay published after it opens. They do not have to be
  processed first.
- `tests/fixtures/archive_2026-10-29_michigan.ndjson.gz` stays valid, because it is committed with its own
  hash. It cannot be rebuilt from its source: `scripts/build_archive_fixtures.py` reads the v1 index, which is
  gone, and the file named in its `source_day.path` will be removed. The same 1,083,422 rows exist as the
  2026-10-29 parquet (`docs/2026-11-13-routes-8-65-66-eda.md`).

## Corrections to earlier notes

- TODO.md, Michigan Ave section intro until 2026-11-20: "every archive day before the northbound lane opens is
  one that cannot be re-collected". The archive keeps every published day. What is bounded is the before window
  itself, not how long its days stay available. Reworded in the same change.
- `docs/playbook.md` gotcha "Archive `index.json` has no `days` key" dated the v2 format "since at least
  2026-11-13". The changelog dates it 2026-11-03. Sharpened in the same change.

## How to re-check

```
BASE=https://data.chicagotransitalerts.app
MANIFEST=$(curl -s $BASE/positions/index.json | jq -r .path)
curl -s $BASE/$MANIFEST | jq '.coverage, (.days | length), ([.days[].files.bus.bytes] | add)'
curl -sI $BASE/positions/bus/2026/10/2026-10-29.ndjson.gz | head -1
curl -s https://chicagotransitalerts.app/data/CHANGELOG.md | sed -n '1,60p'
```

Check three things:

- `coverage.first` is still 2026-09-28, and `days | length` still equals the calendar days from first to
  latest. If either moved, the archive has started dropping days: mirror what is left (Foundation item) and
  record it with `/finding`.
- A 404 on the NDJSON path means the v1 files are gone, which this note expects.
- A new changelog entry on positions may change the format. Read it before touching `cta.archive`.
