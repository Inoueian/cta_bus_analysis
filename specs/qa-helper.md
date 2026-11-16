# Spec: Shared QA-row helper (`cta/qa.py`)

Status: done (implemented 2026-11-16 on branch `claude/clever-keller-9knigq`)
Owner: Satoru  ·  Date: 2026-11-16  ·  TODO item: Foundation — "Shared QA-row helper (`cta/qa.py`): move `cta.mansueto.qa_rows`, `QA_COLUMNS` and `stage_totals` from `scripts/route_run_level.py` into one module that imports nothing from `cta`; `cta.archive._record_qa` builds its rows with it and the old names stay as aliases, so the additivity check exists once instead of three times. A refactor: no QA table or view moves on the committed fixtures (Rule 7). Split out of the `/qa` item on 2026-11-16 because it adds a module to the `cta/` import surface; unblocks that item and gives the stop-level view's stages one helper to call. Spec: specs/qa-helper.md (draft)."
Tags: `kind:spec stage:qa topic:qa-table topic:process`

## Question

Give the QA arithmetic one owner, so that a stage added tomorrow (the stop-level view's, the `/qa` baseline's)
calls one helper and a fix to the additivity check lands once. Today the check is written three times:
`cta.mansueto.qa_rows` (in memory), `cta.archive._record_qa` (DuckDB) and `stage_totals` in
`scripts/route_run_level.py` (summing over calls), with a fourth copy in a notebook. Pure restructuring: no
QA number, view row or public name changes. `specs/qa-skill.md` waits for this.

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| Row builder | `cta/mansueto.py` `qa_rows`, `QA_COLUMNS` | `stage, rows_in, rows_out, reason, count` | imported from `cta.mansueto` by `cta/calendar.py`, `cta/michigan_ave_segment.py`, `cta/dlsd_run_quality.py`, `cta/views.py`, `scripts/route_run_level.py` |
| DuckDB recorder | `cta/archive.py` `_record_qa`, `QA_COLUMNS` | same five columns plus `archive_date`, `seq` in `archive_qa` | also called by `cta/mansueto_raw.py` (twice) |
| Summing | `scripts/route_run_level.py` `stage_totals` | per-call QA table → one row per (group, stage) | used by `tests/test_route_run_level.py` as `rrl.stage_totals` |
| Notebook copy | `notebooks/eda_routes_8_65_66.ipynb` `stage_table` | — | left as it is (Out of scope) |
| Fixture | `tests/fixtures/mansueto_2026-07-27_route3.parquet`, `tests/fixtures/getpatterns/` | existing | no new fixture |
| Prose | `CLAUDE.md` Layout paragraph; `docs/playbook.md` pattern "Emit a QA table from a pipeline stage" | — | the pattern still calls the helper a TODO item |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| QA columns | `cta.qa.QA_COLUMNS` | `["stage", "rows_in", "rows_out", "reason", "count"]` | — |
| Row builder | `cta.qa.qa_rows(stage, rows_in, rows_out, reasons) -> list[dict]` | keys = `QA_COLUMNS`; `rows_in`, `rows_out`, `count` int; `reason` str or None | one row per non-zero reason, one `None` row when nothing dropped; raises `AssertionError` when counts do not sum to `rows_in - rows_out` |
| Summing | `cta.qa.stage_totals(qa, by, call_keys) -> DataFrame` | index `by + ["stage"]`; `rows_in`, `rows_out` int64, one int64 column per reason | one row per (group, stage) |
| Aliases | `cta.mansueto.qa_rows`, `cta.mansueto.QA_COLUMNS`, `cta.archive.QA_COLUMNS`, `scripts.route_run_level.stage_totals` | the `cta.qa` objects themselves | — |
| Tests | `tests/test_qa.py` | — | — |
| Prose | `CLAUDE.md` Layout paragraph and the `cta/__init__.py` module list name `cta/qa.py`; playbook pattern rewritten with `/finding` to point at `cta.qa` | — | — |
| QA table | in the report: `old_module, name, new_module, reason` ∈ `moved_with_alias`, `merged_duplicate` | four rows: `moved_with_alias` for `cta.mansueto.qa_rows`, `cta.mansueto.QA_COLUMNS`, `scripts.route_run_level.stage_totals`; `merged_duplicate` for `cta.archive.QA_COLUMNS` | one row per name; all four stay importable, so `names_in == names_out == 4` |

## Method

Prior art to copy: `specs/split-cta-api.md` (the shape of a refactor spec and its name-inventory QA table);
`cta/mansueto.py` `qa_rows` (moves verbatim); `tests/test_mansueto.py`
`test_qa_reasons_sum_to_rows_dropped_and_stages_chain`. Playbook patterns "Emit a QA table from a pipeline
stage" and "Check that a refactor changed nothing".

1. `cta/qa.py` holds `QA_COLUMNS`, `qa_rows` and `stage_totals`, moved verbatim, except that `stage_totals`
   raises `AssertionError` explicitly instead of using a bare `assert` (`python -O` strips those; same
   exception under pytest). It imports nothing from
   `cta` (every source module imports it). No ADR: ADR-005's decision already lists QA among the package's
   contents; the CLAUDE.md Layout paragraph gains the module name.
2. `cta.mansueto` imports `qa_rows` and `QA_COLUMNS` from `cta.qa` and keeps both names; its importers are not
   edited. `cta.archive.QA_COLUMNS` is the same object. `scripts/route_run_level.py` imports `stage_totals`
   from `cta.qa` and keeps the name.
3. `cta.archive._record_qa` calls `cta.qa.qa_rows` first and then deletes and inserts, `seq` being the row's
   position. One error path differs from today, where rows are replaced and then the check raises: a failed
   check now raises before the `DELETE`, so `archive_qa` keeps what it held. The message still names the
   stage and the day.
4. Run the whole suite. `git diff tests/` shows the new file only: no existing assertion is edited (Rule 7).
   Then the local-day comparison of the second playbook pattern, if an archive day is cached.

## Thresholds and exclusions

None. No constant moves or changes.

## Fixtures

| Fixture | Built from (public file) | Cut | Rows / bytes | Builder |
|---|---|---|---|---|
| `tests/fixtures/mansueto_2026-07-27_route3.parquet` | existing | | | |
| `tests/fixtures/getpatterns/getpatterns_18414.json`, `getpatterns_18415.json` | existing | | | |

## Acceptance tests

All in `tests/test_qa.py`; offline. No test hard-codes a QA count from a fixture: those live in the `/qa` baseline (`specs/qa-skill.md`).

- [ ] `test_qa_rows_known_case`: hand-built. `qa_rows("s", 10, 7, {"a": 2, "b": 1, "c": 0})` returns two rows (`a` 2, `b` 1) with `rows_in` 10 and `rows_out` 7; `qa_rows("s", 5, 5, {})` returns one row with `reason` None and `count` 0; `qa_rows("s", 10, 7, {"a": 2})` raises `AssertionError`.
- [ ] `test_stage_totals_known_case`: hand-built. Two calls of stage `s` for one pid, years 2025 (10 → 7 with `a` 2, `b` 1) and 2026 (5 → 5 with no reason), `by=["pid"]`, `call_keys=["pid", "year"]`: one row with `rows_in` 15, `rows_out` 12, `a` 2, `b` 1. A table whose counts do not sum raises `AssertionError`.
- [ ] `test_old_names_are_the_shared_helper`: `cta.mansueto.qa_rows is cta.qa.qa_rows`; `cta.mansueto.QA_COLUMNS`, `cta.archive.QA_COLUMNS` and `cta.qa.QA_COLUMNS` are one object; `scripts.route_run_level.stage_totals is cta.qa.stage_totals`.
- [ ] `test_qa_imports_nothing_from_cta`: parsing `cta/qa.py` with `ast` finds no import of `cta` or a `cta.` module and no relative import (`from . import ...`).
- [ ] `test_record_qa_failed_check_leaves_table_untouched`: on `cta.archive.open_archive_db()` in memory, record stage `stage_x` for `2026-10-29` as 10 → 7 with `{"a": 3}`; a second call with `{"a": 2}` raises `AssertionError` whose message contains `stage_x` and `2026-10-29`, and `cta.archive.qa(con, "2026-10-29")` still returns the first row.
- [ ] `test_stage_totals_on_route3_fixture` (the QA-table case): on `tests/fixtures/mansueto_2026-07-27_route3.parquet`, `run_level_from_mansueto_with_qa(["18414", "18415"], ...)` summed with `stage_totals(qa, ["pid"], ["pid"])` has one row per (pid, stage) for both pids and the four stages of `cta.mansueto.STAGES`; on every row the reason columns sum to `rows_in − rows_out`; and per pid, `rows_out` at `order` equals that pid's row count in the view. Identities only, so no threshold change edits it.

## Out of scope

- Changing any threshold, reason name, stage name or QA number. If a number moves, the refactor is wrong.
- Re-pointing the importers of `cta.mansueto.qa_rows` to `cta.qa`, or removing the aliases: a follow-up TODO item.
- Editing the notebook's `stage_table`, or any notebook.
- Replacing the DuckDB `archive_qa` table with in-memory QA, or changing what `cta.archive.qa` returns.
- Fixture cases, the baseline, `scripts/qa.py` and the skill: `specs/qa-skill.md`.

## Open questions

Both resolved by the owner on 2026-11-16.

1. **A failed additivity check in `_record_qa` leaves `archive_qa` untouched instead of replaced
   (Method 3).** **Accepted.** It never fires on a committed fixture, so Rule 7 holds; keeping the old order
   would keep the check duplicated.
2. **Aliases or re-pointed importers?** **Aliases in this spec; the importers are re-pointed to `cta.qa` and
   the aliases removed in a follow-up** (TODO.md Foundation, "Re-point the importers of the QA helper").
