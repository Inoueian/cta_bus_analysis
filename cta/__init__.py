"""CTA Bus Wait & Travel Time Explorer: ingestion adapters, cleaning, imputation, views and QA (ADR-005).

Modules, one per data source plus the shared layers:

- ``bustracker``: Bus Tracker API client, daily budget, throttle, ``getpatterns`` fetch and the disk
  cache it alone owns, reader included (specs/split-cta-api.md).
- ``mansueto``: StopWatch CloudFront URL helpers, parquet reader, cleaning stages with QA, footer
  ``data_edge`` probe, ``fetch_parquet`` (specs/mansueto-adapter.md).
- ``archive``: Transit Alerts position archive ingest, cleaning, fix pairs, stop-arrival imputation
  (specs/archive-adapter.md).
- ``calendar``: holidays, archive outages, declared source coverage and Mansueto freshness in one
  place; rows are flagged, never dropped (specs/calendar-module.md).
- ``views``: the ADR-003 run-level view from any of the three sources (``run_level_from_archive``,
  ``run_level_from_mansueto``, ``run_level_from_mansueto_raw``).
- ``qa``: the QA columns, the per-stage row builder ``qa_rows`` and ``stage_totals``; imports nothing
  from ``cta`` (specs/qa-helper.md).
- ``qa_baseline``: the fixture QA cases, ``diff_qa`` and the baseline file behind ``scripts/qa.py`` and
  ``/qa``; a development tool tied to the checkout (specs/qa-skill.md).
- ``stop_validity``: dated stop windows for patterns whose geometry changed under one pid: the dated
  changes, the per-stop measurement against raw pings and the loader of the committed
  ``notebooks/routes_8_65_66_stop_validity.json`` (specs/stop-validity-measurement.md).
- ``geo``: great-circle distances in feet; imports nothing from ``cta`` (specs/stop-validity-measurement.md).
- ``dlsd_run_quality``, ``michigan_ave_segment``: helpers migrated from ``notebooks/``
  (specs/package-migration.md); their JSON snapshots stay under ``notebooks/``.
"""
