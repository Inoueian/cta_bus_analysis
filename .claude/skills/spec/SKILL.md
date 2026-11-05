---
name: spec
description: Write or review a spec in specs/ from a TODO item or a one-line ask. Use when the user says "spec this", "write a spec for", "review the spec", or names a TODO item that has no spec yet. Produces specs/<slug>.md from specs/TEMPLATE.md with status draft; a review returns a checklist of gaps.
---

# /spec — write or review a spec

Arguments: a TODO.md line, a sentence, or a path to an existing `specs/*.md` to review.

## Before writing

1. Read `CLAUDE.md`, `specs/TEMPLATE.md`, the TODO.md item this spec serves, and the most recent `done`
   spec of the same kind (an adapter spec for an adapter, a view spec for a view). Quote the item verbatim in the header.
   Find the spec of the same kind by tag, not by guessing: `grep -ln 'Tags:.*stage:view' specs/*.md`
   (vocabulary in `docs/playbook.md`).
2. Read the ADRs the item touches (DECISIONS.md). A spec never contradicts an Accepted ADR; if it must, it says so under Open questions and proposes a new ADR.
3. Look for prior art before inventing. Run these and read what they find, rather than designing from memory:

   ```
   grep -n '^def \|^class ' cta/*.py          # every helper that exists today
   grep -rn '<keyword>' cta/ docs/ specs/     # one grep per noun in the TODO item
   grep -n 'Tags:.*source:<x>' docs/playbook.md docs/*.md specs/*.md   # one grep per source and stage the item touches
   ```

   Read every playbook gotcha and pattern the tag grep returns before writing Method; a `kind:pattern`
   entry is usually the "Prior art to copy" line. A gotcha the spec must handle goes in Method or
   Thresholds with the playbook heading cited.

   Reference by file and function rather than re-deriving. The scorecard pipeline cited in ADR-004 and the
   helpers in `notebooks/*.py` count as prior art.
4. If a fixture is needed and none exists under `tests/fixtures/`, the spec must say how to build it, from what public file, and its expected SHA-256 or row count.

## Writing

Fill every section of the template, including the `Tags:` line (one `kind:spec`, then the `source:`,
`stage:` and `topic:` tags from `docs/playbook.md`; no new tags from a spec). The parts people skip are
the ones that matter:

- **Method** opens with `Prior art to copy: cta/<module>.py <function or stage>; tests/test_<module>.py <test>`
  so the implementer mirrors a shape instead of designing one. If nothing fits, write "none" and say why.
- **Outputs** need a schema (column names and types) and a grain (one row per what). "A DataFrame" is not a schema.
- **Thresholds** need a value and evidence, or the word "unknown" and a plan to measure it. Name each as a module constant.
- **Acceptance tests** must be runnable offline against a committed fixture, and each must become one pytest.
  Start each item with its test function name (`test_...`) and name its fixture path. Include at least one
  analytic case (a hand-built input with a known answer) and one QA-table case (reason counts sum to rows_in − rows_out).
- **Numbers in acceptance tests are requirements unless marked.** Mark a number you have not measured on the
  committed fixture as `~N` or "(estimate; measure, then pin)". `/implement` may correct only marked numbers;
  an unmarked number it cannot meet becomes an xfail and a report line, so mark every count, size and ratio
  you are guessing.
- **Out of scope** lists the helpful things an implementer must not do.
- Status is `draft` when written by an agent. Only the owner flips it to `ready`.

Keep it under about 120 lines and eight acceptance items. A spec that needs more is two specs, split by
module (one adapter, one view, one script), not by feature.

## Reviewing

Return a checklist, each line pass or gap with the fix:

- [ ] Question states a rider- or analysis-facing outcome, not a mechanism.
- [ ] Method names prior art to copy, by file and function, or says why none fits.
- [ ] Every output has schema and grain; identifiers are strings; timestamps tz-aware UTC.
- [ ] Every threshold has evidence or is marked unknown.
- [ ] Every acceptance item starts with its test function name, names its fixture, and is offline.
- [ ] Every number in an acceptance test is measured on the fixture or marked as an estimate.
- [ ] A QA-table test exists.
- [ ] Out of scope is non-empty.
- [ ] No conflict with Accepted ADRs; CLAUDE.md rules 1–6 respected.
- [ ] Under about 120 lines and eight acceptance items, or split.
- [ ] TODO.md item exists and will link to this spec.
- [ ] `Tags:` line present, every tag in the `docs/playbook.md` vocabulary, exactly one `kind:`.
- [ ] Every playbook gotcha matching the spec's `source:` and `stage:` tags is handled or cited.

## After

- Add the spec path to the TODO.md item as `/todo` describes (`Spec: specs/<slug>.md (draft)`).
- Do not implement. That is `/implement`, and only from a `ready` spec.
- Report: the path, the open questions the owner must answer, every number marked as an estimate, and any TODO or ADR edits made.
