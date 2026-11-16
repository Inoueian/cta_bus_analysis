---
name: qa
description: Run every adapter on its committed fixture, print the per-stage QA table (rows in, rows out, reason counts) and diff it against the committed baseline tests/fixtures/qa_baseline.csv. Use when the user says "run /qa", "did the QA table move", "check the QA baseline", "record the baseline", after /implement's pytest run, after /fixture rebuilds a fixture, or when tests/test_qa_baseline.py fails. Records a new baseline only for a spec'd threshold or exclusion change, a rebuilt fixture, or a new case; never for a refactor.
---

# /qa — fixture QA tables against the committed baseline

Arguments: case names from `cta.qa_baseline.FIXTURE_CASES` (`archive`, `mansueto_route3`,
`mansueto_6410`, `mansueto_raw`), or nothing for every case.

The baseline is what makes CLAUDE.md Rule 2 a command: each adapter's QA table on its committed fixture
is pinned in `tests/fixtures/qa_baseline.csv`, and `tests/test_qa_baseline.py`
`test_baseline_matches_fixtures` fails on any difference. The baseline is a fixture, not a test
assertion; the `docs/*-qa.md` notes stay the human record with the reasoning (`specs/qa-skill.md`).

## Run

```
python scripts/qa.py            # every case; exit status 1 on any difference
python scripts/qa.py archive    # one case, against that case's baseline rows only
```

Offline: it reads `tests/fixtures/` and `notebooks/michigan_ave_kept_pids.json`, never the network or
`data/` (Rules 3, 4).

## Read the result

1. "no difference": say so, with the case names, and stop.
2. A diff: name each case, key, stage and reason that moved, with the baseline and observed numbers
   (`field` is `rows_in`, `rows_out`, `count`, `missing_row` for a row only in the baseline, `new_row`
   for a row only observed). Then decide which of these it is. If it is none of them, stop and report;
   do not record.

   | Why the table moved | What to do |
   |---|---|
   | (a) A spec whose Thresholds table names a threshold or exclusion change (Rule 2) | Record the cases the spec names; the diff must be what the spec predicts |
   | (b) `/fixture` rebuilt a fixture a case reads | Record that case; the rows of every other case must not move |
   | (c) A case was added to `FIXTURE_CASES` | Record that case; the rows of every other case must not move |
   | A refactor (Rule 7), or anything unexplained | Never record. The code change is wrong, or it is a behaviour change that needs a spec |

## Record

```
python scripts/qa.py <case> --record    # replaces only that case's rows; prints the diff it accepts
```

- `scripts/qa.py --record` is the only writer of `tests/fixtures/qa_baseline.csv`; never edit it by hand.
- Name the cases. With no case it rewrites the whole file, which also drops rows of a case no longer in
  `FIXTURE_CASES`; do that only when a case was removed on purpose.
- Then run `python scripts/qa.py` (no difference) and `python -m pytest -q`.
- Add the new table to a dated `docs/*-qa.md` note with `/finding` (`kind:qa`): the diff accepted, the
  spec or fixture rebuild that explains it, and the table after. The note is the human record.

## Do not

- Record to make `test_baseline_matches_fixtures` pass without one of (a) to (c).
- Hard-code the baseline's counts in a test, or edit the counts existing tests assert.
- Add a network call or a `data/` read to a case; patterns come from `tests/fixtures/getpatterns/` by
  explicit directory.

## Report

The cases run; "no difference", or the diff quoted; which of (a) to (c) applied and its spec or fixture;
the cases recorded and the `docs/` note; pytest's summary line.
