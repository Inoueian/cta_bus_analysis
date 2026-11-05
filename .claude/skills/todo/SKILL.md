---
name: todo
description: Update TODO.md (add, reword, move or close an item) keeping the file's shape and the spec marker on every active item. Use when the user says "add a TODO", "close this item", "update the backlog", "mark done", or when another skill (/spec, /implement, /adr) needs a TODO.md edit. Owns the Done entry format and the Spec / No spec vocabulary.
---

# /todo — keep TODO.md truthful

Arguments: what changed, in a sentence, or nothing (then ask which item and what happened to it).

## Shape of the file

- Sections are fixed: Foundation, the phases, the side quests, Done. Items under a `### Now` or `### Next`
  heading, or directly under Foundation / Phase 2 / Phase 3, are active. Done is history: newest first,
  one line per finished item ending with `(YYYY-MM-DD)`.
- `Last updated:` at the top is today's date whenever the file changes.
- An active item says what the deliverable is (file, function, script, notebook, docs note) and cites
  the ADR, spec or docs note it rests on. Evidence goes in the item (counts, dates, pids), not adjectives.

## The spec marker

Every active item ends with exactly one of:

- `Spec: specs/<slug>.md (draft|ready|done)` — the spec exists; the status in parentheses mirrors the
  spec's own `Status:` line. On every edit of TODO.md, re-read each referenced spec's `Status:` and
  correct the marker, whichever item you were asked to touch; report any marker you corrected.
- `Spec: to write` — non-trivial work with no spec yet. `/implement` cannot start it; `/spec` can.
- `No spec: <reason>` — the reason is one of `exploratory` (a notebook with a Findings cell, durable results
  to `docs/`), `applies existing code` (a thin script plus a `docs/` QA note, no new thresholds), `documentation`,
  or `ADR` (the deliverable is a DECISIONS.md entry). Anything else is `Spec: to write`.

A marker is a promise about process, not a size estimate: an item that adds or changes a threshold,
schema, exclusion or data source is never `No spec`.

## Operations

- **Add**: one line in the right section, with the marker. Place it where its dependencies put it: a
  section whose intro claims an order (Foundation: "dependency order") must stay true after the edit, and
  the report says where the line went and why. If it blocks other items, say which.
- **Reword after a finding**: keep the item's identity, replace the stale clause, cite the docs note or
  commit that made it stale. Do not append a diary; the Done section and `docs/` hold the history.
- **Partially done**: split. Close the finished part as its own Done line with the date, and reword the
  remaining item to only what is left (its marker may change). No strikethrough inside active items.
- **Close**: move the line to the top of Done with the date, the spec path and the files or numbers that
  prove it (test counts, fixture names, measured ratios). Remove any pointer line left behind ("moved to…").
- **Never** delete or edit a Done entry; correct it with a new line that says what was wrong.
- **Reorder** only when an add or reword makes a claimed order false, or when asked; say what moved.

## Hand-offs

- `/spec` calls this with `Spec: specs/<slug>.md (draft)` when it writes a spec; the owner flips `ready`.
- `/implement` calls this to close the item, with the spec path and the QA numbers from its report.
- `/adr` calls this to add `ADR-NNN` to every item the decision touches.

## Report

The lines added, moved or changed, quoted; markers corrected to match a spec's `Status:`; and any item
whose marker or position you could not decide (say why).
