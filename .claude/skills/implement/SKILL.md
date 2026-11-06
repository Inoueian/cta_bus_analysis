---
name: implement
description: Implement a spec from specs/ that is marked ready. Use when the user says "implement specs/<name>.md", "build this spec", or "do the archive adapter spec". Writes a plan, then acceptance tests, then code under cta/ (or the legacy location CLAUDE.md names), runs pytest, emits the QA table, and updates TODO.md. Refuses specs not marked ready.
---

# /implement — build from a ready spec

Argument: a path under `specs/`.

## Gate

1. Read, in this order and nothing else yet: `CLAUDE.md`, the spec, the ADRs the spec cites in
   DECISIONS.md, the prior-art module the spec's Method names and that module's test file, and the
   playbook entries for the spec's tags:

   ```
   grep -n 'Tags:.*kind:gotcha.*source:<x>' docs/playbook.md   # one per source: and stage: tag on the spec
   ```

   Read each matching gotcha (heading to the next `###`). Do not open notebooks unless the spec points at
   one. Do not read other modules until a test fails for want of one.
2. If the spec's status is not `ready`, stop and say so; offer `/spec` to review it. Do not implement a draft because it looks fine.
3. If the spec contradicts itself or an Accepted ADR, stop and ask. Otherwise do not ask; write assumptions down and continue.
4. Confirm every fixture the acceptance tests name exists under `tests/fixtures/`. If one is missing and the spec says how to build it, build it first, from the public file it names, and verify the stated SHA-256 or row count. Never download more than one archive day.

## Plan before code

Write the plan into the conversation before creating or editing any file:

| Acceptance item | Test function | Fixture | Needs (function or module) |
|---|---|---|---|

Use the spec's test names; if an item has none, `test_<item>`. Below the table, list the files you expect to
create or change: everything the spec's Outputs table names, and nothing else. Keep the table; the report
ends with it, each row marked done, xfail or open.

## Order of work

1. **Tests first.** One pytest per acceptance item, named as in the plan, in `tests/test_<module>.py`. Run them; they must fail for the right reason (missing function, not import error).
2. **Code.** In `cta/` if it exists, otherwise where CLAUDE.md's layout note says. Copy the shape of the prior-art module the spec names before designing a new one. Thresholds are named module constants with an evidence comment. Identifiers are strings; timestamps tz-aware UTC. DuckDB for anything over ~1M rows; return pandas at function boundaries.
3. **QA table.** Every stage emits rows in, rows out and reason counts. A test asserts the reasons sum to the difference.
4. **Run `python -m pytest -q`** for the whole suite, not just the new file. Fix what you broke.
5. **Script entry point** if the spec names one: thin argparse in `scripts/`, documents itself with `-h`.

## When a test disagrees with the data

- A number the spec marks as an estimate (`~N`, "estimate", "unknown; measure, then pin") may be corrected:
  measure it on the fixture, pin it, and record old value, new value and evidence in the report.
- Every other assertion is a requirement. Never edit it to make a test pass. Keep the spec's value, mark the
  test `xfail` with the reason, and report it under "spec got wrong".
- Three failed fixes on the same assertion means stop: leave it failing or xfail, and report. Do not try a fourth.
- Before finishing, run `git diff --stat tests/` and name in the report every assertion changed after it was
  first written, with why.

## Do not

- Change a threshold or exclusion the spec states. If the data says it is wrong, keep the spec's value, make the test pass or mark it xfail with the reason, and report it.
- Touch notebooks except to update an import path.
- Write to `data/` from tests, commit anything under `data/`, print `CTA_API_KEY`, or add network calls to tests.
- Add rider-facing prose (ADR-002).
- Widen scope into the spec's Out of scope list, even when it is one line away.
- Edit a file the spec's Outputs table does not name without listing it in the report with the reason.

## Finish

Run these; paste the first line of pytest's summary into the report:

```
python -m pytest -q
git status --porcelain | grep -E '^.. (data/|\.env)'   # must print nothing
git diff --stat                                        # only the plan's files plus tests/, docs/, TODO.md and the spec
grep -n '^Status:' specs/<slug>.md                     # must read done after step 1 below
```

Then:

1. TODO.md: close the item as `/todo` describes (Done, today's date, spec path, QA numbers). Flip the spec's status to `done` and add the commit or PR reference.
2. If an implementation choice is one future work must respect, record it with `/adr`.
3. If a durable data finding came up, record it with `/finding` (a dated `docs/` note for a measurement,
   a `docs/playbook.md` entry for a gotcha or pattern).
4. Commit on the working branch with a message that names the spec. Do not open a PR unless asked. The
   commit hook in `.claude/settings.json` re-runs pytest and refuses staged `data/` or `.env` paths; a
   blocked commit is a failed check to fix, not something to work around.

## Report

If the report would list more than two "spec got wrong" items, or the suite cannot get green after
every plan row was attempted, stop there: say the spec needs an owner pass or a stronger model before
more work, and do not keep iterating.

In this order, briefly: assumptions made; files changed, naming any file outside the spec's Outputs table and why; the plan table with each row's state; the QA table; test results (counts, any xfail and why, any assertion changed after it was first written); anything the spec got wrong or left open. Lead with failures if there are any.
