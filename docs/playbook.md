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
| `2026-10-02-michigan-ave-corridor-stops.md` | `kind:measurement source:bustracker stage:clean topic:pattern-catalog` | Migrated from the vault: how the 40-stop corridor snapshot was built (name and latitude filter, 51 stops, 11 excluded by id), the exclusion list the JSON does not hold, the stale `roosevelt_stpids` |
| `2026-10-02-michigan-ave-corridor-scope.md` | `kind:measurement source:bustracker source:mansueto topic:thresholds topic:pattern-catalog` | Migrated from the vault: Michigan Ave baseline scope (Roosevelt to Delaware, anchor stops, 19 candidate routes, 45 patterns kept at a 5-minute median) and what ADR-010 changed |
| `2026-10-02-michigan-ave-6402-pattern-trim.md` | `kind:measurement source:bustracker source:mansueto topic:pattern-catalog topic:fixtures` | Migrated from the vault: four stops after Hubbard hand-removed from the cached pattern of PID 6402 (148 SB), median 7.37 min on 479 trips; the trim is local only and the committed fixture is untrimmed |
| `2026-09-24-dlsd-rush-hour-min-sample.md` | `kind:measurement source:mansueto stage:figure topic:thresholds` | Migrated from the vault: evidence for the 30-run Mon to Thu gate on DLSD rush plots (weekday median 62 runs per cell, Friday 12) and how each day slice uses the one gate |
| `2026-09-24-dlsd-rush-express-routes.md` | `kind:measurement source:bustracker stage:figure topic:pattern-catalog` | Migrated from the vault: DLSD entry and exit stops for routes 134, 135, 136, 143, 148 (11 PIDs), the expected geography, and the 13x against 14x comparison panes |
| `2026-09-23-dlsd-segment-boundaries-146-147.md` | `kind:measurement source:bustracker stage:clean topic:thresholds topic:pattern-catalog` | Migrated from the vault: the DLSD segment is the one pattern hop over 10,000 ft; entry and exit stops for routes 146 and 147 (18 PIDs); PID 839 has no DLSD hop |
| `2026-08-10-mansueto-freshness-probe.md` | `kind:measurement source:mansueto stage:fetch topic:calendar` | Migrated from the vault: HEAD walk of the raw day files on 2026-08-10 (2026-07-27 present, 2026-07-28 missing), the earliest sighting of the stall; other freshness signals |
| `2026-10-02-michigan-ave-legacy-segment-view-check.md` | `kind:qa source:mansueto stage:view topic:qa-table` | Migrated from the vault: what the deprecated `build_michigan_segment_view` does and its 2026-10-03 check (461,215 rows, 37,651 trips, 43 of 45 PIDs, 137 backwards trips); corrects 14130/14132 to route 157 |
| `2026-09-23-mansueto-imputation-method.md` | `kind:measurement source:mansueto stage:impute topic:thresholds` | Migrated from the vault: Mansueto interpolates stop times linearly in distance between ~5-minute pings, extrapolates trip ends, clamps `speed_mph` to [1, 115] and fills; the DLSD `analysis_ok` filter |
| `2026-09-23-bustracker-api-endpoints.md` | `kind:measurement source:bustracker stage:fetch topic:budget topic:pattern-catalog` | Migrated from the vault: `getpatterns` and `getstops` response shapes, the 10,000-a-day cap and how `cta.bustracker` rations it, the batch that fails on one unknown pid |
| `2026-08-10-mansueto-parquet-column-mapping.md` | `kind:measurement source:mansueto stage:view topic:identifiers` | Migrated from the vault: Mansueto column to ADR-003 column mapping verified on PID 6662 (11 columns, 0 null or duplicate trip keys), query-to-view mapping, the stop-level row shape |
| `2026-11-10-mansueto-raw-day-profile.md` | `kind:measurement source:mansueto source:archive stage:impute topic:thresholds` | Raw CSV day 2026-10-22 through the archive pair and imputation stages: 420 s keeps 98.3% of pairs (180 s keeps 190 of 21,834), `tmstmp` truncated about 46 s early, route 47 has no `origtatripno`, calendar-day files split midnight runs, day files exist back to 2022-05-19 |
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
- Cause: the catalog was last modified 2025-01-16 and is not a list of published files. Two different failures: a route with no rows at all, so there is no pid and no URL to probe (route 10, seen 2026-10-02, no `10.0` variant either); and a listed pid whose parquet returns 404 (route 65 PIDs 7906 and 7907, seen 2026-09-21, while 7905, 3213 and 6652 of the same route return 200). Also patterns added after January 2025 (route 6 PID 7107, route 4 PIDs 28326–28329, route 147 PID 839) are missing.
- Fix: check `cta.mansueto.parquet_http_status(pid)` before planning on a PID, union only over pids that answer 200 or are cached locally, and log each skipped pid with its route and status instead of failing the run; discover current PIDs from the archive or Bus Tracker `getpatterns`; record archive-only routes in the TODO item (Michigan Ave "Route 10" item).

### Mansueto imputed history stops at 2026-07-28 and never overlaps the archive
Tags: `kind:gotcha source:mansueto source:archive topic:calendar`
- Symptom: a cross-source comparison finds no common service day.
- Cause: the per-pattern parquets have been frozen since 2026-07-28 (`MANSUETO_DATA_EDGE`, ADR-007) and the archive starts 2026-09-28. The same bucket's raw 5-minute position CSVs (`full_day_data/`) do continue, 2026-08-13 to 2026-10-27 with gaps (`docs/2026-11-06-mansueto-raw-positions.md`), but they are positions, not imputed arrivals, read through our own imputation by `cta.mansueto_raw` (`source='mansueto_raw'`, ADR-009); 2026-07-28 to 2026-08-12 is covered by nothing.
- Fix: same-source self-consistency is the adapter gate (`MAX_SELF_CONSISTENCY_DEVIATION`); the cross-source test stays skipped until `cta.mansueto.data_edge` moves. Each source's declared window is `cta.calendar.source_coverage()` (`coverage_days` gives the per-day spine; `calendar_flag(..., source=)` marks rows `coverage_gap`), and `cta.calendar.source_freshness` reads the download metadata and says `moved` when a frozen source passed its edge. Re-measure before assuming the edge changed; the constants change only through Rule 2.

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

### Mansueto raw `tmstmp` is truncated to the minute
Tags: `kind:gotcha source:mansueto stage:impute topic:timezone`
- Symptom: raw-CSV arrivals run about 46 s ahead of archive arrivals for the same bus.
- Cause: `full_day_data/*.csv` `tmstmp` is `YYYYMMDD HH:MM` Chicago wall time with the seconds cut off, not rounded: 10,145 of 10,933 fixes matched to the archive on 2026-10-22 were 0 to 60 s early, mean 46 s (`docs/2026-11-10-mansueto-raw-day-profile.md`).
- Fix: not corrected, by owner decision (`specs/mansueto-raw-adapter.md`, Method 8). Travel times and headways within the source are unaffected; compare absolute times with the archive knowing the bias.

### Mansueto raw `origtatripno` can be null
Tags: `kind:gotcha source:mansueto stage:clean topic:identifiers`
- Symptom: a route almost vanishes from one raw-CSV day, counted as `null_run_key_or_pdist`.
- Cause: on 2026-10-22, route 47's six patterns 502450 to 502455 had no `origtatripno` (3,265 of the route's 3,295 rows); none were null on 2026-09-15. The ADR-009 run key needs it. `tatripid` is never null but coarser (16,380 against 18,286 run keys), so it cannot replace it.
- Fix: rows are dropped and counted (`specs/mansueto-raw-adapter.md`); check the QA table per day before relying on a route.

### Mansueto raw day files are calendar days, not service days
Tags: `kind:gotcha source:mansueto stage:view topic:calendar`
- Symptom: late-night runs are cut in two, or a post-midnight trip carries the next day's date.
- Cause: each `full_day_data/YYYY-MM-DD.csv` holds local 00:00 to 23:55 and has no scheduled start, so the run key's `data_date` is the calendar date. On 2026-10-22, 23 of 1,559 Michigan runs started by 00:05 and 31 ended after 23:50; route 66 had 4.6% of its fixes before 04:00.
- Fix: none; accepted and documented (`specs/mansueto-raw-adapter.md`, Method 8). A file can also hold a few stale rows dated the evening before (4 on 2026-10-22); the adapter drops them as `other_data_date`. Stitching across files needs its own spec before late-night numbers for routes 8 and 66 are used.

### Mansueto imputed times can run backwards along a pattern
Tags: `kind:gotcha source:mansueto stage:clean topic:qa-table`
- Symptom: a trip's `bus_stop_time` decreases between consecutive stops.
- Cause: stop times are imputed from ~5-minute pings, so sequence order and time order disagree on short gaps.
- Fix: `cta.mansueto.clean_trips` drops and counts them as `nonmonotone_time` in the `order` stage (0 on the route 3 fixture day). Against pattern order the archive cannot produce them, because arrivals interpolate along monotone `pdist`. Against the Michigan latitude sequence it can, when a pattern's stop order differs from latitude order: route 4 NB PID 25899 loops off Michigan (north to Randolph, east on Randolph, north on Columbus, west on Wacker, back south on Michigan), so it serves Lake/Randolph after South Water, 2 trips on the 2026-10-29 fixture day; the hop into that loop is dropped as `detour_hop` (`specs/michigan-segment-from-view.md`).

### Mansueto `speed_mph` is a ping-interval speed
Tags: `kind:gotcha source:mansueto stage:view topic:thresholds`
- Symptom: Mansueto speeds look faster and smoother than imputed stop-to-stop speeds.
- Cause: it is the speed over the ~5-minute ping interval that encloses the stop, not between stops. Values outside [1, 115] mph are blanked and forward- and back-filled upstream, so a speed can belong to a neighbouring interval (`docs/2026-09-23-mansueto-imputation-method.md`).
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
- Open: the source of the six-holiday list in `cta.calendar.cta_holidays` is not recorded anywhere in the repo. The vault note it used to cite (`cta-holiday-schedule-filtering`, 2026-10-02, migrated 2026-11-13) holds no list: it asks for US federal holidays falling Mon to Fri at the least, and CTA's published holiday schedule if a stable source exists, checked against service anomalies in the data. Other federal holidays and observed days are not flagged. Changing the list is Rule 2 (`specs/calendar-module.md` leaves it out of scope).
- Fix: `cta.calendar.calendar_flag` labels each service date (`holiday:<name>`, `known_gap_day`, and with `source=` also `coverage_gap` for a date outside that source's declared coverage; the views pass their source); pairs that span a `known_gaps` window are dropped as `spans_known_gap`, the day itself stays. Exclusions and coverage windows live only in `cta/calendar.py`.

### `getpatterns` has a daily budget
Tags: `kind:gotcha source:bustracker stage:fetch topic:budget`
- Symptom: Bus Tracker returns an error after many pattern fetches, or a test tries to go online.
- Cause: 10,000 calls per day per key (`CTA_API_DAILY_MAX`), one call per pid.
- Fix: `cta.bustracker.batch_pattern_stops` caches each pid's response forever under `data/cta_api_cache/` and counts live calls in `request_log.json` by Chicago date (cache hits are free; warning at `CTA_API_DAILY_WARN`, 9,500; `daily_api_request_count()` reads the count). Calls are spaced by `CTA_API_MIN_INTERVAL_SEC` and retried three times on 429 / 503. Tests read the committed `tests/fixtures/getpatterns/` only. Never print `CTA_API_KEY`. Endpoint shapes: `docs/2026-09-23-bustracker-api-endpoints.md`.

### `getpatterns` fails the whole batch when one pid is unknown
Tags: `kind:gotcha source:bustracker stage:fetch topic:pattern-catalog`
- Symptom: a comma-delimited `getpatterns` call (up to 10 pids) returns `No data found for parameter` and no patterns at all.
- Cause: the live API rejects the whole call if any one pid is unknown to it, and Mansueto has parquets for historical pids the live API no longer serves (`docs/2026-09-23-bustracker-api-endpoints.md`).
- Fix: `cta.bustracker.batch_pattern_stops` calls one pid at a time, catches the `RuntimeError`, skips the pid and prints the skipped list. A skipped pid has no `pdist`, `rtdir` or `stop_rank`, so its rows cannot enter the run-level view.

### The Mansueto parquet has no direction column
Tags: `kind:gotcha source:mansueto source:bustracker stage:clean`
- Symptom: a stop-level key (`stop_id`, `route`, `direction`) cannot be built from the parquet alone.
- Cause: the eleven published columns hold no direction (`docs/2026-08-10-mansueto-parquet-column-mapping.md`).
- Fix: `cta.mansueto.clean_trips` joins the getpatterns `rtdir` from `cta.bustracker.pattern_stops_table`; the view exposes it as `direction`. Route 157's patterns are labelled Westbound / Eastbound although they run on Michigan, so a corridor direction is not always the `rtdir` (`corridor_stops_from_view` places them by stop membership).

### Mansueto arrivals at the ends of a trip can be extrapolated
Tags: `kind:gotcha source:mansueto stage:impute`
- Symptom: the first or last stop of a Mansueto trip has an odd arrival time.
- Cause: stops before the first ping or after the last one are extrapolated from the implied segment speed, not interpolated between two pings (`docs/2026-09-23-mansueto-imputation-method.md`). No ping time is published, so `bracket_gap_s` cannot show it.
- Fix: nothing in `cta/` flags these rows. Prefer interior stops for timing endpoints on Mansueto data, and say so when a segment starts or ends at a terminal.

### Day slices do not exclude holidays
Tags: `kind:gotcha stage:figure topic:calendar`
- Symptom: a Mon to Thu or Friday bucket includes a day on which CTA ran holiday service.
- Cause: `cta.dlsd_run_quality.day_slice_mask` and `cta.michigan_ave_segment.michigan_day_slice_mask` look at the day of week only. The DLSD comparison plots were made that way and have not been redone.
- Fix: filter on the view's `calendar_flag` (`holiday:` prefix) before slicing; `dlsd_runs_from_view` and `corridor_stops_from_view` carry the column. Whether a holiday joins the weekend slice or gets its own bucket is undecided: say which in the figure. The DLSD figures are redone when the notebooks are re-pointed (TODO.md Foundation, first item; "Completed workstreams").

### PID 6402's hand trim exists only in a local cache file
Tags: `kind:gotcha source:bustracker topic:pattern-catalog topic:fixtures`
- Symptom: 148 Southbound PID 6402 shows stops after Michigan & Hubbard (`1104`, `1105`, `1106`, `18396`) that published trips never serve, and its corridor exit moves to Monroe.
- Cause: the four stops were deleted by hand from `data/cta_api_cache/getpatterns_6402.json`, which is gitignored. A fresh clone, a deleted cache or a refetch has the untrimmed pattern, and so does the committed `tests/fixtures/getpatterns/getpatterns_6402.json` (`docs/2026-10-02-michigan-ave-6402-pattern-trim.md`).
- Fix: nothing in `cta/` re-applies the trim. `TRIM_6402_STPIDS` names the stops and `segment_view_report` lists an issue when the legacy view has rows there. The kept record in `notebooks/michigan_ave_kept_pids.json` still says Delaware to Hubbard, so read entry and exit from it, not from the pattern's last corridor stop. Making the trim reproducible is a behaviour change and needs a spec.

### Corridor stops next to the Lake Shore Drive ramp carry express speeds
Tags: `kind:gotcha source:mansueto stage:figure topic:thresholds`
- Symptom: the north end of a Michigan Ave speed chart looks much faster than the rest.
- Cause: the 14x express routes join the Drive at Delaware, and Mansueto `speed_mph` is a ping-interval speed, so a ping pair around Delaware, Chestnut or Pearson can span part of the Drive. The vault note records the exclusion as a "DLSD speed leak"; the size of the effect was not measured.
- Fix: `cta.michigan_ave_segment.filter_dlsd_leak_stops` drops `1128` and `1127` northbound and `1097` and `1098` southbound (`NORTHBOUND_DLSD_LEAK_STPIDS`, `SOUTHBOUND_DLSD_LEAK_STPIDS`) from charts only; the stops stay in the corridor definition, and Chicago (`1126`) stays in the charts. It is a published exclusion (Rule 2).

### The corridor snapshot's metadata does not match its stop list
Tags: `kind:gotcha source:bustracker stage:clean topic:pattern-catalog`
- Symptom: `corridor.roosevelt_stpids` in `notebooks/michigan_ave_stops_snapshot.json` names four stops, two of which are not among the 40 `stops`.
- Cause: `15362` and `17084` are Roosevelt-named side-street stops that the discovery notebook excluded afterwards; the metadata was not updated, and the eleven-id exclusion list is not in the JSON at all (`docs/2026-10-02-michigan-ave-corridor-stops.md`).
- Fix: use `1591` (southbound) and `1580` (northbound) as the Roosevelt anchors and take stops only from `stops`. The exclusion list is in the dated note and in section 4.5 of `notebooks/michigan_ave_stop_discovery.ipynb`.

### Rush-route plot cells are gated on Mon to Thu counts, whatever slice is drawn
Tags: `kind:gotcha stage:figure topic:thresholds`
- Symptom: a Friday pane for routes 134, 135, 136, 143 or 148 comes out almost empty, or shows cells resting on a handful of runs.
- Cause: Friday cells have a median of 12 runs, weekday cells 62 (`docs/2026-09-24-dlsd-rush-hour-min-sample.md`). A per-slice `min_runs=30` empties Friday; no gate at all draws noise.
- Fix: pass `valid_cells=cta.dlsd_run_quality.valid_rush_plot_cells(dlsd_runs)` to `hour_dlsd_stats` for every slice. The set is built from Mon to Thu runs at `MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY` (30); Friday reuses it and may rest on few runs, so say so on the figure. Routes 146 and 147 are not gated; the weekend slice holds only them.

### Not every pattern of a Lake Shore Drive route uses the Drive
Tags: `kind:gotcha source:bustracker stage:clean topic:pattern-catalog`
- Symptom: a pid of route 147 has no entry in `notebooks/dlsd_boundaries_snapshot.json`, or a route-wide DLSD statistic is short of runs.
- Cause: PID 839 (147 Northbound, about 9,300 trips) starts north of the Drive at Sheridan & Foster; its largest hop is about 1,000 ft (`docs/2026-09-23-dlsd-segment-boundaries-146-147.md`).
- Fix: DLSD timing joins on `pid` through `load_dlsd_boundaries`, so such patterns drop out by construction. Count runs per pid, not per route, when checking coverage. Stop names say "Lake Shore Drive", never "DLSD".

### The legacy segment view builds empty when parquet reads fail
Tags: `kind:gotcha source:mansueto stage:view`
- Symptom: `build_michigan_segment_view` returns zero rows although `kept_pid_cache_status` shows every cache file present.
- Cause: the builder wraps `pd.read_parquet` in `except Exception: continue`, so a missing pyarrow or a corrupt file skips the pid silently (seen 2026-10-03, `docs/2026-10-02-michigan-ave-legacy-segment-view-check.md`).
- Fix: `segment_view_report` warns about it; install `requirements.txt` first. The builder is deprecated: use `corridor_stops_from_view`, which reads the run-level view and emits a QA table.

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
- Run `/fixture` (`.claude/skills/fixture/SKILL.md`): it picks the builder to copy by source (`scripts/build_archive_fixtures.py` for one archive day filtered to kept PIDs with an `index.json`-shaped manifest; `scripts/build_mansueto_fixtures.py` for parquet cuts, footer sample and `mansueto.manifest.json`), names the source-moved guard for each source (index SHA-256; `Last-Modified` on `MANSUETO_DATA_EDGE`; a recorded HEAD for the raw CSVs, which have no manifest), and prints the deviations from the spec's `~N` estimates. One archive day per fixture file and a 20 MB fixture budget (Rule 3); tests never write to `data/` (Rule 4); bytes deterministic (gzip mtime 0, sorted zstd parquet).

### Probe a remote parquet without downloading it
Tags: `kind:pattern source:mansueto stage:fetch topic:network`
- Copy `cta.mansueto.data_edge`: `http_head` for size and `Last-Modified`, `parquet_footer` by range request, `footer_summary` for per-row-group statistics. `docs/2026-11-04-mansueto-data-edge.md` shows what it answers.
- For the raw day files, which have no footer to read, walk the dates with HEAD requests, newest first; the first 200 is the newest day (`docs/2026-08-10-mansueto-freshness-probe.md` has the loop). `cta.calendar.source_freshness` answers the same question offline from the download metadata.

### Verify a parquet's schema before naming its columns in code
Tags: `kind:pattern source:mansueto stage:qa topic:identifiers`
- Copy `scripts/verify_parquet.py` (`verify`, tested in `tests/test_verify_parquet.py`): on one real file, list the columns, find the trip key and count its nulls, count duplicate (trip, stop) pairs, read the min and max arrival time, describe stops per trip, and check dtypes (the arrival column must be a datetime, ids consistently typed). Record the result in a dated note (`docs/2026-08-10-mansueto-parquet-column-mapping.md` is the one for Mansueto). A missing stop is never given a fabricated time.

### Find the express segment of a pattern
Tags: `kind:pattern source:bustracker stage:clean topic:thresholds`
- Copy section 2 of `notebooks/dlsd_stop_discovery_rush_routes.ipynb`: order the `getpatterns` stops, take the largest gap between consecutive stops, call it the express segment when it exceeds 10,000 ft, and keep the stop before and after as entry and exit. Review the result against the expected geography (`docs/2026-09-24-dlsd-rush-express-routes.md`) before writing `notebooks/dlsd_boundaries_snapshot.json`. The 10,000 ft is inline in the notebooks, not yet a named constant in `cta/`.

### Draw a corridor speed chart
Tags: `kind:pattern stage:figure topic:thresholds`
- Copy `notebooks/michigan_ave_speed_plots.ipynb`: one figure per day slice, a Northbound and a Southbound panel with a shared y axis; x is latitude, south to north, with street ticks from `corridor_street_tick_positions`; y is minutes per mile, so slow is high, with `ax.secondary_yaxis` giving mph through `60 / x` both ways. Per stop: median line, interquartile band, and a dashed p95 minutes per mile computed as `60 / q05(speed)`. A stop with fewer than `MIN_OBS` (10) observations is a gap. Hours are the three slowest by pooled median (`slowest_hours`, within `DEFAULT_PLOT_HOURS`, the same hours for both directions; `SLOW_HOURS_OVERRIDE` in the notebook), over `shared_observation_window` (the 720 hours before the newest observation).
- The notebook still feeds this layout with Mansueto ping-interval `speed_mph`. New charts keep the layout and take segment speeds from `corridor_segment_min_per_mile_stats` (ADR-010).

### Add a CLI entry point
Tags: `kind:pattern topic:process`
- Copy `scripts/archive_run_level.py`: argparse, a module docstring with examples that `-h` prints, every computation in `cta/`, output paths under `data/`. The script is thin enough that its test is the `cta` test.

### Flag a service date instead of filtering it
Tags: `kind:pattern topic:calendar stage:clean`
- Copy `cta.calendar.calendar_flag`: return a label column, let downstream decide. A day slice reads the label before its day-of-week mask (gotcha "Day slices do not exclude holidays"). New calendar facts (Mansueto freshness, source-coverage holes) go in `cta/calendar.py`, not in the adapter.

### Check that a refactor changed nothing
Tags: `kind:pattern stage:qa topic:process topic:fixtures`
- In the suite: copy `tests/test_bustracker.py` `test_parser_equivalence` (`pd.testing.assert_frame_equal` of the new path against the old one on a fixture) while both paths exist; `specs/split-cta-api.md` is the shape of a spec whose whole job is a refactor. Existing tests pass with import changes only (CLAUDE.md rule 7).
- Beyond the suite, for cleaning or imputation code: each fixture is one archive day cut to a few PIDs, so it cannot see every branch. Before the refactor, run `scripts/archive_run_level.py --days <a cached day> --out <path outside the repo>/before.parquet`; after it, the same with `after.parquet`; then `assert_frame_equal` the two parquets and the two `.qa.csv` files. Use a day already under `data/archive/raw/` (no download) and write both outputs outside the repo.

### Filter runs by structure, not by a minute cap
Tags: `kind:pattern stage:clean topic:thresholds`
- Copy `cta.dlsd_run_quality.add_quality_flags`: `analysis_ok` is both times present, exit after entry, and exit index equal to entry index plus one. The old `[1, 120]` minute cap is kept only as the informational `legacy_drop` flag; posted speed limits are not filters. The reason is the ~5-minute resolution of Mansueto arrivals (`docs/2026-09-23-mansueto-imputation-method.md`).

### Record a durable fact
Tags: `kind:pattern topic:process`
- A measurement: `/finding` writes a dated `docs/` note (`docs/2026-11-04-mansueto-data-edge.md` is the shape). A gotcha or a pattern: `/finding` appends here. A choice future work must respect: `/adr`. A step every task follows: the skill file. CLAUDE.md holds only rules an agent acts on.
