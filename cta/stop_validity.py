"""Dated stop validity for patterns whose geometry changed under the same pid (specs/stop-validity-measurement.md).

A stop belongs to a pattern from a date (ADR-011, point 3). The dated geometry changes come from the committed pid
list; the per-stop windows are measured against raw pings (``stop_validity_from_pings``) and committed as
``notebooks/routes_8_65_66_stop_validity.json``, which ``load_stop_validity`` reads back. The Mansueto adapter applies
the windows (specs/mansueto-stop-validity.md); this module changes no view.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from cta import geo

EPOCH_SLACK_DAYS = 45  # notebooks/eda_routes_8_65_66.ipynb 6.1: a stop first seen later than this after the pid's first day was added
VALIDITY_SAMPLE_DAYS = ("2025-07-15", "2025-09-16", "2025-10-14", "2026-09-15")  # notebook 6.2 Tuesdays from 2024-09-03 on; one inside every geometry period of the four pids
MAX_STOP_PING_DISTANCE_FT = 328.0  # 100 m (owner, 2026-11-21): measured 2026-11-21, served candidate distances reach 214 ft and unserved ones start at 486 ft with none between; 100 m is the gap's log-scale middle (323 ft)
REFERENCE_DAY = max(VALIDITY_SAMPLE_DAYS)  # today's geometry on all four pids, so every stop of a dominant pattern was served
MARGIN_FACTOR = 1.25  # a candidate distance within this factor of the threshold on either side (262 to 410 ft at 100 m) is too close to call: stop and report

SOURCE = "mansueto"
VALIDITY_TITLE = "Measured stop validity windows for routes 8 and 66 (specs/stop-validity-measurement.md)"
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "notebooks" / "routes_8_65_66_stop_validity.json"
PERIOD_COLUMNS = ["pid", "start", "end_exclusive", "sample_day"]
ROW_COLUMNS = ["route", "direction", "stop_id", "stop_name", "from_pid", "source", "first_arrival_day", "nearest_ping_ft", "valid_from"]
AMBIGUOUS_COLUMNS = ["route", "direction", "stop_id", "from_pid", "sample_day", "nearest_ping_ft"]


def today_geometry_first_day(pid_file: dict) -> dict[str, str]:
    """Per pid, the first day of the geometry that is still current (the last ``geometry_changes`` entry)."""
    out: dict[str, str] = {}
    for change in pid_file.get("geometry_changes", []):
        pid = str(change["pid"])
        out[pid] = max(out.get(pid, ""), str(change["first_day_new"]))
    return out


def _object_frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    """Frame of object columns, so a missing date stays ``None`` (pandas 3 would turn it into NaN in a string column)."""
    return pd.DataFrame({c: pd.Series([r.get(c) for r in rows], dtype="object") for c in columns})


def geometry_periods(pid_file: dict, pid: str, sample_days=VALIDITY_SAMPLE_DAYS) -> pd.DataFrame:
    """One row per geometry period of ``pid``: ``start`` and ``end_exclusive`` (ISO days, ``None`` when open) and ``sample_day``.

    The history is cut at each ``first_day_new`` of the pid in ``geometry_changes``. ``sample_day`` is the latest of
    ``sample_days`` inside the period; a period with none raises, naming the pid and the period.
    """
    pid = str(pid)
    changes = sorted(str(c["first_day_new"]) for c in pid_file.get("geometry_changes", []) if str(c["pid"]) == pid)
    rows = []
    for start, end in zip([None] + changes, changes + [None]):
        inside = [d for d in sample_days if (start is None or d >= start) and (end is None or d < end)]
        if not inside:
            raise ValueError(
                f"pid {pid}: no sample day inside the period {start or 'start of history'} to {end or 'end of history'} "
                f"(sample days {list(sample_days)})"
            )
        rows.append({"pid": pid, "start": start, "end_exclusive": end, "sample_day": max(inside)})
    return _object_frame(rows, PERIOD_COLUMNS)


def _pings_by_pid_day(pings: pd.DataFrame) -> dict[tuple[str, str], tuple]:
    """(pid, data_date) -> latitudes and longitudes of the fixes that have both; a fix with a null coordinate is skipped."""
    good = pings.dropna(subset=["lat", "lon"])
    keyed = good.assign(pid=good["pid"].astype(str), data_date=good["data_date"].astype(str))
    return {key: (g["lat"].to_numpy(), g["lon"].to_numpy()) for key, g in keyed.groupby(["pid", "data_date"])}


def stop_validity_from_pings(
    candidates: pd.DataFrame, stops: pd.DataFrame, pings: pd.DataFrame, periods: pd.DataFrame, max_ft: float
) -> pd.DataFrame:
    """The JSON's rows: per candidate stop, its distance to the nearest ping in each period and the day it became valid.

    ``candidates``: ``route``, ``direction``, ``stop_id``, ``from_pid``, ``first_arrival_day`` (and ``stop_name``).
    ``stops``: ``cta.bustracker.pattern_stops_table`` (``pid``, ``stpid``, ``lat``, ``lon``). ``pings``: raw fixes
    (``pid``, ``data_date``, ``lat``, ``lon``). ``periods``: ``geometry_periods`` of every candidate pid.
    ``nearest_ping_ft`` maps each period's sample day to the feet from the stop to the nearest fix of the candidate's
    pid dated that day; the stop is served in the period when that is at most ``max_ft``. ``valid_from`` is the start of
    the earliest period from which every later period is served (``None``: served in all). A stop not served in the
    last period raises: today's stop missed on today's geometry is a threshold or data fault.
    """
    keyed_stops = stops.assign(pid=stops["pid"].astype(str), stpid=stops["stpid"].astype(str)).drop_duplicates(["pid", "stpid"])
    position = {(r.pid, r.stpid): (r.lat, r.lon, getattr(r, "stpnm", None)) for r in keyed_stops.itertuples()}
    fixes = _pings_by_pid_day(pings)
    rows = []
    for cand in candidates.to_dict("records"):
        pid, stop = str(cand["from_pid"]), str(cand["stop_id"])
        if (pid, stop) not in position:
            raise ValueError(f"candidate stop {stop} is not in the pattern of pid {pid}")
        lat, lon, name = position[(pid, stop)]
        pid_periods = periods[periods["pid"].astype(str) == pid]
        if pid_periods.empty:
            raise ValueError(f"no geometry periods for pid {pid}")
        distances: dict[str, float] = {}
        served: list[bool] = []
        for period in pid_periods.itertuples():
            day = str(period.sample_day)
            if (pid, day) not in fixes:
                raise ValueError(f"pid {pid}: no pings with a position dated sample day {day}")
            feet = geo.nearest_feet(lat, lon, *fixes[(pid, day)])
            distances[day] = round(feet, 1)
            served.append(feet <= max_ft)
        if not served[-1]:
            raise ValueError(
                f"stop {stop} (pid {pid}) is not served in its last period: nearest ping {list(distances.values())[-1]} ft "
                f"on {list(distances)[-1]} against {max_ft} ft; a threshold or data fault, not a window"
            )
        first = len(served) - 1
        while first > 0 and served[first - 1]:
            first -= 1
        valid_from = None if first == 0 else str(pid_periods.iloc[first]["start"])
        given = cand.get("stop_name")
        stop_name = str(given) if given is not None and not pd.isna(given) else (None if name is None else str(name))
        rows.append(
            {
                "route": str(cand["route"]), "direction": str(cand["direction"]), "stop_id": stop, "stop_name": stop_name,
                "from_pid": pid, "source": SOURCE, "first_arrival_day": str(cand["first_arrival_day"]),
                "nearest_ping_ft": distances, "valid_from": valid_from,
            }
        )
    return _object_frame(rows, ROW_COLUMNS)


def ambiguous_distances(rows: pd.DataFrame, max_ft: float) -> pd.DataFrame:
    """Candidate-period distances within ``MARGIN_FACTOR`` of ``max_ft`` on either side (bounds included).

    The spec says to stop and report on any such distance rather than choose a side of the threshold.
    """
    found = []
    for row in rows.to_dict("records"):
        for day, feet in row["nearest_ping_ft"].items():
            if max_ft / MARGIN_FACTOR <= feet <= max_ft * MARGIN_FACTOR:
                found.append({**{c: row.get(c) for c in AMBIGUOUS_COLUMNS if c != "sample_day" and c != "nearest_ping_ft"},
                              "sample_day": day, "nearest_ping_ft": feet})
    return _object_frame(found, AMBIGUOUS_COLUMNS)


def pattern_stop_distances(stops: pd.DataFrame, pings: pd.DataFrame, pids: list[str], day: str) -> pd.DataFrame:
    """Per stop of each pid's pattern, the feet to the nearest fix of that pid dated ``day`` (``pid``, ``stpid``, ``nearest_ping_ft``)."""
    fixes = _pings_by_pid_day(pings)
    rows = []
    for pid in (str(p) for p in pids):
        if (pid, day) not in fixes:
            raise ValueError(f"pid {pid}: no pings with a position dated {day}")
        for stop in stops[stops["pid"].astype(str) == pid].itertuples():
            rows.append({"pid": pid, "stpid": str(stop.stpid), "nearest_ping_ft": geo.nearest_feet(stop.lat, stop.lon, *fixes[(pid, day)])})
    return pd.DataFrame(rows, columns=["pid", "stpid", "nearest_ping_ft"])


def read_stop_validity_file(path: Path | None = None) -> dict:
    """The committed JSON as written: ``title``, the threshold and sample days it was measured with, and ``rows``."""
    return json.loads(Path(path or DEFAULT_PATH).read_text())


REVIEW_COLUMNS = ["measured_valid_from", "not_served"]  # added by the review (ADR-014): the measured date and the intervals not served
DROPPED_RUN_COLUMNS = ["route", "pid", "vehicle_id", "service_date", "first_arrival_from", "first_arrival_to", "rule", "evidence", "decided"]


def _review_key(entry: dict) -> tuple[str, str]:
    return str(entry["from_pid"]), str(entry["stop_id"])


def _check_review_keys(review: list[dict], rows: list[dict]) -> None:
    """Raise ``ValueError`` when a review entry names a (pid, stop) that is not among the measured rows."""
    known = {(str(r["from_pid"]), str(r["stop_id"])) for r in rows}
    unknown = [f"{pid}/{stop}" for pid, stop in (_review_key(e) for e in review) if (pid, stop) not in known]
    if unknown:
        raise ValueError(f"review entries name stops that are not among the measured rows: {', '.join(unknown)}")


def load_stop_validity(path: Path | None = None) -> pd.DataFrame:
    """The applied windows: ``ROW_COLUMNS`` plus ``measured_valid_from`` and ``not_served`` (list of ``(from, to)`` ISO days, inclusive).

    ``valid_from`` is the owner's reviewed date where a review entry has one, else the measured one (ADR-014; the
    measured rows stay as measured). Only keys with a window or an interval come back: the stops whose earlier
    arrivals, or arrivals inside an interval, are not real.
    """
    data = read_stop_validity_file(path)
    rows, review = data["rows"], data.get("review", [])
    _check_review_keys(review, rows)
    by_key = {_review_key(e): e for e in review}
    out = []
    for row in rows:
        entry = by_key.get(_review_key(row), {})
        applied = {c: row.get(c) for c in ROW_COLUMNS}
        applied["measured_valid_from"] = row.get("valid_from")
        applied["valid_from"] = entry.get("valid_from") or row.get("valid_from")
        applied["not_served"] = [(str(a), str(b)) for a, b in entry.get("not_served", [])]
        if applied["valid_from"] is not None or applied["not_served"]:
            out.append(applied)
    frame = _object_frame(out, ROW_COLUMNS + REVIEW_COLUMNS)
    if frame.duplicated(["route", "direction", "stop_id"]).any():
        raise ValueError("two applied windows share a (route, direction, stop_id) key")
    return frame


def load_dropped_runs(path: Path | None = None) -> pd.DataFrame:
    """The committed ``dropped_runs`` (``DROPPED_RUN_COLUMNS``): runs whose arrivals the pings did not observe (ADR-015)."""
    return _object_frame(read_stop_validity_file(path).get("dropped_runs", []), DROPPED_RUN_COLUMNS)


def write_validity_file(
    rows: pd.DataFrame, path: Path | None = None, *, title: str = VALIDITY_TITLE,
    max_ft: float = MAX_STOP_PING_DISTANCE_FT, sample_days=VALIDITY_SAMPLE_DAYS,
) -> Path:
    """Write the committed JSON: the header, the threshold and sample days it was measured with, and ``rows``.

    The file's existing ``review`` and ``dropped_runs`` are kept. Raises ``ValueError``, writing nothing, when a review
    entry names a (pid, stop) that is not among ``rows``.
    """
    path = Path(path or DEFAULT_PATH)
    records = rows.to_dict("records")
    kept = {k: v for k, v in (read_stop_validity_file(path) if path.is_file() else {}).items() if k in ("review", "dropped_runs")}
    _check_review_keys(kept.get("review", []), records)
    out = {"title": title, "max_stop_ping_distance_ft": max_ft, "sample_days": list(sample_days), "rows": records, **kept}
    path.write_text(json.dumps(out, indent=1) + "\n")
    return path
