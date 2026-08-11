# Decisions

Architecture Decision Records (ADRs) for this project. **Newest at the top.** Past entries are historical record — never edit them. To reverse a decision, add a new ADR and mark the older one `Superseded by ADR-NNN`.

Statuses:
- **Proposed** — under discussion, not yet in effect
- **Accepted** — in effect
- **Superseded by ADR-NNN** — replaced by a later decision
- **Deprecated** — no longer in effect, not replaced

---

## ADR-003: Two canonical data views — run-level and stop-level
Date: 2026-08-10
Status: Accepted

### Context

The app answers two structurally different distributional questions. Wait time asks "at this stop, how long between buses on this route in this direction?" — a computation over the arrival-time sequence at a single stop, ignoring runs. Travel time asks "given a bus arrived at stop A, how long until the same bus reached stop B?" — a computation within a single run, joining two of its stop visits. A view that indexes cleanly for one is inefficient for the other, so serving both queries off a single derived table means every request pays a large scan or join cost.

The Mansueto per-Pattern parquet naturally represents the run-level shape: each row is one (trip, stop, arrival_time) tuple. But it is partitioned by Pattern ID, and a rider does not think in patterns — they think in "the 6 Northbound." So a query about the 6 Northbound at 55th Street currently requires opening every Pattern parquet whose Pattern belongs to route 6, direction Northbound.

### Decision

Materialize two canonical derived views from the Mansueto data:

1. **Run-level view.** One row per stop-visit within a run. Columns include `run_id`, `route`, `direction`, `pattern_id`, `stop_id`, `stop_sequence_index`, `arrival_time`. This is essentially the union of all Mansueto Pattern parquets with normalized column names; we preserve Mansueto's project-constructed trip identifier as `run_id`.
2. **Stop-level view.** One row per (`stop_id`, `route`, `direction`). Value column is an ordered list of arrival timestamps aggregated across all Patterns that hit that stop for that route and direction. `pattern_id` is retained as a per-timestamp label so pattern-level regrouping is possible without rebuilding.

Preserve upstream identifiers (`trip_id`, `pattern_id`, `stop_id`) as passthrough columns. Do not invent replacement identifiers.

### Consequences

We maintain two derived artifacts, refreshed together whenever we pull new Mansueto data. Wait-time queries become a single-row lookup on the stop-level view; travel-time queries filter the run-level view to one run and join two stops within it; the average-travel-time-over-time chart is a groupby over the run-level view on date. Collapsing multiple Patterns into one `(route, direction)` row in the stop-level view means a rider who only cares about "will a 6 Northbound show up" gets the pooled empirical distribution, which is what they actually experience. If we later need pattern-level disaggregation (e.g., separating "6 Jackson Park Express" from "6 to 95th"), the retained `pattern_id` label makes it a query change, not a schema change. Exact column names in the Mansueto parquet are not yet verified; the ingestion task will confirm and adapt.

---

## ADR-002: No unreviewed LLM output reaches app users
Date: 2026-08-10
Status: Accepted

### Context

This project is likely to use LLMs at several points: to help write code, to draft explanatory text about what a distribution means for a rider, or to summarize route-level reliability. LLM output is fluent, plausible, and often wrong in ways a casual reader cannot detect. If unreviewed LLM prose ships to the app user, we are making public factual claims about CTA service that we have not actually verified — which undermines the whole reason to build this tool.

### Decision

No LLM output visible to the app user ships without a human review step. This applies especially to written explanations, natural-language summaries, insights, and any UI copy that presents itself as a statement of fact. Numerical or statistical output computed by our own code (distributions, aggregates, plots) is not covered by this rule; only content generated or paraphrased by an LLM.

### Consequences

Any feature that would otherwise auto-generate user-facing text needs a review gate before publication — a human-in-the-loop workflow, pre-generated and reviewed content shipped as static, or a clear "auto-generated, not reviewed" disclosure. This rules out features where the user requests explanatory text that must be produced in real time without disclosure. It preserves the project's credibility as a source of information about actual CTA performance and forces us to be explicit whenever we cross the line from computed output into interpreted text.

---

## ADR-001: Use Mansueto CTA Stop Watch processed parquet as the primary data source
Date: 2026-08-10
Status: Accepted

### Context

The project needs a historical record of when each CTA bus actually passed each stop, so it can compute empirical distributions of wait time and travel time. The CTA itself does not publish this: its public feed only exposes 5-minute snapshots of live bus positions, and its trip IDs are not unique enough to reconstruct trips reliably. The first iteration of this repo (preserved on the `legacy` branch) read raw daily-CSV location pings from the older Chi Hack Night Ghost Bus CloudFront bucket and would have required us to build our own trip-stitching and stop-imputation pipeline. In the meantime, the Mansueto Institute has taken over that pipeline, publishes a per-Pattern parquet file of imputed stop-level arrival times, and maintains it on an automated schedule.

### Decision

Consume the Mansueto processed parquet files at `https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch/processed_by_pid/trips_<PID>_full.parquet` as the primary data source. Do not maintain a parallel imputation pipeline.

### Consequences

We inherit Mansueto's methodology and are bound by its update cadence (roughly two-week lag observed as of 2026-08-10). We do not have to build or maintain a spatial-imputation pipeline, which saves substantial engineering effort. If the Mansueto bucket ever goes offline or diverges from our needs, we would need to fall back to raw pings; the legacy branch documents what that path looks like. Freshness must be probed manually (see the knowledge-vault note `cta-stop-watch-freshness-check`) because the bucket exposes no manifest.

---
