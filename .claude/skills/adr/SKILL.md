---
name: adr
description: Record an architecture decision in DECISIONS.md. Use when the user says "log an ADR", "record this decision", "add a decision", or when an implementation makes a choice that future work must respect (a data source, a schema, a threshold policy, a stack). Inserts a numbered entry at the top with today's date and handles supersession.
---

# /adr — record a decision

Arguments: the decision in a sentence, or nothing (then ask the three questions below).

## Rules of the file

- Newest at the top, directly under the `---` that follows the status legend.
- Past entries are historical record: never edit their text. To reverse one, add a new ADR and change the old one's status line only, to `Superseded by ADR-NNN`.
- Numbering is sequential; read the current highest number from the file, do not guess.
- Date is today's date in ISO form. Status is `Proposed` unless the user says it is accepted.

## Gather

Ask only for what the user has not already said:

1. **Context.** What forces the decision now? Cite evidence: a measurement, a profiling result, a prototype, a constraint. One paragraph.
2. **Decision.** The choice, stated so an implementer can act on it without reading the context. Name files, sources, schemas or thresholds concretely.
3. **Consequences.** What becomes easier, what becomes harder, what risk is accepted, what must now be maintained. Include the fallback if the decision fails.

## Write

Use exactly this shape, matching the existing entries:

```
## ADR-NNN: <title>
Date: YYYY-MM-DD
Status: Proposed | Accepted

### Context
...

### Decision
...

### Consequences
...

---
```

If the decision amends an earlier ADR without reversing it, say `Status: Accepted (amends ADR-NNN; does not supersede it)` and leave the older entry alone. If it reverses one, update the older status line and say which ADR replaces it.

## After

- If CLAUDE.md states the old behaviour (layout, sources, conventions), update that line too; CLAUDE.md must never disagree with an Accepted ADR.
- If a TODO.md item or a spec depends on the decision, add the ADR reference there (TODO.md edits follow `/todo`).
- Report: the ADR number, its status, and every other file touched.
