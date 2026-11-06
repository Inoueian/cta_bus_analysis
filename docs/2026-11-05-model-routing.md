# Model routing for spec-driven work (decided 2026-11-05)

Tags: `kind:owner-note topic:process`

A note for the owner, not the agent: CLAUDE.md holds only rules an agent acts on, and an agent cannot
choose its own model or effort. This records which model runs which step once Fable-class credits run
out, and where that choice is enforced.

## Prices (Anthropic API list, 2026-11; Claude Code credit ratios track them)

| Model | Input $/M | Output $/M | Relative to Fable 5.1 |
|---|---|---|---|
| Fable 5.1 | 10 | 50 | 1x |
| Opus 5.5 | 4 | 20 | 0.4x |
| Sonnet 5.5 | 2 | 10 | 0.2x |
| Haiku 5.5 | 0.10 | 0.50 | 0.01x |

## Routing

Cost is dominated by long agentic sessions, not clerical edits. Judge cost per completed task: a failed
cheap run plus a rerun costs more than one run on the stronger model.

| Step | Model | Effort | Why |
|---|---|---|---|
| `/spec`, review of a spec that adds a data source, exploratory notebooks, findings | Opus | high | The judgment step: prior art, ADR consistency, data quirks. Cheap by volume. Opus defaults to medium effort, so set high explicitly. |
| `/implement` from a `ready` spec | Sonnet | medium | The spec and acceptance tests constrain the work; pytest is the oracle. One fresh session per spec: cost scales with context resent per turn. Start at medium and raise only if quality drops. |
| `/todo`, `/adr`, spec checklist review | whatever the session has | | Small files, small cost either way. |

Escalate an implementation to Opus when the spec introduces a new module shape or data source, or when
a Sonnet run reports more than two "spec got wrong" items or cannot get green. The implement skill
stops and says so at that point rather than iterating.

## Where it is enforced

- **Skill frontmatter** is the mechanical lever. A `SKILL.md` may carry `model:` and `effort:`; without
  `context: fork` the override applies to the main conversation for the rest of that turn, then the
  session model resumes on the next prompt. When ready to switch, add `model: sonnet` and
  `effort: medium` to `.claude/skills/implement/SKILL.md`, and `model: opus` and `effort: high` to
  `.claude/skills/spec/SKILL.md`. Until then the fields are left out so the session model applies.
- **The commit hook** (`.claude/hooks/precommit.sh`) enforces the pytest gate and CLAUDE.md rules 4 and 5
  regardless of model.
- **The skill files** are written for the weaker model: labels (estimate vs requirement), checklists,
  commands, a plan table before code, a reading cap, and a stop condition.
- Cloud sessions read the committed `.claude/settings.json` and skill files but not user or local
  settings, so a per-model effort default in `~/.claude/settings.json` affects local runs only.

## How to re-check

Prices: the Claude API pricing page. Frontmatter fields: the Claude Code skills reference
(`model`, `effort`). Re-measure the routing by comparing, per spec, the number of "spec got wrong"
report lines and reruns on Sonnet against Opus.
