"""Canonical views (ADR-003). ``run_level_from_archive`` is the archive adapter's output (ADR-004)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from cta import archive, bustracker, calendar

SOURCE_ARCHIVE = "archive"

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
            "stop_sequence_index": arr["seq"].astype("int64"),
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
