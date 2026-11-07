# Decisions

Architecture Decision Records (ADRs) for this project. **Newest at the top.** Past entries are historical record — never edit them. To reverse a decision, add a new ADR and mark the older one `Superseded by ADR-NNN`.

Statuses:
- **Proposed** — under discussion, not yet in effect
- **Accepted** — in effect
- **Superseded by ADR-NNN** — replaced by a later decision
- **Deprecated** — no longer in effect, not replaced

---

## ADR-010: Michigan Ave corridor speed is defined on segments between consecutive corridor stops
Date: 2026-11-07
Status: Accepted

### Context

The Michigan Ave corridor charts (`notebooks/michigan_ave_speed_plots.ipynb`) plot Mansueto's `speed_mph`, a
speed over each ~5-minute GPS ping, attached to stops. Moving `cta.michigan_ave_segment` onto the run-level view
(`specs/michigan-segment-from-view.md`) removes that column: the view carries arrival times, not ping speeds, and
CLAUDE.md rule 6 forbids mixing ping-interval and imputed speeds. A speed from arrivals belongs to the stretch
between two stops, not to a stop. Attaching it to stops leaves the first observed stop of every run without a value
(1,500 of 15,216 corridor rows on the 2026-10-29 archive fixture day; that stop is Roosevelt, where the new
northbound lane starts, for 283 of the 1,500 runs and Delaware for 335) or forces one stop's value to describe the
road after it while the others describe the road before. The two
measures also differ: on PID 6410 (151 NB, 2026-06-28 to 07-28) the median ping-interval speed at observed corridor
stops is 5.23 mph and the median stop-to-stop speed is 4.28 mph. ADR-009 adds a third source whose ~300 s arrivals
are unfit for stop-to-stop speed. The owner chose segments on 2026-11-07 while resolving the spec's open questions.

### Decision

Corridor speed is a property of a segment: a consecutive pair of stops in a direction sequence of
`cta.michigan_ave_segment.direction_stop_sequences()` (22 northbound, 18 southbound). For each run, a hop between
consecutive observed corridor stops has speed = getpatterns `pdist` difference ÷ arrival-time difference; the hop's
speed is assigned to every segment it covers, with `hop_n_segments` recording how many, and bucketed by the hop's
start arrival in America/Chicago. Every such row is used: stop times are imputed from GPS positions on every source,
so a hop covering several segments measures the same road over a longer stretch, and it mostly reflects a pattern
having no stop in between (1,510 of 1,513 such hops on the fixture day). Hops with a missing or non-positive distance, a non-positive time, or a
route distance more than 1.5 times the straight-line distance between their stops (the bus left Michigan between
them, as route 4 PID 25899 does on its Randolph, Columbus and Wacker loop) are dropped and counted, never given a NaN
speed. Segments are plotted at the midpoint latitude of their two stops, in
minutes per mile. Ping-interval `speed_mph` is never plotted alongside segment speeds, and arrivals from a source
with ~300 s pings (`source == "mansueto_raw"`, ADR-009) are excluded from segment speeds by the figure code via
`source` and `bracket_gap_s`. The DLSD-leak stop exclusion carries over to segments that touch a leak stop.

### Consequences

Every segment speed means the same thing, the corridor's first and last stops are covered by the segments next to
them, and speeds from the archive and from Mansueto arrivals use one definition. New charts are not comparable with
the existing ping-interval charts (about 18% slower on 151 NB), so the before-picture is built entirely on segment
speeds and labelled as such. Neighbouring segments covered by one hop share a value, which smooths the profile, and
pooled statistics weight a hop by the segments it covers; filtering on `hop_n_segments == 1` gives the comparison. Mansueto parquet arrivals are themselves imputed from ~5-minute pings, so their segment
speeds inherit that imputation error; the archive is the preferred source for the before-picture, with Mansueto
history for drift only. The speed-plot helpers gain a segment-aware leak filter and a per-segment stats helper, and
the speed-plot notebook must be re-pointed to segments (a follow-up item). Whether the leak exclusion is still needed
for stop-to-stop speeds is a measurement for the before-picture note. If segment speeds prove too noisy on short
segments, pooling adjacent segments is the fallback, as a new ADR.

---

## ADR-009: Mansueto raw daily positions are a bounded third source, read through our own imputation
Date: 2026-11-06
Status: Accepted (amends ADR-007 and ADR-004; does not supersede either)

### Context

On 2026-11-06, while reviewing the Mansueto `cta-stop-watch` repository for prior art, a HEAD sweep of
the bucket's `full_day_data/YYYY-MM-DD.csv` files showed that the raw 5-minute vehicle positions kept
being published after the per-pattern parquets froze: 71 day files from 2026-08-13 to 2026-10-27
(missing 09-30, 10-02, 10-03, 10-16, 10-17), nothing for 2026-07-28 to 2026-08-12, and nothing since
2026-10-28 (`docs/2026-11-06-mansueto-raw-positions.md`). A one-day profile (2026-09-15) found the same
core fields as the archive (`pdist` in feet, pattern id, vehicle id), a 300 s poll cadence,
minute-resolution vehicle timestamps, no scheduled-start key, and no checksum manifest. The parquets
remain frozen at 2026-07-28 and the upstream metrics job still runs but has no actual-service months
after July 2026. ADR-007 recorded 2026-07-28 to 2026-09-27 as covered by no source and deferred every
cross-source check until the parquet data edge moved; 46 of those days now have raw positions, and
25 days (2026-09-28 to 2026-10-27) exist in both the archive and the CSVs.

### Decision

1. The archive stays the primary live source (ADR-004 unchanged).
2. The Mansueto raw CSVs become a third source, `source='mansueto_raw'`, read through the same pair and
   imputation stages as the archive (`cta.archive.fix_pairs` / `impute_arrivals` shape, getpatterns
   `pdist` for stops), never through Mansueto's imputation. The adapter gets its own spec and its own
   named gap threshold: `MAX_BRACKET_GAP_S = 180` is an archive constant and would drop every 5-minute
   pair. Its run key is built from `vid`, `pid`, `origtatripno` and `data_date` because the CSV has no
   `sched_start_date` / `sched_start_sec`. `bracket_gap_s` is populated, so downstream filters can treat
   5-minute arrivals differently from 60 s ones.
3. The CSVs are history, not freshness. The refresh job probes their edge alongside the parquet edge and
   never depends on them; a day missing from the CSVs is a declared coverage gap in `cta/calendar.py`.
4. The deferred cross-source checks (ADR-004, ADR-007) no longer wait for the parquet edge. Two
   comparisons replace the single ADR-006 check: archive arrivals against CSV arrivals on the 25 overlap
   days, which isolates poll rate with the method held fixed; and our CSV or archive arrivals against
   the Mansueto parquet on the 2022 to July 2026 history, which isolates method. ADR-006's 20% bound is
   the tolerance for both until measured otherwise.
5. The parquet stays a frozen history source for drift and the side quests, labelled as Mansueto's
   imputation; time series show the 2026-07-28 to 2026-08-12 hole rather than bridge it.
6. Phase 3 schedule handling copies Mansueto's approach, not their code: historical feeds from the
   Transit.land archive, GTFS `shape_id` suffix as the pattern id, feed versions deduplicated by keeping
   each feed's days only up to the next feed's first day.

### Consequences

The coverage hole shrinks from two months to sixteen days, and cross-source bias becomes measurable
now instead of after an upstream resumption that may never come. We maintain a third adapter whose
source has no manifest and has already been down for nine days, so ingestion must verify by probing
and record what it found. Arrivals from this source carry about plus or minus 2.5 minutes of
interpolation uncertainty plus minute rounding: fine for headways and corridor travel times, unfit for
stop-to-stop speed, which the stop-level and figure code must respect through `bracket_gap_s` and
`source`. If the CSVs are retired upstream, the adapter and its coverage window become history in
`cta/calendar.py` and the parquet-only language of ADR-007 applies again.

---

## ADR-008: `stop_sequence_index` is the dense getpatterns stop rank on both adapters
Date: 2026-11-04
Status: Accepted (amends ADR-003; does not supersede it)

### Context

ADR-003 names `stop_sequence_index` without defining it. The archive adapter (specs/archive-adapter.md)
used the Bus Tracker `getpatterns` `seq`, which counts waypoints as well as stops: PID 18414 has 105
stops and a last `seq` of 319, and the fixture day reached 367. Mansueto's own `stop_sequence` is a
third numbering. The `± 1` neighbour idiom in `cta.dlsd_run_quality` and any "next stop" logic need
an index that is contiguous and means the same thing whichever source produced the row. The owner
resolved this on 2026-11-04 while closing the open questions of specs/mansueto-adapter.md.

### Decision

`cta.bustracker.pattern_stops_table` carries `stop_rank`: the dense 0-based rank of each stop within
its pattern by `seq` over `typ == 'S'` points only (`cta.bustracker.with_stop_rank` computes it for a
hand-built table). Both `cta.views.run_level_from_archive` and `cta.views.run_level_from_mansueto`
set `stop_sequence_index = stop_rank`. Neither `seq` nor Mansueto `stop_sequence` appears in the
run-level view.

### Consequences

Stops are indexed identically across sources, so travel-time and neighbour logic is source-agnostic
and the index of a stop is stable across archive days as long as the pattern is unchanged. The index
is tied to the getpatterns snapshot in the cache: when a pattern gains or loses a stop the ranks
after it shift, so a rebuilt cache can renumber history. Rows whose stop is absent from the current
pattern are dropped and counted (`stop_not_in_pattern`, about 1% of route 3 rows from July 2026
against a November 2026 pattern). Joining to a stop by `stop_id` is unaffected and remains the way
to address a stop across time.

---

## ADR-007: Mansueto StopWatch is a frozen history source until it resumes
Date: 2026-11-04
Status: Accepted (amends ADR-004; does not supersede it)

### Context

On 2026-11-04 the parquet footers of PIDs 18414, 18415 and 6414 all report `max(bus_stop_time)` on
2026-07-28, and every probed file carries `Last-Modified` 2026-07-28 (`docs/2026-11-04-mansueto-data-edge.md`).
The bucket has not been regenerated for over three months. The Transit Alerts archive starts
2026-09-28, so no service day exists in both sources and the two months in between are covered by
neither. ADR-004 assumed a ~2-week Mansueto lag, a standing cross-check on overlapping days, and
Mansueto as the maintained fallback for freshness. The first and second are not available today and
the third is weaker than stated.

### Decision

Treat Mansueto as a frozen history source with data edge `MANSUETO_DATA_EDGE = "2026-07-28"`
(named constant in `cta.mansueto`, re-measured by `cta.mansueto.data_edge(pid)` and recorded in
each download's `trips_<pid>_full.meta.json`). The archive is the only live source. The Mansueto
adapter is still built (ADR-003 run-level view, `source='mansueto'`), but it is validated by
same-source self-consistency against the legacy pipeline's recorded medians, not by a same-day
archive comparison. The ADR-004 cross-check on overlapping days, the Phase 1 overlap cross-check and
the Phase 3 Mansueto backfill are deferred until a re-measured data edge is later than 2026-09-28.

### Consequences

History back to 2022 remains usable for drift and for the DLSD and Michigan side quests, with
2026-07-28 to 2026-09-27 as a known hole that every time series must show, not bridge. Systematic
bias between sources cannot be measured yet; ADR-006's 20% bound stands as the only cross-source
check. Phase 3 refresh rests entirely on the archive, which ADR-004 already flagged as a single
volunteer's service. If Mansueto resumes, reopen this ADR: run the deferred cross-checks and revise
`specs/mansueto-adapter.md`'s acceptance list. If it never resumes, a later ADR should retire the
fallback language in ADR-004.

---

## ADR-006: Cross-source validation tolerance is 20% on per-pattern corridor medians
Date: 2026-11-03
Status: Accepted

### Context

`specs/archive-adapter.md` accepted the archive adapter if every kept Michigan Ave pattern with at
least 30 runs on the fixture day (2026-10-29) had a corridor median within 10% of the Mansueto
30-day median recorded in `notebooks/michigan_ave_kept_pids.json` (window ending ~2026-10-03). On
the committed fixture, 14 of 17 such patterns pass and three do not: 4524 (147 NB) at 1.12, 8119
(26 SB) at 0.86 and 19378 (4 NB) at 0.88. The median ratio over all 43 patterns with a result is
0.985. Two of the three were already outside 10% in the prototype table the spec cites. A single
day's median against a 30-day median from a month earlier carries day-to-day and seasonal variation
that 10% does not allow for; nothing in the per-stage QA points at the pipeline.

### Decision

The per-pattern tolerance for cross-source validation (archive vs Mansueto corridor medians, and
any later same-shape check such as the Mansueto adapter's) is 20%, applied to patterns with at
least 30 runs in the archive sample. `tests/test_views_archive.py` carries it as
`MAX_MEDIAN_RATIO_DEVIATION = 0.20`. The 10% figure in the spec's acceptance list is superseded.

### Consequences

The archive adapter's acceptance list is fully met and the test is a real gate again rather than an
xfail. A 20% bound will not catch a subtle systematic bias between sources; the standing cross-check
on overlapping days (ADR-004) and a future same-day comparison, once the Mansueto adapter exists,
are where that is measured. If a pattern drifts past 20% it is a finding to investigate, not a
reason to widen further without a new ADR.

---

## ADR-005: Importable package + DuckDB for position-scale data
Date: 2026-11-03
Status: Accepted

### Context

Logic currently lives in `notebooks/*.py` and is imported through `sys.path` hacks from notebooks
and tests. The new position archive is ~1M rows per day, ~30M per month; pandas-only processing
of consecutive-fix pairs at that scale is slow and memory-bound. The scorecard project showed that
DuckDB handles a full month in about a minute on a laptop and that SQL stages are easy to review.

### Decision

Create an importable package `cta/` (adapters, cleaning, imputation, views, calendar, QA). Scripts
and notebooks call into it; tests import it directly. Use DuckDB for ingestion and for any stage
over ~1M rows; functions return pandas DataFrames so notebooks stay pandas-native. Add
`requirements.txt` and a CI workflow running `pytest` with no network.

### Consequences

One-time migration of the three notebook helper modules. Agents get a stable import surface and a
test harness, which is what spec-driven work needs. DuckDB becomes a hard dependency.

---

## ADR-004: Add the Transit Alerts position archive as a second source; keep Mansueto for history
Date: 2026-11-03
Status: Accepted (amends ADR-001; does not supersede it)

### Context

The Chicago Transit Alerts archive (collected by chicago-transit-insights) publishes every CTA bus
position at ~60 s (30 s from 2026-11-01) as daily, checksummed files, from 2026-09-28 onward,
nightly. Mansueto provides imputed stop arrivals from ~5 min pings with history to ~2022 and a
~2 week lag. A one-day prototype reproduced the Mansueto corridor medians on Michigan Ave within
1% from the archive, and resolved a 20-minute southbound incident that 5-minute pings would smear.
The archive has no stop events, so using it means owning the stop-imputation step ADR-001 avoided.

### Decision

Consume both. The archive is the primary source for all dates it covers; Mansueto is the source for
earlier dates and for long-run drift. Each source has an adapter that emits the ADR-003 run-level
view with a `source` column. Stop pdist comes from Bus Tracker `getpatterns`. Cleaning rules are
adopted from the MIT-licensed cta-bus-speed-scorecard pipeline (dedup, trip key, gap/snap filters)
with attribution; the terminal trim and pattern-length filters are not adopted for stop-level views.

### Consequences

We own an imputation step and its QA, but at 5–10× the resolution of Mansueto's. Freshness improves
from ~2 weeks to ~1 day, which makes Phase 3 scheduled refresh realistic. Risk: the archive is run by
one volunteer and has had quota outages; the ingest must verify checksums and record gaps, and the
Mansueto adapter stays maintained as the fallback. Overlapping days (Sep 28 onward) are used as a
standing cross-check between sources.

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
