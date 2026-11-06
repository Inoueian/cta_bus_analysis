# Spec: Split `cta.cta_api` into `cta.bustracker` and `cta.mansueto`

Status: done (implemented 2026-11-04, commit d2aa39b on branch `claude/epic-babbage-5ivl4f`)
Owner: Satoru  ·  Date: 2026-11-04  ·  TODO item: Foundation — "Split `cta.cta_api` into `cta.bustracker` (API client, daily budget, throttle, `getpatterns` fetch and disk cache; fold in the cache reader `cta/patterns.py` so the cache format has one owner) and `cta.mansueto` (`parquet_url`, `parquet_http_status`, `RT_TO_PID_URL`); update importers (notebooks' import cell only), keep every public name. After the package migration. Spec: `specs/split-cta-api.md` (to write)."
Tags: `kind:spec source:bustracker source:mansueto topic:process`

## Question

Give each data source (ADR-004) one module named after it, so the Mansueto adapter spec has a
home (`cta/mansueto.py`) and the `getpatterns` cache format has a single owner instead of two
(`cta_api.py` writes it, `patterns.py` reads it, each with its own path helper and parser).
Pure restructuring: no behaviour change, no new features, every public name kept. Deferred from
`specs/package-migration.md` (Open questions, resolved 2026-11-04: "keep now, rename in the split").

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Source modules | `cta/cta_api.py` (324 lines), `cta/patterns.py` (86 lines) | public names listed under Method 1–2 | both define `repo_root()` and the cache dir `data/cta_api_cache` |
| Package importers | `cta/dlsd_run_quality.py` (`BASE`, `parquet_url`), `cta/michigan_ave_segment.py` (`RT_TO_PID_URL`, `batch_pattern_stops`), `cta/views.py` (`patterns.pattern_stops_table`) | — | absolute imports, rewritten in place |
| Script importers | `scripts/build_archive_fixtures.py` (`cta_api.*`), `scripts/archive_run_level.py` (`patterns.pattern_stops_table`; docstring names `cta_api`) | — | — |
| Notebook importers | `notebooks/dlsd_travel_time_146_147.ipynb`, `dlsd_stop_discovery_rush_routes.ipynb`, `michigan_ave_stop_discovery.ipynb` | each has one `from cta.cta_api import (...)` in its first code cell | import cell only |
| Tests | `tests/test_cta_api.py` (6 tests), `tests/test_views_archive.py` (imports `patterns`), `tests/test_package_layout.py` (`LEGACY_MODULES`) | 68 tests total, no network | same assertions after the move |
| Fixture | `tests/fixtures/getpatterns/getpatterns_<pid>.json` (45 files, fetched 2026-11-03) | raw `bustime-response` roots | already committed; no new fixture |
| Prose | `CLAUDE.md` Layout paragraph, `README.md` layout tree (still lists `notebooks/cta_api.py`: stale since the package migration), `cta/patterns.py` docstring | — | — |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Bus Tracker module | `cta/bustracker.py` | every public name from `cta_api.py` except the Mansueto ones, plus every public name from `patterns.py` (Method 1) | — |
| Mansueto module | `cta/mansueto.py` | `BASE`, `RT_TO_PID_URL`, `CLOUDFRONT_MIN_INTERVAL_SEC`, `parquet_url`, `parquet_http_status` (Method 2) | — |
| Removed | `cta/cta_api.py`, `cta/patterns.py` | — | see Open questions (no shim) |
| Tests | `tests/test_bustracker.py` (the 6 tests from `test_cta_api.py` plus the acceptance tests below), `tests/test_mansueto.py` (`parquet_url`) | — | — |
| QA table | in the implementation report: one row per public name: `old_module`, `name`, `new_module`, `reason` ∈ {`moved`, `merged_duplicate`, `alias`} | — | one row per name; `moved + merged_duplicate + alias == names_in`, and `names_out == moved + alias` |

Identifiers stay strings; nothing here touches timestamps.

## Method

1. `git mv cta/cta_api.py cta/bustracker.py`, then delete the Mansueto names from it (step 2) and
   fold in `patterns.py`. Public names kept in `cta.bustracker`: `CHICAGO`, `CTA_API_BASE`,
   `CTA_API_MIN_INTERVAL_SEC`, `CTA_API_DAILY_WARN`, `CTA_API_DAILY_MAX`, `CTA_API_MAX_RETRIES`,
   `CTA_API_RETRY_BASE_SEC`, `LAST_CTA_REQUEST_URL`, `repo_root`, `api_cache_dir`, `load_dotenv`,
   `daily_api_request_count`, `cta_api_get`, `ptr_to_stops_df`, `pattern_stops_from_ptr`,
   `pattern_records`, `batch_pattern_stops`; from `patterns.py`: `PATTERN_STOP_COLUMNS`,
   `default_cache_dir`, `cache_path`, `load_getpatterns`, `stops_from_getpatterns`,
   `pattern_stops_table`. Private names tests touch (`_chicago_today`, `_save_request_log`,
   `_increment_daily_counter`, `_save_getpatterns_cache`, `_last_api_call_monotonic`) keep their names.
2. `cta/mansueto.py` gets `BASE`, `RT_TO_PID_URL`, `CLOUDFRONT_MIN_INTERVAL_SEC`,
   `_throttle_cloudfront` (and its monotonic state), `parquet_url`, `parquet_http_status`, verbatim.
   `bustracker` must not import `mansueto` and vice versa.
3. One owner for the cache format. Three duplicate pairs collapse to one implementation each, the
   second name kept as an alias (QA reason `alias`): `default_cache_dir = api_cache_dir`;
   `cache_path(pid, cache_dir)` is the implementation and `_getpatterns_cache_path` is removed
   (private, QA reason `merged_duplicate`); `_load_getpatterns_cache` is replaced by the public
   `load_getpatterns(pid, cache_dir)` (`merged_duplicate`). `stops_from_getpatterns` is rewritten
   to call `ptr_to_stops_df` per pattern and prepend `pid`, `rtdir`; output identical to today
   (acceptance test 3). `repo_root` appears once, in `bustracker` (`patterns.repo_root` is a `merged_duplicate`); `mansueto`
   has no need of it.
4. Rewrite importers: the three package modules, two scripts (and the `archive_run_level.py`
   docstring), the three notebooks' import cell (`from cta.cta_api import (...)` becomes two
   statements, `from cta.bustracker import (...)` and `from cta.mansueto import (...)`; no other
   cell changes; outputs untouched). `scripts/cache_dlsd_parquets.py` keeps its own copies of
   `BASE` / `parquet_url` (Out of scope, as in the previous spec).
5. Tests: `git mv tests/test_cta_api.py tests/test_bustracker.py`, retarget `monkeypatch.setattr`
   calls; move `test_parquet_url_basic` to `tests/test_mansueto.py`; `tests/test_views_archive.py`
   imports `bustracker` for `pattern_stops_table`; `tests/test_package_layout.py`:
   `LEGACY_MODULES` becomes `("bustracker", "mansueto", "dlsd_run_quality", "michigan_ave_segment")`
   and the bare-import regex additionally forbids `cta.cta_api` and `cta.patterns` in notebooks.
6. Prose: `CLAUDE.md` Layout paragraph names the new modules; `README.md` layout tree moves the
   three helpers under `cta/` with the new names (fixes the stale `notebooks/` entries); the
   `patterns.py` docstring sentence about the cache owner moves to the `bustracker` module docstring.
7. Run `pytest` (expect 68 + new acceptance tests, zero failures), then produce the QA table from
   the inventory in steps 1–3.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| none new | — | every constant above moves verbatim (`CTA_API_DAILY_MAX = 10_000` etc.; evidence unchanged, see `cta_api.py` docstring) | an implementer changing any value here is a spec violation |

## Acceptance tests

Each becomes one pytest; all offline; fixtures named.

1. **Name inventory.** A frozen list in the test of the 23 public `bustracker` names and 5 `mansueto`
   names above: each is importable from its module, and for every function the
   `inspect.signature` equals the pre-split signature recorded in the test (hand-copied from
   `cta_api.py` / `patterns.py` at HEAD `12f0aeb`). `cta.bustracker` and `cta.mansueto` do not
   import each other (`sys.modules` check after a fresh import).
2. **Legacy modules gone.** `importlib.import_module("cta.cta_api")` and `("cta.patterns")` raise
   `ModuleNotFoundError`; `tests/test_package_layout.py` finds no notebook cell importing them.
3. **Parser equivalence (analytic).** Hand-built root with two patterns, each with waypoints
   (`typ == "W"`) and stops in shuffled `seq`: `stops_from_getpatterns` returns 4 rows sorted by
   (`pid`, `seq`), `pdist_ft` float, `stpid` string, and equals `ptr_to_stops_df` per pattern after
   dropping `pid`, `rtdir`. Then on the 45 fixture files: `pattern_stops_table(KEPT, GETPATTERNS_DIR)`
   has the same row count and column set as `test_views_archive.py` obtains today.
4. **One cache path.** `cache_path("7107", d)` is the file `batch_pattern_stops` writes (mocked
   `urlopen`, `use_cache=True`) and `load_getpatterns("7107", d)` reads back the same root.
5. **QA-table case.** The implementation report's table satisfies
   `moved + merged_duplicate + alias == names_in` (29 public: 22 from `cta_api`, 7 from `patterns`, where
   `patterns.repo_root` is the public `merged_duplicate`; plus 2 private merged) and
   `names_out == moved + alias`; the test encodes the same inventory as a dict and asserts the sums.
6. **Existing tests unchanged.** The 6 tests from `test_cta_api.py` pass with only the module
   reference changed; total test count ≥ 68 + 5.
7. **Scripts smoke.** `python scripts/archive_run_level.py -h` and `scripts/build_archive_fixtures.py -h`
   exit 0 (both import the new modules at top level).

## Out of scope

- Any behaviour change: budget, throttle, retry, cache file format, printed progress lines.
- Deduplicating `scripts/cache_dlsd_parquets.py` against `cta.mansueto` (its 3 tests stay as they are).
- Renaming `dlsd_run_quality` or `michigan_ave_segment`, or splitting `michigan_ave_segment.py`.
- Touching the Mansueto parquet readers in `dlsd_run_quality.py` / `michigan_ave_segment.py`; the
  Mansueto adapter spec owns those.
- Re-running notebooks; any cell other than the import cell.
- A compatibility shim `cta/cta_api.py` re-exporting the new modules (see Open questions).

## Open questions

Both resolved by the owner on 2026-11-04.

- **Shim or clean removal?** **Clean removal** (acceptance test 2 as written). Every importer is in
  this repo and is updated in the same change; a shim would leave two names for one thing, which is
  what the previous spec deferred this rename to fix.
- **`load_dotenv` home.** **`bustracker`** (it exists to load `CTA_API_KEY`). No `cta/env.py`.
