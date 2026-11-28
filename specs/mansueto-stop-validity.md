# Spec: Dated stop validity in the Mansueto adapter (routes 8 and 66)

Status: draft
Owner: Satoru  ·  Date: 2026-11-17. Revised 2026-11-18 to 11-21 (measured windows, fixtures, the measurement split out;
history in git). Revised 2026-11-27: the owner's review of the windows (ADR-014) is applied as reviewed entries in the
windows file. 2026-11-28: unobserved arrivals dropped (ADR-015), one run; `15341` on 9376 not served in the first detour.  ·  TODO item: Phase 1, Next — "Dated stop validity in the Mansueto adapter for routes 8 and 66
([ADR-011](DECISIONS.md), [ADR-014](DECISIONS.md)): have `cta.mansueto.clean_trips` drop arrivals dated before a stop's
reviewed `valid_from` …" (full text in TODO.md)
Tags: `kind:spec source:mansueto stage:clean topic:pattern-catalog topic:qa-table`

## Question

The Mansueto parquet has an arrival at every stop of today's route 8 and 66 detours for every run from 2024-09-03,
though the buses reached those streets only in late 2025. That is 2,127,091 arrivals on the four dominant patterns
(`docs/2026-11-15-routes-8-65-66-run-level-qa.md`). A wait at those stops describes another street, and a travel time
ending there rests on a road the bus was not on. `specs/stop-validity-measurement.md` measured, per stop, the date from
which the buses served it. The owner's review (ADR-014; `docs/2026-11-23-stop-validity-review-driving-and-corners.md`)
corrected 20 of those dates to where the buses drove and added one period when a stop was not served. This spec has the Mansueto adapter's pattern join drop the
earlier arrivals, as it already drops stops not in the pattern (ADR-011).

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Stop validity | `notebooks/routes_8_65_66_stop_validity.json` via `cta.stop_validity.load_stop_validity()` | `rows` (measured, `stop_validity.ROW_COLUMNS`) and the new `review` and `dropped_runs` lists (below) | committed; 38 measured rows |
| Mansueto trips | `cta.mansueto.read_trips`; the fixtures below | `cta.mansueto.TRIP_COLUMNS` | |
| Pattern stops | `cta.bustracker.pattern_stops_table` | `pid`, `stpid`, `seq`, `rtdir` | `getpatterns` fixtures in tests; the local cache for the rebuild |
| Full-history parquets | `data/mansueto/` (2.0 GB), local | `trips_<pid>_full.parquet` | the rebuild only |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Dropped runs | the JSON's top-level `dropped_runs`: `route`, `pid`, `vehicle_id`, `service_date`, `first_arrival_from`, `first_arrival_to` (Chicago clock times), `rule` ("ADR-015 point 2"), `evidence`, `decided`; all strings. One entry: 8, 9368, 1286, 2025-11-24, 18:15, 19:55, evidence `docs/2026-11-23-longest-pdist-dating.md` | one per run |
| Review entries | the JSON's top-level `review`: `route`, `direction`, `stop_id`, `from_pid`, `valid_from` (ISO day or null), `not_served` (list of `[from, to]` ISO days, inclusive; one entry has one), `rule` ("ADR-014 point 1" or "point 3"), `evidence` (a `docs/` path), `schedule_sha1` (list: the GTFS versions that first carried each change the entry dates, ADR-013 point 3), `decided` (ISO day); all strings | one per reviewed (pid, stop) |
| Loader | `load_stop_validity()` returns the applied windows: `ROW_COLUMNS` with `valid_from` the reviewed value where an entry exists, plus `measured_valid_from` and `not_served`; only keys with a window or an interval | object columns (`_object_frame`) | one per key |
| Writer | `cta.stop_validity.write_validity_file(rows, path)`: writes the measured rows and keeps the file's existing `review` and `dropped_runs`; raises when an entry names a (pid, stop) not among the rows. `scripts/route_run_level.py --write-validity` calls it | — | — |
| Adapter | `cta.mansueto.clean_trips(trips, pattern_stops, stop_validity=None)`: stage `pattern_join` gains `REASON_STOP_BEFORE_VALID_FROM = "stop_before_valid_from"`, `REASON_RUN_UNOBSERVED = "run_unobserved"`, and `REASON_STOP_NOT_SERVED = "stop_not_served"`. A loader `cta.stop_validity.load_dropped_runs()` returns the dropped runs, passed as `dropped_runs=None` (loads the committed list) beside `stop_validity`. `mansueto_view_from_trips` and `run_level_from_mansueto[_with_qa]` gain `stop_validity=None`, which loads the committed table (an empty frame applies none) | `CLEAN_COLUMNS`, `STAGES`, `RUN_LEVEL_COLUMNS` unchanged | one row per kept (run, stop) |
| CLI | `scripts/route_run_level.py --source mansueto` applies the table; `--no-validity` builds without windows, for re-measuring; `detour_stop_arrivals.csv` then counts the arrivals the windows kept | — | — |
| `/qa` case | `cta.qa_baseline.FIXTURE_CASES["mansueto_2025_10_14_routes8_65_66"]`: the 24 `getpatterns_ok` pids of `notebooks/routes_8_65_66_pids.json`; `_mansueto_case` gains `day=None` (`start=day`, `end` the next day); recorded in `tests/fixtures/qa_baseline.csv` | baseline rows | a new case; route 3 and 6410 rows do not move |
| QA note | `docs/<date>-routes-8-65-66-stop-validity-qa.md` (`/finding`) | route 8, 65 and 66 `pattern_join` totals against the 2026-11-15 note. Per dominant pid, `stop_before_valid_from` plus the rebuild's `arrivals_before_today_geometry` against that note's unwindowed counts (6662 636,909; 6665 884,215; 9368 354,954; 9376 251,013). Per review entry, the arrivals its date moved against the measured window. Runs whose `run_id` has no trailing date (expected 0) | — |

The 21 review entries the implementer writes (decided 2026-11-27, the last 2026-11-28; evidence:
`docs/2026-11-23-stop-validity-review-driving-and-corners.md`, and for the last row
`docs/2026-11-28-intersection-centre-and-drop.md`):

| `from_pid` | `stop_id` | `valid_from` (measured) | `rule` | `schedule_sha1` |
|---|---|---|---|---|
| 6662 | 17834, 5500, 739, 741, 742, 14762, 6712, 6713 | 2025-09-28 (2025-09-27) | point 1 | `a664d63ce34554f88476278df6a5b66c873db9ee` |
| 6662 | 6714 | 2025-09-28 (none) | point 3 | `a664d63ce34554f88476278df6a5b66c873db9ee` |
| 6665 | 6613, 6614, 5020, 769 | 2025-11-23 (2025-11-24) | point 1 | `14d83314a4f56f375d6336a4bb7528df4487b055` |
| 6665 | 18803 | 2025-11-23 (none) | point 3 | `14d83314a4f56f375d6336a4bb7528df4487b055` |
| 9368 | 15368, 2051, 15369, 5496, 17834, 5500 | 2025-11-23 (2025-11-25) | point 1 | `14d83314a4f56f375d6336a4bb7528df4487b055` |
| 9376 | 15341 | none (none); `not_served` 2025-08-17 to 2025-11-22 | point 3 | `e3ebf32877de205c8bf930c77bfb366c19901d48`, `14d83314a4f56f375d6336a4bb7528df4487b055` |

## Method

Prior art to copy: `cta/mansueto.py` `clean_trips` stage `pattern_join` (a reason inside an existing stage);
`cta/stop_validity.py` `_object_frame` and `load_stop_validity`; `tests/test_mansueto.py`
`test_clean_trips_analytic_case` and `test_qa_reasons_sum_to_rows_dropped_and_stages_chain`; `tests/test_views_mansueto.py`.

Preparatory refactor (no behaviour change, rule 7; no test edited; `/qa` shows no diff): the service-date rule at the
end of `clean_trips` becomes `_service_date(df)`, and the JSON writing in `scripts/route_run_level.py`
`write_validity` moves to `cta.stop_validity.write_validity_file`.

1. *Review*: the measured rows stay as measured, so a re-measure can be compared with them. The review records what
   the owner decided and why, and `load_stop_validity` applies it on top. Measured and reviewed dates keep separate
   provenance (CLAUDE.md, "When sources disagree").
2. *Adapter*: in `pattern_join`, after the join gives each row its `rtdir`, a row whose (`route`, `rtdir`, `stpid`) has a
   window and whose run's `_service_date` is before `valid_from` is dropped as `stop_before_valid_from`. A row whose
   date falls in a `not_served` interval is dropped as `stop_not_served`. One reason per row; the stage's reasons sum to
   its `rows_in − rows_out`. Every row of a run whose `vid`, `pid` and service date match a `dropped_runs` entry, and
   whose earliest arrival falls in its clock window, is dropped as `run_unobserved` first (ADR-015). The service date is the run id's trailing date, as Mansueto builds it; otherwise the
   Chicago date of the run's earliest row (the QA note counts such runs).
3. *Defaults*: `clean_trips` applies windows only when given them. The view functions load the committed table when
   `stop_validity` is `None`; `--no-validity` passes an empty frame.
4. `scripts/route_run_level.py --source mansueto` is run once for routes 8, 65 and 66, and the QA note is written.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| Validity windows | each key's applied `valid_from`: measured, or reviewed where an entry exists | `specs/stop-validity-measurement.md`; ADR-014 and the review table | per stop; the QA note counts each entry's effect |

New exclusions: `stop_before_valid_from`, `run_unobserved` (one run) and `stop_not_served` (one interval) (Rule 2; this
spec, the QA table and the `/qa` baseline carry them; ADR-011 point 3, ADR-014 and ADR-015 record the decisions).

## Fixtures

Unchanged from the 2026-11-21 build: `tests/fixtures/mansueto_2025-10-14_routes8_65_66.parquet` (57,074 rows) and
`mansueto_2025-12-02_routes8_65_66.parquet` (58,464 rows), the 24 `getpatterns` files, manifest
`tests/fixtures/mansueto_routes8_65_66.manifest.json`. On 2025-10-14, route 66 eastbound is past its change, westbound
between its two, and route 8 between its two. 2025-12-02 is after every window and interval. The JSON gains its
`review` list in this spec's commit.

## Acceptance tests

- [ ] `test_clean_trips_stop_validity_hand_built` (`tests/test_mansueto.py`): route `r1` Eastbound patterns `p1` (a, b,
      c) and `p2` (b, c, d), `p3` Westbound (c), route `r2` (c); window (`r1`, Eastbound, c) from 2025-09-27. Dropped as
      `stop_before_valid_from`: c on runs dated 2025-09-26, one at 00:30 Chicago on 09-27. Kept: c on 09-27, c on `p3`
      and `r2`, every other stop. (`r1`, Eastbound, b) not served 2025-09-10 to 09-12 drops b on 09-11 as
      `stop_not_served` and keeps it on 09-13. `pattern_join` reasons sum to `rows_in − rows_out`;
      `stop_validity=None` gives the output without this spec. A `dropped_runs` entry for one vehicle, pid, date and
      clock window drops all of that run's rows as `run_unobserved` and nothing of the vehicle's other runs that day.
- [ ] `test_load_stop_validity_applies_review` (`tests/test_stop_validity.py`, a hand-built file in `tmp_path`): a
      review `valid_from` replaces the measured one, kept in `measured_valid_from`; an entry gives a window to a row
      with none; `not_served` comes back as pairs; an entry naming a stop not among the rows raises; and
      `write_validity_file` keeps the `review` list when it rewrites the rows.
- [ ] `test_stop_validity_review_snapshot` (committed JSON). 21 entries, each with `rule`, `evidence`, `decided` and a
      list of 40-hex `schedule_sha1`. The applied windows equal the review table: 31 windows and one interval. The measured rows are
      unchanged (`test_stop_validity_snapshot` still passes).
- [ ] `test_view_stop_validity_default_and_empty`. One hand-built run, dated the day before the first loaded key's
      `valid_from`. `stop_validity=None` drops it (one `stop_before_valid_from`), as the loaded frame does; an empty
      frame keeps it.
- [ ] `test_mansueto_view_fixture_2025_10_14`. A key whose applied `valid_from` is after 2025-10-14 has no arrival,
      including Wells & Chicago (6665 `18803`); `15341` on 9376 has none either, dropped as `stop_not_served`
      (~270; estimate, measure, then pin). Other keys keep every arrival of the build with an empty table.
      `stop_before_valid_from` is ~4,000 on routes 8 and 66 together (estimate; measure, then pin) and 0 on route 65.
- [ ] `test_mansueto_view_fixture_2025_12_02`: no `stop_before_valid_from`, `run_unobserved` or `stop_not_served` on any of the 24 pids;
      the view equals the build with an empty table.
- [ ] `test_baseline_matches_fixtures` (existing): passes with the new case recorded and the `mansueto_route3` and
      `mansueto_6410` rows not re-recorded.

## Out of scope

- Re-dating windows from GPS positions in `cta/` (TODO item "Dated pattern stop tables from the archived GTFS"), and
  editing the measured rows or `specs/stop-validity-measurement.md`'s method.
- One source per day and the reader (`specs/run-level-reader.md`); the raw-CSV and archive adapters, which impute
  against today's geometry.
- A section-jump count in `cta/` for finding unreported days on other routes (Phase 2), and a flag column on the view.
- Routes beyond 8, 65 and 66; route 65 (no geometry change); waits, headways and event days.

## Decisions (owner)

- 2026-11-18: route 8 in the 2025-10-14 fixture. 2026-11-19: the window is pattern metadata applied by the Mansueto
  adapter (ADR-011). 2026-11-21: the measurement is its own spec; the 2025-12-02 fixture covers all three routes.
- 2026-11-23: dates follow where the buses drove; a corner served under any stop id is served (ADR-014).
- 2026-11-27: the 18 date moves, the windows for `6714` and `18803`, and the five same-corner rows kept, all
  confirmed. The review is recorded in the JSON, with evidence, and applied by this spec, not re-measured in code.
- 2026-11-28: the unreported days are dropped (ADR-015). Measured, every stop the pings skipped is already windowed, so
  the decision adds one run (`docs/2026-11-28-intersection-centre-and-drop.md`).
- 2026-11-28: `15341` on 9376 is not served from 2025-08-17 to 2025-11-22. No stop served the intersection
  northbound then: a stop at the Blue Line transfer would be well used and would show as a dwell, and within 100 ft of
  the centre none exceeds 3 s. Riders walked a block to the Blue Line.

## Open questions

None. All were answered by the owner on 2026-11-27 and 2026-11-28.
