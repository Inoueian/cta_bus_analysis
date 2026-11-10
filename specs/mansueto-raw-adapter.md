# Spec: Mansueto raw-positions adapter → run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-10  ·  TODO item (Foundation): "Mansueto raw-positions adapter (`cta/mansueto_raw.py`, `source='mansueto_raw'`, ADR-009): read `full_day_data/YYYY-MM-DD.csv` (71 day files 2026-08-13 to 2026-10-27, 300 s cadence, minute timestamps, `pdist` in feet, no manifest; `docs/2026-11-06-mansueto-raw-positions.md`) into the archive's pair and imputation stages with its own named gap threshold (`MAX_BRACKET_GAP_S = 180` would drop every pair), a run key from `vid`, `pid`, `origtatripno`, `data_date`, one committed day cut as the fixture (`/fixture`, Rule 3) and the per-stage QA table; `cta.views.run_level_from_mansueto_raw` with `bracket_gap_s` populated. Day files exist back to 2022-05-19 (HEAD on four sampled days, `docs/2026-11-10-mansueto-raw-day-profile.md`), but ADR-009 bounds the source to the 2026 window; reading history is a new decision. Unblocks the Phase 3 cross-source checks. Spec: specs/mansueto-raw-adapter.md (draft)"
Tags: `kind:spec source:mansueto stage:clean stage:impute stage:view`

## Question

What did riders experience between 2026-08-13 and 2026-09-27, the 46 days no other source covers, and
how much does a 5-minute poll change an imputed arrival compared with a 60 s one? Both need the ADR-003
run-level view from Mansueto's raw day CSVs, built by our imputation (ADR-009). Now, because the Phase 1
route views and the Phase 3 cross-source checks wait on it. Evidence for every number below:
`docs/2026-11-10-mansueto-raw-day-profile.md` (one day, 2026-10-22, run through the archive stages).

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Raw day CSV | `{cta.mansueto.BASE}/full_day_data/YYYY-MM-DD.csv`, cached as `data/mansueto_raw/YYYY-MM-DD.csv` | `vid, tmstmp, lat, lon, hdg, pid, rt, des, pdist, dly, tatripid, origtatripno, tablockid, zone, scrape_file, data_time, data_hour, data_date` | 26 to 45 MB; no manifest or checksum; `tmstmp` is `YYYYMMDD HH:MM` Chicago wall time, truncated to the minute (about 46 s early on average); a calendar day, not a service day |
| Pattern stops | `cta.bustracker.pattern_stops_table` (getpatterns cache) | pid, rtdir, seq, stop_rank, stpid, pdist_ft | passed in or read from `pattern_cache_dir`; never fetched here |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Cached day + metadata | `cta.mansueto_raw.fetch_day(day, dest_dir) -> Path`, writes `YYYY-MM-DD.meta.json` | url, bytes, last_modified, fetched_at, rows | one per day file |
| Positions | `cta.mansueto_raw.read_day(path, pids=None) -> DataFrame` | route, pid, vehicle_id, origtatripno, data_date (str); tmstmp (str); vehicle_ts (UTC, NaT if ambiguous); pdist, lat, lon (float) | one row per CSV row, nothing dropped |
| Clean fixes | `cta.mansueto_raw.clean_fixes(con, day, positions) -> DataFrame` | `cta.archive.CLEAN_FIX_COLUMNS` | one row per (run_id, vehicle_ts) |
| Run-level view + QA | `cta.views.run_level_from_mansueto_raw_with_qa(days, pids, *, csv_dir, pattern_stops=None, pattern_cache_dir=None, con=None) -> (view, qa)`; `run_level_from_mansueto_raw(...)` returns the view | view: `RUN_LEVEL_COLUMNS`, `source='mansueto_raw'`, `bracket_gap_s` populated; qa: `day` + `cta.archive.QA_COLUMNS` | view: one row per (run, stop); qa: one row per (day, stage, reason) |

`run_id = f"{vid}-{pid}-{origtatripno}-{data_date}"` (ADR-009). `service_date = data_date`.

## Method

Prior art to copy: `cta/archive.py` `clean_fixes` → `fix_pairs` → `impute_arrivals` (called, not copied) and
`_record_qa`; `cta/mansueto.py` `fetch_parquet` / `write_meta` and `to_utc`; `cta/views.py`
`run_level_from_mansueto_with_qa`; `tests/test_archive.py` `test_synthetic_trip_arrival_time_is_exact`,
`test_pair_filters_each_reason_once`. Playbook pattern "Add a source adapter that produces the run-level view".

1. `fetch_day`: `cta.mansueto.http_head`, then (ADR-009: verify by probing, record what was found):
   404 raises `FileNotFoundError` naming the day as a coverage gap; a cached file whose metadata matches the HEAD
   `bytes` and `Last-Modified` is returned without downloading; metadata that differs raises, never overwrites.
   Otherwise `download` to a `.part` file (as `fetch_parquet`); a size other than the HEAD `bytes` raises and
   leaves no file or metadata behind. Tests replace both network functions.
2. `read_day`: DuckDB `read_csv(all_varchar=true)` on `.csv` or `.csv.gz`; identifiers through
   `cta.mansueto._id_str` (gotcha "Identifiers arrive as `6410.0`"); `vehicle_ts` = `cta.mansueto.to_utc` of the
   parsed `tmstmp` (`RAW_TZ`), no correction for the truncated seconds; ambiguous or nonexistent DST times become
   NaT (gotcha "naive Chicago wall time"; none in the 2026 window, which ends before 2026-11-01).
3. Stage `read`: rows_in = rows_out = rows for the requested pids. Stage `clean`: drop rows with null `vid`,
   `pid`, `origtatripno`, `data_date`, `pdist` or `tmstmp` (`null_run_key_or_pdist`), then rows whose `data_date`
   is not the file's day (`other_data_date`: 4 of 212,797 on 2026-10-22, stale fixes from 23:55 to 23:58 the
   evening before; kept, they would rebuild the previous day's run_ids from a second file), then NaT `vehicle_ts`
   (`dst_ambiguous_time`), then keep one fix per (run_id, vehicle_ts) with min `pdist` (`duplicate_fix`). So
   `service_date` always equals the file's day and (run_id, stop_id) is unique across days.
4. Stage `pairs`: `cta.archive.fix_pairs(con, day, fixes, known_gaps=None, max_gap_s=MAX_RAW_BRACKET_GAP_S)`.
   This adds one keyword, `max_gap_s: float = MAX_BRACKET_GAP_S`, to `fix_pairs`; archive behaviour and
   tests are unchanged. Transit Alerts `known_gaps` are not Mansueto outages, so none are passed.
5. Stage `impute`: `cta.archive.impute_arrivals` unchanged.
6. QA lives in `archive_qa` on a connection from `cta.mansueto_raw.open_db()` (in-memory by default), which also
   creates a one-row marker table `mansueto_raw_db`; `cta.mansueto_raw.qa(con, day)` returns it. The adapter
   refuses a connection without the marker or with rows in `archive_ingest`: on the 25 overlap days the two
   sources would overwrite each other's `clean`, `pairs` and `impute` rows. The archive side stays unguarded (not
   changed here), so the module docstring says never to pass this connection to `cta.archive` ingest. The private
   `cta.archive._record_qa` and `cta.mansueto._id_str` are used as they are; a shared QA helper is the `/qa` item.
7. View: as `run_level_from_archive` assembles it; `stop_sequence_index = stop_rank` (ADR-008);
   `calendar_flag` from `cta.calendar.calendar_flag(..., index=None)` (holidays only; gotcha "Holidays and
   archive outages are flags"). `bracket_gap_s` is never NaN here, so gap filters must also use `source` (gotcha
   "`bracket_gap_s` NaN means unknown"). A day's file in `csv_dir` is `<day>.csv`, `<day>.csv.gz` or
   `mansueto_raw_<day>_*.csv.gz` (the fixture), nothing else; none or several raises. Never touches the network.
8. Known limits, in the module docstring and not fixed here (owner, 2026-11-10), each a playbook gotcha: arrivals
   0 to 60 s early ("Mansueto raw `tmstmp` is truncated to the minute"); null `origtatripno` rows dropped, route 47
   on 2026-10-22 ("Mansueto raw `origtatripno` can be null"); runs split at local midnight and calendar-date
   `service_date` ("Mansueto raw day files are calendar days"); missed-poll arrivals (`bracket_gap_s` 540 to
   660) kept, downstream filters decide.
9. No speed column (Rule 6). ADR-010 excludes this source from segment speeds in figure code via `source`.
10. On landing, reword the playbook gotcha "Mansueto imputed history stops at 2026-07-28 and never overlaps the
    archive" ("no adapter reads them" stops being true) to point at `cta.mansueto_raw`.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `MAX_RAW_BRACKET_GAP_S` | 660.0 | 2026-10-22 profile: 97% of pairs at 240/300/360 s; a second cluster, one missed poll, ends at 660 s (full day: 438 pairs at 660 s, 27 at 720 s); drops 85 of 21,834 pairs (0.4%). Owner chose 660 over 420 on 2026-11-10 | 420 drops the missed-poll pairs: 1.8% fewer arrivals; 180 keeps 190 pairs |
| `RAW_TZ` | `America/Chicago` | day file spans 00:00 to 23:55; localized as Chicago, fixes land within 60 s of the archive's UTC `vehicle_ts` | wrong tz shifts every arrival 5 to 6 h |
| `SOURCE_MANSUETO_RAW` | `"mansueto_raw"` | ADR-009 | n/a |
| `MAX_IMPLIED_MPH`, `GEOMETRY_SLACK_FT` | archive values, reused | 0 and 23 pairs dropped at 300 s cadence on the cut | n/a |

## Fixtures

Numbers marked `~` were measured on an uncommitted cut on 2026-11-10; `/fixture` pins them.

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/mansueto_raw_2026-10-22_michigan.csv.gz` + `mansueto_raw.manifest.json` | `full_day_data/2026-10-22.csv` (43,877,441 bytes, `Last-Modified` 2026-10-23 10:02:16 UTC, 212,797 rows) | header plus lines whose `pid` is one of the 45 in `notebooks/michigan_ave_kept_pids.json`, verbatim, source order, gzip mtime 0 | ~23,453 rows, ~0.73 MB | `scripts/build_mansueto_raw_fixtures.py` (new; refuses if the HEAD differs from the values here) |
| `tests/fixtures/getpatterns/` | existing, 45 files | | | |

2026-10-22: a Thursday in both sources, outside `known_gaps` and the missing CSV days, so Phase 3 can cut the
archive side of the same day. Own manifest, as `scripts/build_mansueto_fixtures.py` rewrites `mansueto.manifest.json`.

## Acceptance tests

In `tests/test_mansueto_raw.py` and `tests/test_views_mansueto_raw.py`.

- [ ] `test_read_day_rows_and_types` (`tests/fixtures/mansueto_raw_2026-10-22_michigan.csv.gz`): ~23,453 rows matching the manifest's rows and SHA-256, ~44 pids, identifiers `str`, `vehicle_ts` tz-aware UTC with second 0 on every row, no nulls introduced.
- [ ] `test_clean_fixes_counts` (`tests/fixtures/mansueto_raw_2026-10-22_michigan.csv.gz`): ~23,393 fixes, ~1,559 runs, reasons `duplicate_fix` ~60 and nothing else.
- [ ] `test_known_case_arrivals` (hand-built, no fixture): pings at 08:00, 08:05, 08:10 Chicago on 2026-09-15 with pdist 0, 3000, 6000 and stops at 1500 and 4500 ft arrive at 13:02:30 and 13:07:30 UTC exactly, `bracket_gap_s == 300`; a repeated `tmstmp` keeps the lower pdist; a null `origtatripno` row and a 2025-11-02 01:30 row are dropped as `null_run_key_or_pdist` and `dst_ambiguous_time`.
- [ ] `test_two_days_no_shared_runs` (hand-built, no fixture; `tmp_path`): files for 2026-09-15 and 2026-09-16 hold one bus's trip each, and the second also holds two fixes of the first day's trip with `data_date` 2026-09-15; the view over both days counts 2 `other_data_date` on 2026-09-16, has zero (run_id, stop_id) duplicates, and every row's `service_date` is its file's day.
- [ ] `test_gap_threshold_is_per_source` (hand-built, no fixture): 300 s and 600 s pairs survive and a 900 s pair is `gap_over_max` under `MAX_RAW_BRACKET_GAP_S`; the same 300 s pair is dropped by `fix_pairs` with no `max_gap_s`; `cta.archive.MAX_BRACKET_GAP_S == 180`.
- [ ] `test_run_level_view` (`tests/fixtures/mansueto_raw_2026-10-22_michigan.csv.gz`, `tests/fixtures/getpatterns/`): columns exactly `RUN_LEVEL_COLUMNS`; `source == "mansueto_raw"`; ~97,663 rows, ~1,532 runs; zero (run_id, stop_id) duplicates; `bracket_gap_s` never null, max ≤ 660, median 300; `stop_sequence_index` strictly increasing within a run when sorted by `arrival_time` then index; `service_date == "2026-10-22"`; `calendar_flag == ""`.
- [ ] `test_qa_table` (`tests/fixtures/mansueto_raw_2026-10-22_michigan.csv.gz`, `tests/fixtures/getpatterns/`): stages `read`, `clean`, `pairs`, `impute` for the day; reason counts sum to rows_in − rows_out at each; pairs rows_in = fixes − runs (~21,834); `gap_over_max` ~85, `backward_pdist` ~30, `geometry_unsupported` ~23, `later_crossing` ~5.
- [ ] `test_fetch_day_records_and_refuses` (hand-built, no fixture: monkeypatched `http_head` / `download`, `tmp_path`): writes the metadata file; a second call with an unchanged HEAD returns the same path and `download` has been called once; a changed `Last-Modified` raises; a download shorter than the HEAD `bytes` raises and leaves no file or metadata; a 404 raises `FileNotFoundError`; nothing touches the network or `data/`.
- [ ] `test_refuses_foreign_connection_and_files` (hand-built, no fixture; `tmp_path`): a `cta.archive.open_archive_db()` connection (no marker) raises, and so does an `open_db()` connection with a row in `archive_ingest`; `2026-10-22.csv` beside `mansueto_raw_2026-10-22_x.csv.gz` raises, an `archive_2026-10-22_x.ndjson.gz` beside one of them is ignored; `tests/test_archive.py` and `tests/test_views_archive.py` pass unmodified.

## Out of scope

- Comparing these arrivals with the archive or the parquet, per-pid medians, any ADR-006 bound: the Phase 3 cross-source item, which also owns the same-day archive fixture.
- Stitching runs across midnight or deriving a service day; reading two day files as one.
- Shifting `tmstmp` to correct the truncation; falling back to `tatripid` for a null `origtatripno`.
- Days before 2026-08-13. Files exist back to 2022-05-19 (sampled), but ADR-009 bounds this source; history is a new decision.
- Coverage holes and the CSV edge in `cta/calendar.py` (calendar item); the refresh probe (Phase 3).
- A CLI script; `scripts/route_run_level.py` (Phase 1) calls the view function.
- Changing any archive threshold, the shared QA helper (`/qa` item), or `cta.mansueto`.
- Filtering by `bracket_gap_s` or `source` downstream; using `dly`, `des`, `tatripid`, `scrape_file`.

## Open questions

None. Resolved by the owner 2026-11-10: no `tmstmp` shift; null `origtatripno` rows dropped; gap cap 660 s;
calendar-date `service_date` and midnight-split runs accepted. Review fixes applied the same day.
