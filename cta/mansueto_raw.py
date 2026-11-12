"""Mansueto raw day CSVs (``full_day_data/YYYY-MM-DD.csv``): verified fetch, read, clean fixes, fix pairs, QA
(specs/mansueto-raw-adapter.md, ADR-009).

Each day file holds raw Bus Tracker positions polled every ~300 s, Chicago calendar day 00:00 to 23:55,
with ``tmstmp`` as ``YYYYMMDD HH:MM`` wall time and ``pdist`` in feet. The bucket publishes no manifest,
so ``fetch_day`` records the HEAD (bytes, Last-Modified) next to the download and refuses a later
download whose HEAD differs. Positions run through the archive's pair and imputation stages
(``cta.archive.fix_pairs`` with ``MAX_RAW_BRACKET_GAP_S``, ``cta.archive.impute_arrivals``); never through
Mansueto's own imputation. ``cta.views.run_level_from_mansueto_raw`` assembles the ADR-003 view.

Run key (ADR-009): ``run_id = f"{vid}-{pid}-{origtatripno}-{data_date}"``; ``service_date = data_date``.
Each stage records QA rows in ``archive_qa`` on a connection from ``open_db``; ``qa(con, day)`` returns them.

Never pass an ``open_db`` connection to ``cta.archive`` ingest (``ingest_day``, ``clean_fixes``): on the
25 days both sources cover, the two would overwrite each other's ``clean``, ``pairs`` and ``impute`` QA
rows. This module refuses a connection that holds archive ingests or lacks its marker table; the archive
side is not guarded.

Known limits, accepted by the owner on 2026-11-10 and not corrected here (docs/playbook.md gotchas):
- arrivals run 0 to 60 s early, because ``tmstmp`` is truncated to the minute
  ("Mansueto raw `tmstmp` is truncated to the minute");
- rows with a null ``origtatripno`` are dropped, e.g. route 47 on 2026-10-22
  ("Mansueto raw `origtatripno` can be null");
- runs split at local midnight and ``service_date`` is the calendar date
  ("Mansueto raw day files are calendar days, not service days");
- arrivals bracketed by one missed poll (``bracket_gap_s`` 540 to 660) are kept; downstream filters decide,
  using ``source`` because ``bracket_gap_s`` is never NaN here.
No speed column (CLAUDE.md Rule 6). Identifiers are strings; timestamps are tz-aware UTC at every boundary.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
from pathlib import Path

import duckdb
import pandas as pd

from cta import archive, mansueto

SOURCE_MANSUETO_RAW = "mansueto_raw"  # ADR-009 source column
# 2026-10-22 profile: 97% of pairs at 240/300/360 s, one-missed-poll cluster ends at 660 s; drops 85 of 21,834
# Michigan pairs (0.4%). Owner chose 660 over 420 on 2026-11-10 (docs/2026-11-10-mansueto-raw-day-profile.md).
MAX_RAW_BRACKET_GAP_S = 660.0
RAW_TZ = mansueto.MANSUETO_TZ  # alias: to_utc localizes with MANSUETO_TZ; fixes land within 60 s of archive UTC
TMSTMP_FORMAT = "%Y%m%d %H:%M"  # profile: minute resolution, seconds truncated

STAGES = ("read", "clean", "pairs", "impute")
REASON_NULL_KEY = archive.REASON_NULL_KEY
REASON_OTHER_DATA_DATE = "other_data_date"
REASON_DST_AMBIGUOUS = mansueto.REASON_DST_AMBIGUOUS
REASON_DUPLICATE_FIX = archive.REASON_DUPLICATE_FIX

MARKER_TABLE = "mansueto_raw_db"
POSITION_COLUMNS = ["route", "pid", "vehicle_id", "origtatripno", "data_date", "tmstmp", "vehicle_ts", "pdist", "lat", "lon"]
_ID_COLUMNS = {"rt": "route", "pid": "pid", "vid": "vehicle_id", "origtatripno": "origtatripno", "data_date": "data_date"}


# --- fetch ----------------------------------------------------------------------------------------


def day_url(day: str) -> str:
    return f"{mansueto.BASE}/full_day_data/{day}.csv"


def meta_path(csv_path: Path) -> Path:
    csv_path = Path(csv_path)
    return csv_path.with_name(csv_path.name.split(".")[0] + ".meta.json")


def _count_rows(path: Path) -> int:
    with Path(path).open("rb") as f:
        lines = sum(chunk.count(b"\n") for chunk in iter(lambda: f.read(1 << 20), b""))
    return max(lines - 1, 0)


def fetch_day(day: str, dest_dir: Path) -> Path:
    """Local copy of ``full_day_data/<day>.csv`` in ``dest_dir`` plus ``<day>.meta.json`` (url, bytes,
    last_modified, fetched_at, rows).

    A 404 is a coverage gap (``FileNotFoundError``). A cached file whose metadata matches the HEAD is
    returned without downloading; metadata that differs raises and is never overwritten. A download whose
    size differs from the HEAD raises and leaves nothing behind.
    """
    url = day_url(day)
    try:
        head = mansueto.http_head(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(f"no Mansueto raw day file for {day} (coverage gap): {url}") from exc
        raise
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{day}.csv"
    meta_file = meta_path(path)
    if meta_file.is_file():
        meta = json.loads(meta_file.read_text())
        if (meta.get("bytes"), meta.get("last_modified")) != (head["bytes"], head["last_modified"]):
            raise ValueError(
                f"{url} changed since it was fetched: recorded bytes={meta.get('bytes')} "
                f"Last-Modified={meta.get('last_modified')}, bucket now bytes={head['bytes']} "
                f"Last-Modified={head['last_modified']}; re-measure (ADR-009) before replacing {path}"
            )
        if path.is_file() and path.stat().st_size == head["bytes"]:
            return path
    temp = path.with_name(path.name + ".part")
    try:
        mansueto.download(url, temp)
        size = temp.stat().st_size
        if size != head["bytes"]:
            raise ValueError(f"download of {url} is {size} bytes, HEAD reported {head['bytes']}")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    meta = {
        "url": url, "bytes": head["bytes"], "last_modified": head["last_modified"],
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "rows": _count_rows(path),
    }
    meta_file.write_text(json.dumps(meta, indent=1) + "\n")
    return path


def day_file(csv_dir: Path, day: str) -> Path:
    """The one file for ``day`` in ``csv_dir``: ``<day>.csv``, ``<day>.csv.gz`` or ``mansueto_raw_<day>_*.csv.gz``."""
    csv_dir = Path(csv_dir)
    found = [p for p in (csv_dir / f"{day}.csv", csv_dir / f"{day}.csv.gz") if p.is_file()]
    found += sorted(csv_dir.glob(f"mansueto_raw_{day}_*.csv.gz"))
    if not found:
        raise FileNotFoundError(f"no Mansueto raw file for {day} in {csv_dir}")
    if len(found) > 1:
        raise ValueError(f"several Mansueto raw files for {day} in {csv_dir}: {[p.name for p in found]}")
    return found[0]


# --- read -----------------------------------------------------------------------------------------


def read_day(path: Path, pids: list[str] | None = None) -> pd.DataFrame:
    """One row per CSV row of the requested pids (all when ``pids`` is None); nothing dropped.

    Identifiers are strings (through ``cta.mansueto._id_str``), ``tmstmp`` is kept as published,
    ``vehicle_ts`` is its UTC instant (Chicago wall time, no correction for the truncated seconds;
    ambiguous or nonexistent DST times are NaT).
    """
    con = duckdb.connect()
    try:
        raw = con.execute("SELECT * FROM read_csv(?, header=true, all_varchar=true)", [str(path)]).df()
    finally:
        con.close()
    if pids is not None:
        wanted = {mansueto._id_str(p) for p in pids}
        raw = raw[raw["pid"].map(lambda v: mansueto._id_str(v) if v is not None else None).isin(wanted)]
    out = pd.DataFrame(index=raw.index)
    for src, col in _ID_COLUMNS.items():
        values = raw[src]
        mapping = {v: mansueto._id_str(v) for v in values.dropna().unique()}
        out[col] = values.map(mapping).astype("object")
        out.loc[values.isna(), col] = None
    out["tmstmp"] = raw["tmstmp"].astype("object")
    out["vehicle_ts"] = mansueto.to_utc(pd.to_datetime(raw["tmstmp"], format=TMSTMP_FORMAT))
    for c in ("pdist", "lat", "lon"):
        out[c] = pd.to_numeric(raw[c]).astype("float64")
    return out[POSITION_COLUMNS].reset_index(drop=True)


# --- database and QA ------------------------------------------------------------------------------


def open_db(db_path: Path | None = None, **kwargs) -> duckdb.DuckDBPyConnection:
    """DuckDB connection (in-memory by default) with the archive QA tables and this module's marker table."""
    con = archive.open_archive_db(db_path, **kwargs)
    con.execute(f"CREATE TABLE IF NOT EXISTS {MARKER_TABLE}(source VARCHAR)")
    if con.execute(f"SELECT count(*) FROM {MARKER_TABLE}").fetchall()[0][0] == 0:
        con.execute(f"INSERT INTO {MARKER_TABLE} VALUES (?)", [SOURCE_MANSUETO_RAW])
    check_db(con)
    return con


def check_db(con: duckdb.DuckDBPyConnection) -> None:
    """Refuse a connection not from ``open_db`` or one holding archive ingests (QA rows would collide)."""
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    if MARKER_TABLE not in tables:
        raise ValueError("connection was not opened with cta.mansueto_raw.open_db(); refusing to share archive QA tables")
    if "archive_ingest" in tables and con.execute("SELECT count(*) FROM archive_ingest").fetchall()[0][0]:
        raise ValueError("connection holds archive days in archive_ingest; Mansueto raw QA rows would overwrite them")


def qa(con: duckdb.DuckDBPyConnection, day: str) -> pd.DataFrame:
    """QA table for one day: one row per (stage, reason); counts sum to rows_in - rows_out."""
    return archive.qa(con, day)


# --- stages ---------------------------------------------------------------------------------------


def clean_fixes(con: duckdb.DuckDBPyConnection, day: str, positions: pd.DataFrame) -> pd.DataFrame:
    """``read_day`` output to ``cta.archive.CLEAN_FIX_COLUMNS``: one row per (run_id, vehicle_ts), min pdist.

    Records stage ``read`` (nothing dropped) and stage ``clean``, dropping in order: a null run-key field,
    ``pdist`` or ``tmstmp``; a ``data_date`` other than ``day`` (stale fixes of the previous day's runs);
    a DST-ambiguous ``vehicle_ts``; duplicate (run_id, vehicle_ts) fixes.
    """
    check_db(con)
    n = len(positions)
    archive._record_qa(con, day, "read", n, n, {})
    key = ["vehicle_id", "pid", "origtatripno", "data_date", "pdist", "tmstmp"]
    p = positions[positions[key].notna().all(axis=1)]
    n_nonnull = len(p)
    p = p[p["data_date"] == day]
    n_day = len(p)
    p = p[p["vehicle_ts"].notna()]
    n_dst = len(p)
    p = p.assign(
        run_id=p["vehicle_id"] + "-" + p["pid"] + "-" + p["origtatripno"] + "-" + p["data_date"],
        service_date=p["data_date"],
    )
    fixes = (
        p.sort_values(["run_id", "vehicle_ts", "pdist"], kind="stable")
        .drop_duplicates(["run_id", "vehicle_ts"], keep="first")
        .reset_index(drop=True)[archive.CLEAN_FIX_COLUMNS]
    )
    for c in ("route", "pid", "vehicle_id", "run_id", "service_date"):
        fixes[c] = fixes[c].astype("object")
    archive._record_qa(
        con, day, "clean", n, len(fixes),
        {REASON_NULL_KEY: n - n_nonnull, REASON_OTHER_DATA_DATE: n_nonnull - n_day,
         REASON_DST_AMBIGUOUS: n_day - n_dst, REASON_DUPLICATE_FIX: n_dst - len(fixes)},
    )
    return fixes


def fix_pairs(con: duckdb.DuckDBPyConnection, day: str, fixes: pd.DataFrame) -> pd.DataFrame:
    """``cta.archive.fix_pairs`` with ``MAX_RAW_BRACKET_GAP_S``; Transit Alerts known gaps do not apply."""
    check_db(con)
    return archive.fix_pairs(con, day, fixes, known_gaps=None, max_gap_s=MAX_RAW_BRACKET_GAP_S)
