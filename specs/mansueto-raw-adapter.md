# Spec: Mansueto raw-positions adapter → run-level view

Status: draft
Owner: Satoru  ·  Date: 2026-11-10  ·  TODO item (Foundation): "Mansueto raw-positions adapter (`cta/mansueto_raw.py`, `source='mansueto_raw'`, ADR-009): read `full_day_data/YYYY-MM-DD.csv` (71 day files 2026-08-13 to 2026-10-27, 300 s cadence, minute timestamps, `pdist` in feet, no manifest; `docs/2026-11-06-mansueto-raw-positions.md`) into the archive's pair and imputation stages with its own named gap threshold (`MAX_BRACKET_GAP_S = 180` would drop every pair), a run key from `vid`, `pid`, `origtatripno`, `data_date`, one committed day cut as the fixture (`/fixture`, Rule 3) and the per-stage QA table; `cta.views.run_level_from_mansueto_raw` with `bracket_gap_s` populated. The upstream README says day files go back to 2022-05-19; verify with a HEAD before planning on history. Unblocks the Phase 3 cross-source checks."
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
| Raw day CSV | `{cta.mansueto.BASE}/full_day_data/YYYY-MM-DD.csv`, cached as `data/mansueto_raw/YYYY-MM-DD.csv` | `vid, tmstmp, lat, lon, hdg, pid, rt, des, pdist, dly, tatripid, origtatripno, tablockid, zone, scrape_file, data_time, data_hour, data_date` | 26 to 45 MB; no manifest or checksum; `tmstmp` is `YYYYMMDD HH:MM` Chicago wall time, truncated to the minute; a calendar day, not a service day |
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

1. `fetch_day`: `cta.mansueto.http_head` then `download` (ADR-009: verify by probing, record what was
   found). 404 raises `FileNotFoundError` naming the day as a coverage gap. If a metadata file exists and
   the HEAD `bytes` or `Last-Modified` differ from it, raise; never overwrite silently. Tests replace both
   network functions.
2. `read_day`: DuckDB `read_csv(all_varchar=true)` on `.csv` or `.csv.gz`; identifiers through
   `cta.mansueto._id_str` (gotcha "Identifiers arrive as `6410.0`"); `vehicle_ts` = `tmstmp` localized with
   `RAW_TZ` plus `TMSTMP_OFFSET_S`, UTC; an ambiguous fall-back time becomes NaT (gotcha "naive Chicago wall
   time"; none in the 2026 window, which ends before 2026-11-01).
3. Stage `read`: rows_in = rows_out = rows for the requested pids.
4. Stage `clean`: drop rows with null `vid`, `pid`, `origtatripno`, `data_date`, `pdist` or `tmstmp`
   (`null_run_key_or_pdist`), then NaT `vehicle_ts` (`dst_ambiguous_time`), then keep one fix per
   (run_id, vehicle_ts) with min `pdist` (`duplicate_fix`: a parked bus repeats its `tmstmp` across polls).
5. Stage `pairs`: `cta.archive.fix_pairs(con, day, fixes, known_gaps=None, max_gap_s=MAX_RAW_BRACKET_GAP_S)`.
   This adds one keyword, `max_gap_s: float = MAX_BRACKET_GAP_S`, to `fix_pairs`; archive behaviour and
   tests are unchanged. Transit Alerts `known_gaps` are not Mansueto outages, so none are passed.
6. Stage `impute`: `cta.archive.impute_arrivals` unchanged.
7. QA lives in `archive_qa` on a connection this adapter owns (`cta.mansueto_raw.open_db()`, in-memory by
   default); `cta.mansueto_raw.qa(con, day)` returns it. A connection with rows in `archive_ingest` is
   refused: the 25 overlap days would overwrite each other's `clean`, `pairs` and `impute` rows.
8. View: as `run_level_from_archive` assembles it; `stop_sequence_index = stop_rank` (ADR-008);
   `calendar_flag` from `cta.calendar.calendar_flag(..., index=None)` (holidays only; gotcha "Holidays and
   archive outages are flags"). `csv_dir` holds `<day>.csv`, or any file whose name contains the day (the
   fixture). A day with no file raises; the view function never touches the network.
9. Known limits, stated in the module docstring and not fixed here: a run crossing local midnight is two
   run_ids in two files (23 runs start by 00:05 and 31 end after 23:50, of ~1,559); post-midnight arrivals
   carry the calendar date (1,394 arrivals on the cut) where the archive gives the scheduled date.
10. No speed column (Rule 6). ADR-010 excludes this source from segment speeds in figure code via `source`.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| `MAX_RAW_BRACKET_GAP_S` | 420.0 | 2026-10-22 profile: 97% of pairs at 240/300/360 s; max poll spacing 348 s + 60 s truncation; drops 334 of 21,834 pairs (1.5%) | 660 keeps one-missed-poll pairs: +1.8% arrivals, each with a 10-minute bracket; 180 keeps 190 pairs |
| `TMSTMP_OFFSET_S` | 46.0 | archive `vehicle_ts` minus CSV `tmstmp` on 10,145 matched fixes: all in [0, 60), mean 45.8 s | 0 leaves arrivals ~46 s early against the archive; headways and travel times do not move |
| `RAW_TZ` | `America/Chicago` | day file spans 00:00 to 23:55; localized as Chicago, fixes land within 60 s of the archive's UTC `vehicle_ts` | wrong tz shifts every arrival 5 to 6 h |
| `SOURCE_MANSUETO_RAW` | `"mansueto_raw"` | ADR-009 | n/a |
| `MAX_IMPLIED_MPH`, `GEOMETRY_SLACK_FT` | archive values, reused | 0 and 20 pairs dropped at 300 s cadence on the cut | n/a |

## Fixtures

Numbers marked `~` were measured on an uncommitted cut on 2026-11-10; `/fixture` pins them.

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/mansueto_raw_2026-10-22_michigan.csv.gz` + `mansueto_raw.manifest.json` | `full_day_data/2026-10-22.csv` (43,877,441 bytes, `Last-Modified` 2026-10-23 10:02:16 UTC, 212,797 rows) | header plus lines whose `pid` is one of the 45 in `notebooks/michigan_ave_kept_pids.json`, verbatim, source order, gzip mtime 0 | ~23,453 rows, ~0.73 MB | `scripts/build_mansueto_raw_fixtures.py` (new; refuses if the HEAD differs from the values here) |
| `tests/fixtures/getpatterns/` | existing, 45 files | | | |

2026-10-22 is a Thursday like the archive fixture day, is in both sources, and is outside `known_gaps` and
the five missing CSV days, so the Phase 3 check can cut the archive side of the same day. Its own manifest
file, because `scripts/build_mansueto_fixtures.py` rewrites `mansueto.manifest.json`.

## Acceptance tests

All in `tests/test_mansueto_raw.py` and `tests/test_views_mansueto_raw.py`, on the fixture above unless hand-built.

- [ ] `test_read_day_rows_and_types`: ~23,453 rows matching the manifest's rows and SHA-256, ~44 pids, identifiers `str`, `vehicle_ts` tz-aware UTC with second 46 on every row, no nulls introduced.
- [ ] `test_clean_fixes_counts`: ~23,393 fixes, ~1,559 runs, reasons `duplicate_fix` ~60 and nothing else.
- [ ] `test_known_case_arrivals` (hand-built): pings at 08:00, 08:05, 08:10 Chicago on 2026-09-15 with pdist 0, 3000, 6000 and stops at 1500 and 4500 ft arrive at 13:03:16 and 13:08:16 UTC exactly, `bracket_gap_s == 300`; a repeated `tmstmp` keeps the lower pdist; a null `origtatripno` row and a 2025-11-02 01:30 row are dropped as `null_run_key_or_pdist` and `dst_ambiguous_time`.
- [ ] `test_gap_threshold_is_per_source` (hand-built): a 300 s pair survives and a 600 s pair is `gap_over_max` under `MAX_RAW_BRACKET_GAP_S`; the same 300 s pair is dropped by `fix_pairs` with no `max_gap_s`; `cta.archive.MAX_BRACKET_GAP_S == 180`.
- [ ] `test_run_level_view`: columns exactly `RUN_LEVEL_COLUMNS`; `source == "mansueto_raw"`; ~95,925 rows, ~1,531 runs; zero (run_id, stop_id) duplicates; `bracket_gap_s` never null, max ≤ 420, median 300; `stop_sequence_index` strictly increasing within a run when sorted by `arrival_time` then index; `service_date == "2026-10-22"`; `calendar_flag == ""`.
- [ ] `test_qa_table`: stages `read`, `clean`, `pairs`, `impute` for the day; reason counts sum to rows_in − rows_out at each; pairs rows_in = fixes − runs (~21,834); `gap_over_max` ~334, `backward_pdist` ~26, `geometry_unsupported` ~20, `later_crossing` ~5.
- [ ] `test_fetch_day_records_and_refuses` (monkeypatched `http_head` / `download`, `tmp_path`): writes the metadata file; a second call with a changed `Last-Modified` raises; a 404 raises `FileNotFoundError`; nothing touches the network or `data/`.
- [ ] `test_refuses_archive_connection`: a connection with a row in `archive_ingest` raises; `tests/test_archive.py` and `tests/test_views_archive.py` pass unmodified.

## Out of scope

- Comparing these arrivals with the archive or the parquet, per-pid medians, any ADR-006 bound: the Phase 3 cross-source item, which also owns the same-day archive fixture.
- Stitching runs across midnight or deriving a service day; reading two day files as one.
- Days before 2026-08-13. Files exist back to 2022-05-19 (sampled), but ADR-009 bounds this source; history is a new decision.
- Coverage holes and the CSV edge in `cta/calendar.py` (calendar item); the refresh probe (Phase 3).
- A CLI script; `scripts/route_run_level.py` (Phase 1) calls the view function.
- Changing any archive threshold, the shared QA helper (`/qa` item), or `cta.mansueto`.
- Filtering by `bracket_gap_s` or `source` downstream; using `dly`, `des`, `tatripid`, `scrape_file`.

## Open questions

1. `TMSTMP_OFFSET_S = 46`: shift every fix by the measured mean truncation, as specified, or leave times unshifted and let the cross-source check report the bias? One day of evidence; the offset is unmeasured before 2026-09-28.
2. Route 47 has null `origtatripno` on 2026-10-22 (3,265 of 3,295 rows) and is dropped by the ADR-009 key. Accept for now, or fall back to `tatripid` (never null, upstream's key), which amends ADR-009?
3. `MAX_RAW_BRACKET_GAP_S`: 420 as specified, or 660 to keep arrivals across one missed poll and leave the filtering to `bracket_gap_s` downstream?
4. Is calendar-date `service_date` with midnight-split runs acceptable for the Phase 1 route views (routes 8, 65, 66), or should stitching be specced before they use this source?
