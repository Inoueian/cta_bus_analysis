# Playbook: tags, note index, gotchas and patterns

Living reference for agents planning work in this repo. Dated measurement notes in `docs/` are
immutable records; this file is edited in place. `/finding` owns it: it adds entries, keeps the index
and the tag vocabulary current, and prunes tags that stop being used. Read it at planning time
(`/spec` and `/implement` grep it) and before touching a data source for the first time.

Find things by tag, not by reading top to bottom:

```
grep -n 'Tags:.*source:mansueto' docs/*.md specs/*.md       # everything about one source
grep -n 'Tags:.*kind:gotcha.*stage:clean' docs/playbook.md  # gotchas at one stage
```

## Tag vocabulary

Every `docs/` note and every spec carries one `Tags:` line near its top. Two to five tags; exactly one
`kind:`; the rest from the lists below. A tag not listed here is not a tag: `/finding` adds it to this
list first (and says so in its report) or picks an existing one. Proper nouns (module names, PIDs,
ADR numbers, column names) are already grep-able and are never tags.

| Axis | Values | Meaning |
|---|---|---|
| `kind:` | `measurement`, `gotcha`, `pattern`, `qa`, `spec`, `owner-note` | what the entry is: a dated measurement; a symptom-cause-fix; a to-do-X-copy-Y; an implementation QA record; a spec; a note for the owner rather than an agent |
| `source:` | `archive`, `mansueto`, `bustracker`, `gtfs` | the data source it concerns (CLAUDE.md source table) |
| `stage:` | `fetch`, `clean`, `impute`, `view`, `qa`, `figure` | the pipeline stage it concerns |
| `topic:` | `timezone`, `identifiers`, `dedup`, `fixtures`, `network`, `budget`, `thresholds`, `calendar`, `pattern-catalog`, `qa-table`, `process` | a cross-cutting concept that no module or column name captures |

Pruning rule: a `topic:` used by one entry after a year folds into its nearest neighbour.

## Index of dated notes

One line per note, newest first. `/finding` adds a line when it writes a note.

| Note | Tags | One line |
|---|---|---|
| `2026-11-06-mansueto-raw-positions.md` | `kind:measurement source:mansueto source:archive stage:fetch topic:calendar` | Raw 5-minute position CSVs on the Mansueto bucket cover 2026-08-13 to 2026-10-27 (71 days, 25 overlapping the archive), nothing since; parquets still frozen; schema and one-day profile |
| `2026-11-05-model-routing.md` | `kind:owner-note topic:process` | Which model and effort runs `/spec`, `/implement` and the clerical skills, and where that is enforced |
| `2026-11-04-mansueto-data-edge.md` | `kind:measurement source:mansueto topic:calendar topic:timezone` | Every Mansueto parquet ends 2026-07-28; `bus_stop_time` is naive Chicago wall time; row groups are not time-ordered; corrects the kept-pids window to 2026-06-28..07-28 |
| `2026-11-04-mansueto-adapter-qa.md` | `kind:qa source:mansueto stage:clean stage:view topic:qa-table` | Self-consistency on PID 6410 (ratio 1.0000), QA tables on both fixtures, data facts that corrected the spec, dense stop index |
| `2026-11-03-archive-imputation-prototype.md` | `kind:measurement source:archive stage:impute topic:thresholds` | One-day stop-imputation prototype on the Michigan corridor: the evidence behind ADR-004 and the archive spec's thresholds |
| `2026-11-03-archive-adapter-qa.md` | `kind:qa source:archive stage:impute topic:qa-table topic:calendar` | Fixture, QA table for 2026-10-29, conventions the code fixes (one reason per row, known gaps flag days), validation against Mansueto |

## Gotchas

Each entry: symptom, cause, fix, and where the fix lives. An entry is a fact an agent would otherwise
rediscover the hard way. When a gotcha becomes a code guarantee, keep the entry and point at the guard.

### Archive returns HTTP 403 to Python's default User-Agent
Tags: `kind:gotcha source:archive stage:fetch topic:network`
- Symptom: `urllib` gets 403 from `data.chicagotransitalerts.app`; `curl` works.
- Cause: Cloudflare rejects the default `Python-urllib` User-Agent.
- Fix: fetch with `curl` as `cta.archive.run_curl` does, or set `cta.archive.CURL_USER_AGENT`. Verify every file's SHA-256 against `index.json` before ingesting (`cta.archive.verify_day_file`). CloudFront (Mansueto) accepts the default agent but `cta.mansueto.USER_AGENT` names the client anyway.

### Mansueto `bus_stop_time` is naive Chicago wall time, not UTC
Tags: `kind:gotcha source:mansueto stage:clean topic:timezone`
- Symptom: trips appear six hours off, or a few rows refuse to localize in early November.
- Cause: the column is `timestamp[ns]` without a zone and holds America/Chicago wall time (clock-hour profile in `docs/2026-11-04-mansueto-data-edge.md`). The fall-back hour is ambiguous.
- Fix: `cta.mansueto.to_utc` localizes with `MANSUETO_TZ`; ambiguous rows are dropped and counted as `dst_ambiguous_time` in the `read` stage. Never compare it with archive `vehicle_ts` before conversion.

### Mansueto row groups are not time-ordered
Tags: `kind:gotcha source:mansueto stage:fetch`
- Symptom: a date-range read of `trips_<pid>_full.parquet` is as slow as a full read.
- Cause: the last row group spans 2022 to 2026, so row-group statistics cannot skip I/O.
- Fix: read the whole file once into DuckDB (`cta.mansueto.read_trips`) and filter there; cache locally with `fetch_parquet`, which writes `trips_<pid>_full.meta.json` with the footer `data_edge`.

### Identifiers arrive as `6410.0`
Tags: `kind:gotcha topic:identifiers source:mansueto source:bustracker`
- Symptom: a join on `pid` or `stpid` silently matches nothing.
- Cause: legacy code cast `pid` through float; some catalog and notebook paths still produce `"6410.0"`.
- Fix: identifiers are strings everywhere (CLAUDE.md conventions); coerce through `cta.mansueto._id_str` at the boundary. `pids_for_route("3", …)` is an exact string match, so `"3"` does not match `"30"`.

### `rt_to_pid.csv` is stale and incomplete
Tags: `kind:gotcha source:mansueto topic:pattern-catalog`
- Symptom: a route has no Mansueto PIDs, or a listed PID returns 404.
- Cause: the catalog was last modified 2025-01-16. Route 10 is absent (no `10.0` variant either); route 65 PIDs 7906 and 7907 return 404 on CloudFront; patterns added after January 2025 (route 6 PID 7107, route 4 PIDs 28326–28329, route 147 PID 839) are missing.
- Fix: check `cta.mansueto.parquet_http_status(pid)` before planning on a PID; discover current PIDs from the archive or Bus Tracker `getpatterns`; record archive-only routes in the TODO item (Michigan Ave "Route 10" item).

### Mansueto imputed history stops at 2026-07-28 and never overlaps the archive
Tags: `kind:gotcha source:mansueto source:archive topic:calendar`
- Symptom: a cross-source comparison finds no common service day.
- Cause: the per-pattern parquets have been frozen since 2026-07-28 (`MANSUETO_DATA_EDGE`, ADR-007) and the archive starts 2026-09-28. The same bucket's raw 5-minute position CSVs (`full_day_data/`) do continue, 2026-08-13 to 2026-10-27 with gaps (`docs/2026-11-06-mansueto-raw-positions.md`), but they are positions, not imputed arrivals, and no adapter reads them; 2026-07-28 to 2026-08-12 is covered by nothing.
- Fix: same-source self-consistency is the adapter gate (`MAX_SELF_CONSISTENCY_DEVIATION`); the cross-source test stays skipped until `cta.mansueto.data_edge` moves. Re-measure before assuming the edge changed.

### The kept-PIDs "30-day" medians are a midsummer window
Tags: `kind:gotcha source:mansueto stage:view topic:calendar`
- Symptom: a validation against `notebooks/michigan_ave_kept_pids.json` compares October to July.
- Cause: `scripts/cache_dlsd_parquets.py` keeps the 30 days before `max(bus_stop_time)`, so the window is 2026-06-28 to 2026-07-28, not the cache date.
- Fix: say which window a median comes from; ADR-006's 20% tolerance accounts for the season gap.

### `bracket_gap_s` NaN means unknown, not zero
Tags: `kind:gotcha stage:view source:mansueto topic:thresholds`
- Symptom: a gap filter keeps or drops every Mansueto row.
- Cause: Mansueto publishes no ping times, so `cta.views.run_level_from_mansueto` fills `bracket_gap_s` with NaN; the archive fills it from real fix pairs.
- Fix: filters on `bracket_gap_s` must treat NaN as "not assessable" (pass through, count separately), never as 0.

### Mansueto imputed times can run backwards along a pattern
Tags: `kind:gotcha source:mansueto stage:clean topic:qa-table`
- Symptom: a trip's `bus_stop_time` decreases between consecutive stops.
- Cause: stop times are imputed from ~5-minute pings, so sequence order and time order disagree on short gaps.
- Fix: `cta.mansueto.clean_trips` drops and counts them as `nonmonotone_time` in the `order` stage (0 on the route 3 fixture day). Against pattern order the archive cannot produce them, because arrivals interpolate along monotone `pdist`. Against the Michigan latitude sequence it can, when a pattern's stop order differs from latitude order: route 4 NB PID 25899 loops off Michigan (north to Randolph, east on Randolph, north on Columbus, west on Wacker, back south on Michigan), so it serves Lake/Randolph after South Water, 2 trips on the 2026-10-29 fixture day; the hop into that loop is dropped as `detour_hop` (`specs/michigan-segment-from-view.md`).

### Mansueto `speed_mph` is a ping-interval speed
Tags: `kind:gotcha source:mansueto stage:view topic:thresholds`
- Symptom: Mansueto speeds look faster and smoother than imputed stop-to-stop speeds.
- Cause: it is the speed over the ~5-minute ping interval, not between stops.
- Fix: CLAUDE.md rule 6: never compare it with imputed speeds. Corridor speed is defined on segments between consecutive corridor stops, from run-level arrivals and getpatterns `pdist` (ADR-010, `specs/michigan-segment-from-view.md`); until that lands, the legacy segment view and `notebooks/michigan_ave_speed_plots.ipynb` still plot this ping-interval speed.

### GTFS `arrival_time` runs past 24:00
Tags: `kind:gotcha source:gtfs stage:clean topic:calendar`
- Symptom: schedule rows after midnight fail to parse as clock times, or land on the wrong service day.
- Cause: GTFS stop times are offsets from the service day, so post-midnight trips carry `24:xx` and `25:xx`. Mansueto's pipeline handled only `24:xx` and then filtered to 6am to 8pm (their issue 21).
- Fix: nothing in `cta/` reads GTFS yet; the Phase 3 derived-metrics item (ADR-009) must build the stop time as service date plus a seconds offset, never a clock-time parse.

### Holidays and archive outages are flags, not drops
Tags: `kind:gotcha source:archive stage:clean topic:calendar`
- Symptom: a holiday or an outage day is filtered inline in a notebook.
- Cause: the six Sunday-schedule holidays and the archive `known_gaps` windows are easy to hard-code.
- Fix: `cta.calendar.calendar_flag` labels each service date (`holiday:<name>`, `known_gap_day`); pairs that span a `known_gaps` window are dropped as `spans_known_gap`, the day itself stays. Exclusions live only in `cta/calendar.py`.

### `getpatterns` has a daily budget
Tags: `kind:gotcha source:bustracker stage:fetch topic:budget`
- Symptom: Bus Tracker returns an error after many pattern fetches, or a test tries to go online.
- Cause: 10,000 calls per day (`CTA_API_DAILY_MAX`), one call per pid.
- Fix: `cta.bustracker.batch_pattern_stops` caches each pid's response forever under `data/cta_api_cache/` and counts calls; tests read the committed `tests/fixtures/getpatterns/` only. Never print `CTA_API_KEY`.

## Patterns

Each entry: to do X, copy Y. Point at a file and function; the spec template's "Prior art to copy"
line should be able to quote one of these.

### Add a source adapter that produces the run-level view
Tags: `kind:pattern stage:clean stage:view`
- Copy `specs/mansueto-adapter.md` (shape) and `cta/mansueto.py` (`read_trips`, `clean_trips` with named stages in `STAGES`, reason constants `REASON_*`), then `cta.views.run_level_from_mansueto`. Columns are ADR-003; `stop_sequence_index` is the dense getpatterns `stop_rank` (ADR-008, `cta.bustracker.with_stop_rank`); `source` is a constant per adapter.

### Emit a QA table from a pipeline stage
Tags: `kind:pattern stage:qa topic:qa-table`
- Copy `cta.mansueto.qa_rows` (in-memory) or `cta.archive._record_qa` (DuckDB table): one row per non-zero reason, one `None` row when nothing dropped, additivity asserted. The test copies `tests/test_mansueto.py` (`count.sum() == rows_in - rows_out` per stage). Columns are `QA_COLUMNS` in both modules; a shared helper is a Foundation TODO item.

### Name a threshold
Tags: `kind:pattern topic:thresholds`
- Copy the shape of `cta/archive.py` `MAX_BRACKET_GAP_S`: a module constant, one trailing comment naming the evidence (profiling result, ADR, docs note). It also goes in the spec's thresholds table. Changing a published value is Rule 2: spec, QA table and DECISIONS.md move with it.

### Build a committed fixture from a public file
Tags: `kind:pattern topic:fixtures stage:fetch`
- Copy `scripts/build_archive_fixtures.py` (one archive day, filtered to the kept PIDs, plus an index manifest) or `scripts/build_mansueto_fixtures.py` (parquet cuts, footer sample, `mansueto.manifest.json` with bytes, SHA-256 and rows). One archive day at most (Rule 3); tests never write to `data/` (Rule 4). A `/fixture` skill that generalizes both is a Foundation TODO item.

### Probe a remote parquet without downloading it
Tags: `kind:pattern source:mansueto stage:fetch topic:network`
- Copy `cta.mansueto.data_edge`: `http_head` for size and `Last-Modified`, `parquet_footer` by range request, `footer_summary` for per-row-group statistics. `docs/2026-11-04-mansueto-data-edge.md` shows what it answers.

### Add a CLI entry point
Tags: `kind:pattern topic:process`
- Copy `scripts/archive_run_level.py`: argparse, a module docstring with examples that `-h` prints, every computation in `cta/`, output paths under `data/`. The script is thin enough that its test is the `cta` test.

### Flag a service date instead of filtering it
Tags: `kind:pattern topic:calendar stage:clean`
- Copy `cta.calendar.calendar_flag`: return a label column, let downstream decide. New calendar facts (Mansueto freshness, source-coverage holes) go in `cta/calendar.py`, not in the adapter.

### Record a durable fact
Tags: `kind:pattern topic:process`
- A measurement: `/finding` writes a dated `docs/` note (`docs/2026-11-04-mansueto-data-edge.md` is the shape). A gotcha or a pattern: `/finding` appends here. A choice future work must respect: `/adr`. A step every task follows: the skill file. CLAUDE.md holds only rules an agent acts on.
