---
name: spec
description: Write or review a spec in specs/ from a TODO item or a one-line ask. Use when the user says "spec this", "write a spec for", "review the spec", or names a TODO item that has no spec yet. Produces specs/<slug>.md from specs/TEMPLATE.md with status draft; a review returns a checklist of gaps.
---

# /spec — write or review a spec

Arguments: a TODO.md line, a sentence, or a path to an existing `specs/*.md` to review.

## Before writing

1. Read `CLAUDE.md`, `specs/TEMPLATE.md`, and the TODO.md item this spec serves. Quote the item verbatim in the header.
2. Read the ADRs the item touches (DECISIONS.md). A spec never contradicts an Accepted ADR; if it must, it says so under Open questions and proposes a new ADR.
3. Look for prior art before inventing: existing helpers in `notebooks/*.py` or `cta/`, `docs/`, and the scorecard pipeline cited in ADR-004. Reference by file and step rather than re-deriving.
4. If a fixture is needed and none exists under `tests/fixtures/`, the spec must say how to build it, from what public file, and its expected SHA-256 or row count.

## Writing

Fill every section of the template. The parts people skip are the ones that matter:

- **Outputs** need a schema (column names and types) and a grain (one row per what). "A DataFrame" is not a schema.
- **Thresholds** need a value and evidence, or the word "unknown" and a plan to measure it. Name each as a module constant.
- **Acceptance tests** must be runnable offline against a committed fixture, and each must become one pytest. Include at least one analytic case (a hand-built input with a known answer) and one QA-table case (reason counts sum to rows_in − rows_out).
- **Out of scope** lists the helpful things an implementer must not do.
- Status is `draft` when written by an agent. Only the owner flips it to `ready`.

Keep it under about 150 lines. A spec that needs more is two specs.

## Reviewing

Return a checklist, each line pass or gap with the fix:

- [ ] Question states a rider- or analysis-facing outcome, not a mechanism.
- [ ] Every output has schema and grain; identifiers are strings; timestamps tz-aware UTC.
- [ ] Every threshold has evidence or is marked unknown.
- [ ] Every acceptance test names its fixture and is offline.
- [ ] A QA-table test exists.
- [ ] Out of scope is non-empty.
- [ ] No conflict with Accepted ADRs; CLAUDE.md rules 1–6 respected.
- [ ] TODO.md item exists and will link to this spec.

## After

- Add the spec path to the TODO.md item as `/todo` describes (`Spec: specs/<slug>.md (draft)`).
- Do not implement. That is `/implement`, and only from a `ready` spec.
- Report: the path, the open questions the owner must answer, and any TODO or ADR edits made.
