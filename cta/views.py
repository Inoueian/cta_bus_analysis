"""Canonical views (ADR-003): ``run_level_from_archive`` and ``run_level_from_mansueto`` produce the same
run-level table (ADR-004) from the two sources; ``stop_sequence_index`` is the dense getpatterns ``stop_rank``
on both (specs/mansueto-adapter.md)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from cta import archive, bustracker, calendar, mansueto

SOURCE_ARCHIVE = "archive"
SOURCE_MANSUETO = mansueto.SOURCE_MANSUETO
MANSUETO_QA_COLUMNS = ["pid"] + mansueto.QA_COLUMNS

RUN_LEVEL_COLUMNS = [
    "run_id",
    "route",
    "direction",
    "pattern_id",
    "stop_id",
    "stop_sequence_index",
    "arrival_time",
    "bracket_gap_s",
    "vehicle_id",
    "service_date",
    "calendar_flag",
    "source",
]


LEGACY_TRIP_COLUMNS = {
    "run_id": "unique_trip_vehicle_day",
    "stop_id": "stpid",
    "arrival_time": "bus_stop_time",
    "pattern_id": "pid",
    "direction": "rtdir",
    "stop_sequence_index": "stop_sequence",
}  # the Mansueto parquet names that cta.michigan_ave_segment's legacy helpers read (specs/michigan-segment-from-view.md)


def legacy_trip_columns(view: pd.DataFrame) -> pd.DataFrame:
    """``view`` with the six ADR-003 columns renamed to the legacy trip-table names; values and other columns untouched."""
    return view.rename(columns=LEGACY_TRIP_COLUMNS)


def _empty_run_level() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="object") for c in RUN_LEVEL_COLUMNS})
    df["stop_sequence_index"] = df["stop_sequence_index"].astype("int64")
    df["bracket_gap_s"] = df["bracket_gap_s"].astype("float64")
    df["arrival_time"] = pd.to_datetime(df["arrival_time"], utc=True)
    return df


def run_level_from_archive(
    days: list[str],
    pids: list[str],
    *,
    con: duckdb.DuckDBPyConnection | None = None,
    index: dict | None = None,
    raw_dir: Path | None = None,
    pattern_stops: pd.DataFrame | None = None,
    pattern_cache_dir: Path | None = None,
) -> pd.DataFrame:
    """One row per (run, stop) with an imputed arrival time, for ``days`` and ``pids`` (ADR-003 run-level view).

    Days already in ``con`` (``archive_ingest``) are used as they are; any other day is downloaded
    into ``raw_dir`` from ``index`` (which also supplies ``known_gaps``) and ingested first.
    ``pattern_stops`` defaults to the getpatterns cache under ``pattern_cache_dir``.
    """
    pids = list(dict.fromkeys(str(p) for p in pids))
    if con is None:
        con = archive.open_archive_db()
    if pattern_stops is None:
        pattern_stops = bustracker.pattern_stops_table(pids, pattern_cache_dir)
    gaps = calendar.known_gaps(index)
    frames = []
    for day in days:
        if day not in archive.ingested_days(con):
            if index is None or raw_dir is None:
                raise ValueError(f"{day} is not ingested and no index/raw_dir was given to fetch it")
            meta = archive.day_file_meta(index, day)
            archive.ingest_day(con, meta, archive.ensure_day_file(meta, raw_dir))
        fixes = archive.clean_fixes(con, day, pids)
        pairs = archive.fix_pairs(con, day, fixes, known_gaps=gaps)
        frames.append(archive.impute_arrivals(con, day, pairs, pattern_stops))
    if not frames or all(f.empty for f in frames):
        return _empty_run_level()
    arr = pd.concat(frames, ignore_index=True)
    view = pd.DataFrame(
        {
            "run_id": arr["run_id"].astype(str),
            "route": arr["route"].astype(str),
            "direction": arr["rtdir"].astype(str),
            "pattern_id": arr["pid"].astype(str),
            "stop_id": arr["stpid"].astype(str),
            "stop_sequence_index": arr["stop_rank"].astype("int64"),
            "arrival_time": arr["arrival_time"],
            "bracket_gap_s": arr["bracket_gap_s"].astype("float64"),
            "vehicle_id": arr["vehicle_id"].astype(str),
            "service_date": arr["service_date"].astype(str),
        }
    )
    view["calendar_flag"] = calendar.calendar_flag(view["service_date"], index=index)
    view["source"] = SOURCE_ARCHIVE
    view = view.sort_values(["service_date", "pattern_id", "run_id", "stop_sequence_index"]).reset_index(drop=True)
    return view[RUN_LEVEL_COLUMNS]


def _empty_mansueto_qa() -> pd.DataFrame:
    qa = pd.DataFrame({c: pd.Series(dtype="object") for c in MANSUETO_QA_COLUMNS})
    for c in ("rows_in", "rows_out", "count"):
        qa[c] = qa[c].astype("int64")
    return qa


def mansueto_view_from_trips(
    trips: pd.DataFrame, pattern_stops: pd.DataFrame, *, pids: list[str] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run-level view and QA table from ``cta.mansueto.read_trips`` output (any number of pids).

    Cleaning runs per pid through ``cta.mansueto.clean_trips``; the QA table gets a ``pid`` column in
    front of the stage rows. ``pids`` lists the pids that must appear in the QA table even with no rows.
    ``bracket_gap_s`` is NaN: Mansueto does not publish ping times, so downstream code must treat NaN
    as unknown, not zero. ``calendar_flag`` carries holidays only: archive ``known_gaps`` are Transit
    Alerts outages, not Mansueto outages.
    """
    pattern_stops = bustracker.with_stop_rank(pattern_stops)
    wanted = list(dict.fromkeys(str(p) for p in (pids or [])))
    present = list(dict.fromkeys(trips["pid"].astype(str))) if len(trips) else []
    frames, qas = [], []
    null_time = trips.attrs.get(mansueto.ATTR_NULL_TIME_ROWS, 0)  # int for the whole frame, or {pid: int}
    for pid in wanted + [p for p in present if p not in wanted]:
        part = trips[trips["pid"].astype(str) == pid].copy() if len(trips) else trips.copy()
        part.attrs[mansueto.ATTR_NULL_TIME_ROWS] = null_time.get(pid, 0) if isinstance(null_time, dict) else null_time
        clean, qa = mansueto.clean_trips(part, pattern_stops)
        qa.insert(0, "pid", pid)
        qas.append(qa)
        if len(clean):
            frames.append(clean)
    qa_table = pd.concat(qas, ignore_index=True)[MANSUETO_QA_COLUMNS] if qas else _empty_mansueto_qa()
    if not frames:
        return _empty_run_level(), qa_table
    clean = pd.concat(frames, ignore_index=True)
    view = pd.DataFrame(
        {
            "run_id": clean["run_id"].astype(str),
            "route": clean["route"].astype(str),
            "direction": clean["rtdir"].astype(str),
            "pattern_id": clean["pid"].astype(str),
            "stop_id": clean["stpid"].astype(str),
            "stop_sequence_index": clean["stop_rank"].astype("int64"),
            "arrival_time": clean["bus_stop_time"],
            "bracket_gap_s": np.full(len(clean), np.nan, dtype="float64"),
            "vehicle_id": clean["vehicle_id"].astype(str),
            "service_date": clean["service_date"].astype(str),
        }
    )
    view["calendar_flag"] = calendar.calendar_flag(view["service_date"], index=None)
    view["source"] = SOURCE_MANSUETO
    view = view.sort_values(["service_date", "pattern_id", "run_id", "stop_sequence_index"]).reset_index(drop=True)
    return view[RUN_LEVEL_COLUMNS], qa_table


def run_level_from_mansueto_with_qa(
    pids: list[str],
    *,
    parquet_dir: Path,
    pattern_stops: pd.DataFrame | None = None,
    pattern_cache_dir: Path | None = None,
    start=None,
    end=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``run_level_from_mansueto`` plus its QA table (one row per pid, stage, reason).

    Each pid is read from ``trips_<pid>_full.parquet`` under ``parquet_dir`` when that file exists,
    otherwise from every parquet there filtered to the pid (the committed fixtures hold several pids
    per file). ``pattern_stops`` defaults to the getpatterns cache under ``pattern_cache_dir``.
    """
    pids = list(dict.fromkeys(str(p) for p in pids))
    if pattern_stops is None:
        pattern_stops = bustracker.pattern_stops_table(pids, pattern_cache_dir)
    frames = []
    null_time: dict[str, int] = {}
    for pid in pids:
        for path in mansueto.parquet_files_for_pid(parquet_dir, pid):
            trips = mansueto.read_trips(path, pid=pid, start=start, end=end)
            null_time[pid] = null_time.get(pid, 0) + int(trips.attrs.get(mansueto.ATTR_NULL_TIME_ROWS, 0))
            if len(trips):
                frames.append(trips)
    if frames:
        trips = pd.concat(frames, ignore_index=True)
    else:
        trips = pd.DataFrame({c: pd.Series(dtype="object") for c in mansueto.TRIP_COLUMNS})
    trips.attrs[mansueto.ATTR_NULL_TIME_ROWS] = null_time
    return mansueto_view_from_trips(trips, pattern_stops, pids=pids)


def run_level_from_mansueto(
    pids: list[str],
    *,
    parquet_dir: Path,
    pattern_stops: pd.DataFrame | None = None,
    pattern_cache_dir: Path | None = None,
    start=None,
    end=None,
) -> pd.DataFrame:
    """One row per (run, stop) from the Mansueto StopWatch parquets (ADR-003 run-level view, ``source='mansueto'``)."""
    view, _ = run_level_from_mansueto_with_qa(
        pids, parquet_dir=parquet_dir, pattern_stops=pattern_stops, pattern_cache_dir=pattern_cache_dir, start=start, end=end
    )
    return view
