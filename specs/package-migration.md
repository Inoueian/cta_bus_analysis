# Spec: Move importable helpers into a `cta/` package, add CI

Status: ready (open questions answered by the owner 2026-11-04; see below)
Owner: Satoru  ·  Date: 2026-11-03  ·  TODO item: Foundation — "Package + tests + CI (ADR-005): create `cta/`, move `notebooks/cta_api.py`, `dlsd_run_quality.py`, `michigan_ave_segment.py` with tests passing; add `.github/workflows/ci.yml` (pytest, no network)."

## Question

Give agents and humans one stable import surface (`import cta.<module>`) and an automated test
gate, so later specs (archive adapter, Mansueto adapter, calendar) can add tested code without
the `sys.path` hacks that notebooks, scripts and tests use today. Pure restructuring: no
behaviour change, no new features.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Helper modules | `notebooks/cta_api.py` (Bus Tracker + Mansueto URL helpers, budget, caches), `notebooks/dlsd_run_quality.py`, `notebooks/michigan_ave_segment.py` | ~1,500 lines; cross-imports: `dlsd_run_quality` ← `cta_api`; `michigan_ave_segment` ← `cta_api`, `dlsd_run_quality` | `repo_root()` in each is `Path(__file__).resolve().parent.parent`; same depth under `cta/`, so unchanged |
| Their consumers | 9 notebooks (`grep -l "cta_api\|dlsd_run_quality\|michigan_ave_segment" notebooks/*.ipynb`), `scripts/dlsd_weekday_friday_summary.py`, `tests/test_cta_api.py`, `tests/test_dlsd_run_quality.py`, `tests/test_michigan_ave_segment.py` | each inserts `notebooks/` on `sys.path` then imports by bare module name | `tests/conftest.py` already puts the repo root on `sys.path` |
| Existing tests | `tests/` | 48 tests, all mocked, no network | must pass before and after, same count |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| Package | `cta/__init__.py` (empty docstring only), `cta/cta_api.py`, `cta/dlsd_run_quality.py`, `cta/michigan_ave_segment.py` | identical public names to today (see Method 1) | — |
| Packaging | `pyproject.toml` with `[project] name = "cta-bus-analysis"`, `requires-python = ">=3.11"`, dependencies from `requirements.txt`, setuptools `packages = ["cta"]` | — | — |
| CI | `.github/workflows/ci.yml` | ubuntu, Python 3.12, `pip install -r requirements.txt`, `pytest -q` | on push and pull_request |
| Updated consumers | 9 notebooks (import cell only), 1 script, 3 test files, `tests/conftest.py` | imports become `from cta.<module> import ...` | — |
| QA table | in the implementation report, not code: file moved → old path gone, new path present, test count before/after | — | one row per moved module |

## Method

1. `git mv` each helper from `notebooks/` to `cta/`. Keep module names for now (renaming to
   `bustracker`, `mansueto`, `dlsd`, `michigan` is a separate, later change; see Open questions).
   Keep every public name, constant and signature identical.
2. Rewrite the three cross-imports as absolute package imports (`from cta.cta_api import ...`).
3. `tests/conftest.py`: keep the repo-root `sys.path` insert (it makes `import cta` work without
   installing). Remove the per-file `NOTEBOOKS` `sys.path` inserts from the three test modules and
   change their imports to `cta.<module>`.
4. `scripts/dlsd_weekday_friday_summary.py`: replace its `notebooks/` path insert with a repo-root
   insert and import from `cta`. Check `scripts/cache_dlsd_parquets.py` for duplicated constants
   (`BASE`, `RT_TO_PID_URL`, `parquet_url`); leave them, note the duplication in the report.
5. Notebooks: edit only the cell that inserts `notebooks/` on `sys.path` and imports the helpers.
   Replace with a repo-root insert (`REPO_ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()`)
   and `from cta.<module> import ...`. Do not re-execute notebooks; do not touch outputs.
6. Add `pyproject.toml` so `pip install -e .` works; README's install section gains that line.
7. Add `.github/workflows/ci.yml` (contents in Outputs). CI must not need secrets or network.
8. Update CLAUDE.md's layout note (the paragraph starting "This is the target layout") to say
   `cta/` now exists and names the three modules; `docs/` already exists.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|
| none | — | pure restructuring; no numeric thresholds are introduced or changed | — |

## Acceptance tests

- [ ] `pytest -q` passes with exactly the same number of tests as before the move (48 at spec time) and no test is skipped or xfailed.
- [ ] `python -c "import cta.cta_api, cta.dlsd_run_quality, cta.michigan_ave_segment"` succeeds from the repo root with no `sys.path` manipulation.
- [ ] `ls notebooks/*.py` lists nothing (no importable code under `notebooks/`, per CLAUDE.md).
- [ ] New test `tests/test_package_layout.py`: (a) every module in `cta/` imports; (b) no `.ipynb` under `notebooks/` contains the string `"notebooks"` inside a `sys.path.insert` call; (c) `cta.michigan_ave_segment.repo_root()` equals the repo root.
- [ ] `python scripts/dlsd_weekday_friday_summary.py -h` exits 0.
- [ ] `pip install -e .` succeeds in a fresh venv (checked manually by the implementer; CI installs from `requirements.txt` only).
- [ ] CI workflow runs on the PR and is green.
- [ ] Report contains the QA table: for each of the three modules, old path absent, new path present, public-name set identical (compare `dir()` filtered to non-underscore names before and after).

## Out of scope

- Renaming modules or functions, splitting `cta_api.py` into Bus Tracker vs Mansueto parts.
- Introducing DuckDB, the archive adapter, the calendar module, or `docs/` migration.
- Re-running notebooks or changing any cell other than the import cell.
- Deduplicating constants between `scripts/cache_dlsd_parquets.py` and `cta/cta_api.py`.
- Adding type checking, linting or formatting tools to CI.

## Open questions

Both resolved by the owner on 2026-11-04.

- Keep the module names (`cta.cta_api`, `cta.dlsd_run_quality`, `cta.michigan_ave_segment`) or
  rename now to `cta.bustracker`, `cta.dlsd`, `cta.michigan`? **Keep now.** The migration is a pure
  move. The rename happens in the spec that splits `cta_api.py` into `cta.bustracker` (Bus Tracker
  client, budget, `getpatterns` cache; absorbs the cache reader in `cta/patterns.py`) and
  `cta.mansueto` (CloudFront URL helpers). Queued in TODO.md under Foundation; spec to write.
- Should CI also execute one notebook headlessly as a smoke test? **Not yet.** Seven of ten
  notebooks read Mansueto parquets or derived tables under the gitignored `data/`, the other three
  call the Bus Tracker API live, and CI has neither network nor `data/`. Revisit once a notebook
  exists that runs entirely off `tests/fixtures/` (the archive adapter fixtures make that possible).
