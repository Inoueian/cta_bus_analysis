# Spec: <short title>

Status: draft | ready | in progress | done
Owner: <you>  ·  Date: YYYY-MM-DD  ·  TODO item: <link or quote>

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

Numbered steps. Name every threshold and its evidence. Reference prior art
(e.g. scorecard.sql step numbers) rather than re-deriving.

## Thresholds and exclusions

| Name | Value | Evidence | Sensitivity if changed |
|---|---|---|---|

## Acceptance tests

Concrete, runnable. Each becomes a pytest.

- [ ] On fixture X, output has N rows and columns [...].
- [ ] QA table reports reasons [...] and they sum to rows_in − rows_out.
- [ ] Known case: trip T crosses stop S at HH:MM:SS ± 10 s.

## Out of scope

Bullets. What an implementer must not do, even if it seems helpful.

## Open questions

Things the owner must answer before status becomes `ready`.
