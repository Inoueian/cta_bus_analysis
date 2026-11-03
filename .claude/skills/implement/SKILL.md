---
name: implement
description: Implement a spec from specs/ that is marked ready. Use when the user says "implement specs/<name>.md", "build this spec", or "do the archive adapter spec". Writes acceptance tests first, then code under cta/ (or the legacy location CLAUDE.md names), runs pytest, emits the QA table, and updates TODO.md. Refuses specs not marked ready.
---

# /implement — build from a ready spec

Argument: a path under `specs/`.

## Gate

1. Read `CLAUDE.md` and the spec. If the spec's status is not `ready`, stop and say so; offer `/spec` to review it. Do not implement a draft because it looks fine.
2. If the spec contradicts itself or an Accepted ADR, stop and ask. Otherwise do not ask; write assumptions down and continue.
3. Confirm every fixture the acceptance tests name exists under `tests/fixtures/`. If one is missing and the spec says how to build it, build it first, from the public file it names, and verify the stated SHA-256 or row count. Never download more than one archive day.

## Order of work

1. **Tests first.** One pytest per acceptance item, named after it, in `tests/test_<module>.py`. Run them; they must fail for the right reason (missing function, not import error).
2. **Code.** In `cta/` if it exists, otherwise where CLAUDE.md's layout note says. Thresholds are named module constants with an evidence comment. Identifiers are strings; timestamps tz-aware UTC. DuckDB for anything over ~1M rows; return pandas at function boundaries.
3. **QA table.** Every stage emits rows in, rows out and reason counts. A test asserts the reasons sum to the difference.
4. **Run `pytest`** for the whole suite, not just the new file. Fix what you broke.
5. **Script entry point** if the spec names one: thin argparse in `scripts/`, documents itself with `-h`.

## Do not

- Change a threshold or exclusion the spec states. If the data says it is wrong, keep the spec's value, make the test pass or mark it xfail with the reason, and report it.
- Touch notebooks except to update an import path.
- Write to `data/` from tests, commit anything under `data/`, print `CTA_API_KEY`, or add network calls to tests.
- Add rider-facing prose (ADR-002).
- Widen scope into the spec's Out of scope list, even when it is one line away.

## Finish

1. TODO.md: move the item to Done with today's date and the spec path. Flip the spec's status to `done` and add the commit or PR reference.
2. If an implementation choice is one future work must respect, record it with `/adr`.
3. If a durable data finding came up, add it to `docs/` as a dated note.
4. Commit on the working branch with a message that names the spec. Do not open a PR unless asked.

## Report

In this order, briefly: assumptions made; files changed; the QA table; test results (counts, any xfail and why); anything the spec got wrong or left open. Lead with failures if there are any.
