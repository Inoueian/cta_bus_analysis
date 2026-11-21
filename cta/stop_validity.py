"""Dated stop validity for patterns whose geometry changed under the same pid (specs/stop-validity-measurement.md).

A stop belongs to a pattern from a date (ADR-011, point 3). The dated geometry changes come from the committed pid
list; the per-stop windows are measured against raw pings and committed as
``notebooks/routes_8_65_66_stop_validity.json``.
"""

from __future__ import annotations

EPOCH_SLACK_DAYS = 45  # notebooks/eda_routes_8_65_66.ipynb 6.1: a stop first seen later than this after the pid's first day was added


def today_geometry_first_day(pid_file: dict) -> dict[str, str]:
    """Per pid, the first day of the geometry that is still current (the last ``geometry_changes`` entry)."""
    out: dict[str, str] = {}
    for change in pid_file.get("geometry_changes", []):
        pid = str(change["pid"])
        out[pid] = max(out.get(pid, ""), str(change["first_day_new"]))
    return out
