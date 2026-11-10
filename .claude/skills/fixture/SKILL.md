---
name: fixture
description: Build or rebuild a committed test fixture under tests/fixtures/ from a public file, with its manifest (source URL, bytes, SHA-256, rows, fetch time). Use when a spec names a fixture that does not exist, when the user says "build the fixture for", "cut a fixture from", "refresh the getpatterns fixture", or when /implement finds a fixture missing. Enforces the one-archive-day limit, refuses if the source moved, and prints every deviation from the spec's estimates.
---

# /fixture — cut a committed fixture from a public file

Arguments: the spec the fixture serves (`specs/<slug>.md`), or a one-line ask naming the source, the
cut (pids, route, day, window) and the fixture file name. With no argument, ask for the spec.

A fixture is a small, deterministic cut of one public file (or one archive day) that tests read
offline. Its manifest is what makes it a fixture rather than a sample: anyone can re-fetch the source,
re-cut, and get the same bytes, or learn that the source moved. The two existing builders are the
specification; this skill is the procedure for writing the next one, not a generic script.

## Before building

1. Read `CLAUDE.md` Rules 3 and 4, the spec's Inputs, Fixtures and Acceptance tests sections (specs
   written before the template had a Fixtures section describe fixtures in a paragraph under Acceptance
   tests, as `specs/mansueto-adapter.md` does), and the playbook entries for the source:

   ```
   grep -n 'Tags:.*source:<x>' docs/playbook.md          # gotchas and patterns for this source
   grep -n '~[0-9]\|estimate' specs/<slug>.md             # every number the fixture must measure
   ```

2. Pick the prior art by source and copy its shape, not its constants:

   | Source | Copy | Source-moved guard | Manifest |
   |---|---|---|---|
   | Transit Alerts archive (`positions/bus/…ndjson.gz`) | `scripts/build_archive_fixtures.py` `build_day_fixture` | `index.json` `sha256` and `rows` for the day, via `cta.archive.ensure_day_file` | same shape as `index.json` (`days[].files.bus.{path,rows,bytes,sha256}`, `known_gaps`), so `cta.archive.ingest_day` verifies it unchanged |
   | Mansueto parquet (`processed_by_pid/trips_<pid>_full.parquet`) | `scripts/build_mansueto_fixtures.py` `ensure_source`, `cut_one_day`, `cut_last30d` | `Last-Modified` on `cta.mansueto.MANSUETO_DATA_EDGE` and last row within `MAX_EDGE_LAG_DAYS` of it; footer `rows` equals a scan | `mansueto.manifest.json` (`sources` per pid with the `data_edge` dict, `files` per fixture) |
   | Mansueto raw day CSV (`full_day_data/YYYY-MM-DD.csv`) | the Mansueto builder's structure; `cta.mansueto.http_head` + `download` | none upstream (no manifest, ADR-009): record `bytes` and `Last-Modified` from a HEAD at build time and refuse on a later rebuild if either differs | same core as Mansueto, `sources` keyed by day |
   | Bus Tracker `getpatterns` | `scripts/build_archive_fixtures.py` `build_getpatterns_fixture` | add-only: `getpatterns_to_write` fetches only pids with no committed file; `--refresh` overwrites, and is a deliberate change (below) | the JSON files themselves; the builder prints files added, files left untouched and live calls spent against the 10k/day budget |

3. Check `tests/fixtures/` for a fixture that already covers the ask (same source, superset of pids
   or days). Reuse it and stop; a second fixture of the same rows costs every clone a download.

## Rules the builder enforces

- **One archive day** (Rule 3), ever, per builder run and per fixture. A spec that needs two days needs
  two specs or a synthetic fixture. Mansueto parquets are not archive days, but the full files are up to
  400 MB each: fetch into `data/` (gitignored) with `cta.mansueto.fetch_parquet`, never into
  `tests/fixtures/`, and cut by row group as `cut_one_day` does.
- **Refuse if the source moved.** Before cutting, compare the source against the guard in the table above
  and exit with the mismatch (what the manifest or module constant says, what the bucket says now, and
  which ADR or note to re-measure: ADR-007 for the parquet edge, ADR-009 for the raw CSVs, the
  `index.json` `generated_at` for the archive). Never widen the guard to make a build pass; a moved
  source is a finding (`/finding`) before it is a fixture.
- **Deterministic bytes, within one environment.** gzip with `mtime=0, filename=""`; parquet sorted by
  (run, sequence, time) and written with `compression="zstd"`; CSV rows in source order; JSON with
  `indent=1` and a trailing newline. Running the builder twice on an unchanged source in the same
  environment must give fixture files with identical SHA-256s; check it once and say so in the report.
  Two things are expected to differ and are not a failure: the manifest (`built_at`, `fetched_at`), and
  parquet bytes across library versions (pyarrow writes its version into the file's `created_by`
  field). A rebuild that changes a parquet SHA-256 but not its rows, columns or values is a library
  change; say so, and record the pyarrow version in the report.
- **Rows kept verbatim.** A fixture filters rows (by pid, route, day, window); it never edits columns,
  renames, re-types or drops nulls. Cleaning is the adapter's job and the QA table must see the raw rows.
  The one exception is a byte-range sample (the parquet footer) which is labelled as such.
- **Committed getpatterns files are not refreshed in passing.** Patterns drift (route 3 lost 108 + 113
  stops between July and November 2026, `docs/2026-11-04-mansueto-adapter-qa.md`), and every adapter
  test joins on these files, so overwriting them moves pinned numbers in both adapters at once. Adding
  pids is routine. `--refresh` is a Rule 2-sized change: only when the owner asks for it, with the
  before/after test numbers in the report and the spec(s) whose pinned values moved updated.
- **Tests never build.** The builder lives in `scripts/build_<source>_fixtures.py`, reads `.env` only for
  `CTA_API_KEY` (never printed, Rule 5), and tests read only what is committed. `data/` is never committed
  (Rule 4).
- **Size.** Aim under 1 MB per file, under 5 MB per spec; state the measured size in the report. A cut
  that cannot get there (a route's whole history) is the wrong fixture: cut a window or a day.

## Manifest

Every fixture has one, next to it or in the source's shared manifest. There are two shapes, one per
bucket; do not unify them, and add keys rather than rename.

- **Archive**: the `index.json` shape, because `cta.archive.ingest_day` verifies the fixture against it
  exactly as it verifies a real day: `title`, `source_index_generated_at`, `timezone`, `source_day`
  (the published day's `path`, `rows`, `bytes`, `sha256`), `filter`, `known_gaps`, and `days[].files.bus`
  (`path`, `rows`, `bytes`, `sha256` of the fixture). Copy `archive_2026-10-29_michigan.index.json`.
- **Mansueto bucket** (parquets, `rt_to_pid.csv`, raw day CSVs): copy `mansueto.manifest.json`:

  ```
  title        what and for which spec                 builder     scripts/build_<source>_fixtures.py
  built_at     UTC ISO timestamp
  sources      per source file: url, bytes, last_modified, fetched_at, and the guard values
               (parquet: data_edge dict; raw CSV: HEAD bytes and last_modified)
  files        per fixture file: rows, bytes, sha256, the cut (pids, route, day or window, timezone)
  ```

- **getpatterns**: no manifest; the files are the raw API responses, named `getpatterns_<pid>.json`.

Record every self-check the builder runs as a dict under the file entry
(`service_date_check` in the Mansueto manifest is the model), so the test that pins the number can
cite the manifest instead of re-deriving it.

## Deviations from the spec

Before writing, measure every number the spec marks `~N` or "(estimate; measure, then pin)" on the cut:
rows, bytes, runs, pids present, null counts, the per-stage QA counts if the adapter exists. Print one
table:

| Spec line | Estimate | Measured | Note |
|---|---|---|---|

An unmarked number that the fixture contradicts is not corrected here: print it under the same table
with "requirement" in the note and let the owner or `/implement` decide. Pids or days the spec names
that return 404 or are absent from the catalog (route 65's 7906/7907, route 10 in `rt_to_pid.csv`)
are deviations too; list them with the HTTP status.

## Order of work

1. Write or extend the builder under `scripts/`, module docstring with examples that `-h` prints
   (pattern "Add a CLI entry point" in `docs/playbook.md`), every constant named with its evidence.
2. Run it. Read the printed guard checks, the deviation table and the byte counts.
3. Run it again; the SHA-256s must not change.
4. Run `python -m pytest -q`. Existing fixture tests must still pass (a rebuilt fixture that changes
   pinned numbers is a spec change, Rule 2, not a fixture change).
5. `git status --porcelain | grep -E '^.. data/'` must print nothing.

## After

- The spec's Fixtures section (or, in an older spec, its fixture paragraph) gets the measured rows,
  bytes and SHA-256 prefix and a "Built YYYY-MM-DD by `scripts/…`" line; estimates it carried are
  re-marked as measured.
- If the deviation table changed a number the spec relied on, or the source moved, record it with
  `/finding` (a dated note; the Mansueto QA note shows the shape under "Data facts that corrected the
  spec").
- If the fixture replaces one a test reads, update the test's path and nothing else in it.
- Update the playbook pattern "Build a committed fixture from a public file" if the builder taught a
  new guard or cut.
- TODO.md edits follow `/todo`.

## Report

The fixture paths with rows, bytes and SHA-256; the manifest path; the guard values checked and their
result; the deviation table; getpatterns files added (and, after an owner-requested `--refresh`, the
test numbers that moved); live calls spent; the determinism check with the pyarrow version; pytest's
summary line; every file touched outside `scripts/` and `tests/fixtures/` and why.
