---
name: finding
description: Record durable knowledge where agents will find it. Use when a session measured something about the data, hit a gotcha worth not rediscovering, found a pattern worth copying, or is migrating a knowledge-vault note. Routes the entry to a dated docs/ note, to docs/playbook.md (gotchas, patterns), or hands off to /adr; tags it from the closed vocabulary; keeps the note index current.
---

# /finding — capture durable knowledge in the right place

Arguments: what was learned, in a sentence or a pasted table, or a vault note to migrate. With no
argument, ask the one question in Route.

## Route

Decide the destination first. One entry, one destination; say which in the report.

| What was learned | Destination | Shape |
|---|---|---|
| A measurement: a number, a date, a schema fact, with a method and a re-check | New dated note `docs/YYYY-MM-DD-<slug>.md` | Dated note (below) |
| A gotcha: a symptom an agent would hit again, with cause and fix | Append under `## Gotchas` in `docs/playbook.md` | Symptom, cause, fix, where |
| A pattern: to do X, copy Y | Append under `## Patterns` in `docs/playbook.md` | To do X, copy Y, by file and function |
| A choice future work must respect (source, schema, threshold policy, stack) | `/adr`; do not write it here | ADR |
| A step every task of one kind must follow | The skill file for that task (`/spec`, `/implement`, …) | Skill text |
| A rule every agent acts on, every time | CLAUDE.md, one line, and only if nothing above fits | Rule |

If the input is both (a measurement that revealed a gotcha), write the dated note and add a two-line
gotcha that points at it. Never put a gotcha only in a dated note: dated notes are history, the
playbook is what gets read.

## Tags

Every entry carries one `Tags:` line, built only from the vocabulary table in `docs/playbook.md`:
two to five tags, exactly one `kind:`, the rest `source:`, `stage:`, `topic:`. Before writing:

```
grep -n 'Tags:' docs/*.md specs/*.md | grep -o '[a-z-]*:[a-z-]*' | sort | uniq -c | sort -rn
```

- A tag not in the vocabulary is not used. Either pick the nearest listed tag, or add the new one to
  the vocabulary table first with a meaning, and say in the report that the vocabulary grew.
- Proper nouns (modules, functions, PIDs, columns, ADR numbers) are never tags; write them in the text
  where grep finds them.
- Pruning: if the count above shows a `topic:` used once and older than a year, fold it into its
  neighbour, update the entries, and report it.

## Dated note

Copy the shape of `docs/2026-11-04-mansueto-data-edge.md`:

```
# <What was measured>: <the headline number or fact> (measured YYYY-MM-DD)

Tags: `kind:measurement source:<x> …`

One paragraph: why it was measured, what it corrects or confirms, which spec, ADR or TODO item it serves.

## Measurement
How, exactly (command, script, range request, fixture). A table of the numbers. Nothing downloaded in
full that did not need to be; no more than one archive day.

## <Facts confirmed>
Bullets, each a durable statement with its evidence.

## Corrections to earlier notes
Which notes, ADRs or specs said otherwise, and the corrected value. Omit the section if none.

## How to re-check
The command or function that reproduces the headline number, and what to do if it moved.
```

Then add one row at the top of `## Index of dated notes` in `docs/playbook.md` (file, tags, one line).

A note that is for the owner rather than an agent (prices, model choice) is `kind:owner-note` and says so
in its first paragraph, as `docs/2026-11-05-model-routing.md` does.

## Playbook entry

Gotcha:

```
### <Symptom in one line>
Tags: `kind:gotcha source:<x> stage:<y> topic:<z>`
- Symptom: what the agent sees.
- Cause: why, with the evidence (a note, a probe, a line of code).
- Fix: what to do, and the function or constant that already does it. If nothing does, say so and
  name the TODO item that will.
```

Pattern:

```
### <To do X>
Tags: `kind:pattern stage:<y> topic:<z>`
- Copy `<file>` `<function or section>`: the two or three things that make it the right shape.
```

Before appending, grep the playbook for the symptom's nouns; if an entry exists, sharpen it rather
than adding a second. When a gotcha becomes a code guarantee, keep the entry and point at the guard.

## Migrating a vault note

Paste the note. Split it: each measurement becomes a dated note with the vault note's original date in
the file name and "migrated YYYY-MM-DD from vault `<name>`" in its first paragraph; each quirk or
limit becomes a gotcha; each procedure becomes a pattern. Then replace every reference to the vault
note (README.md, TODO.md, module docstrings, DECISIONS.md context) with the new path or heading; TODO.md
edits follow `/todo`.

## After

- If the finding changes a published threshold or exclusion, stop: that is Rule 2 and needs the spec,
  the QA table and possibly `/adr`, not a note.
- If a TODO.md item rests on the finding, reword it with `/todo`, citing the new note or heading.
- If a module constant's evidence comment cites a number the note corrected, update the comment.
- Nothing here runs code or touches `data/`; a note may quote a script but the script is run elsewhere.

## Report

The destination and path or heading; the `Tags:` line; the index row added; vocabulary changes and
prunes; every other file touched (TODO.md, README, docstrings) and why; and what the note corrects.
