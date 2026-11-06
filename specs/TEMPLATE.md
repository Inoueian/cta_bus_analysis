# Spec: <short title>

Status: draft | ready | in progress | done
Owner: <you>  ·  Date: YYYY-MM-DD  ·  TODO item: <link or quote>
Tags: `kind:spec source:<archive|mansueto|bustracker|gtfs> stage:<…> topic:<…>   (vocabulary: docs/playbook.md)`

## Question

One paragraph. What rider- or analysis-facing question does this answer? Why now?

## Inputs

| Input | Where | Schema / keys | Notes |
|---|---|---|---|
| e.g. archive day file | `data/archive/bus-YYYY-MM-DD.ndjson.gz` | fields per `index.json` | SHA-256 verified |

## Outputs

| Output | Path / function | Schema | Grain |
|---|---|---|---|
| e.g. run-level view | `cta.views.run_level(...)` → DataFrame | ADR-003 columns | one row per (run, stop) |

## Method

Prior art to copy: `cta/<module>.py` `<function or stage>`; `tests/test_<module>.py` `<test>`
(or "none" and why).

Numbered steps. Name every threshold and its evidence. Reference prior art
(e.g. scorecard.sql step numbers) rather than re-deriving.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|

## Acceptance tests

Concrete, runnable. Each becomes one pytest; start each item with its test function name and
fixture. Every number is a requirement unless marked `~N` or "(estimate; measure, then pin)";
`/implement` may correct only marked numbers. At most about eight items; split the spec otherwise.

- [ ] `test_<name>_rows`: on `tests/fixtures/<x>`, output has N rows and columns [...].
- [ ] `test_<name>_qa`: QA table reports reasons [...] and they sum to rows_in − rows_out.
- [ ] `test_<name>_known_case`: trip T crosses stop S at HH:MM:SS ± 10 s (hand-built input).
- [ ] `test_<name>_fixture_size`: fixture holds ~N rows (estimate; measure, then pin).

## Out of scope

Bullets. What an implementer must not do, even if it seems helpful.

## Open questions

Things the owner must answer before status becomes `ready`.
