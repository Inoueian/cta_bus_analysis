"""Transit Alerts position archive: verified ingest, clean fixes, fix pairs, stop-arrival imputation, QA.

Ingest and manifest verification are ported from ``scripts/transit_archive.py`` of the MIT-licensed
cta-bus-speed-scorecard (https://github.com/MisterClean/cta-bus-speed-scorecard, Copyright (c) 2026
CTA Bus Speed Scorecard contributors). Cleaning follows ``scorecard.sql`` steps 1-2 ([T0] trip key)
and the pair filters steps 5-6 ([T3] gap, [T4] backward, [T5] geometry, [T6] speed). The terminal
trim [T1], stand-still [T2] and pattern-length [T7] filters are deliberately not applied: stop-level
views need every revenue pattern and the first and last stops (ADR-004, specs/archive-adapter.md).

Every stage records a QA row set (stage, rows_in, rows_out, reason, count) in ``archive_qa`` on the
connection; ``qa(con, day)`` returns it. Each dropped row gets exactly one reason, assigned in
``PAIR_REASON_PRIORITY`` order, so reason counts always sum to rows_in - rows_out.

Timestamps are tz-aware UTC at every function boundary; identifiers are strings.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

from cta import bustracker

ARCHIVE_ORIGIN = "https://data.chicagotransitalerts.app/"
INDEX_URL = ARCHIVE_ORIGIN + "positions/index.json"
CHICAGO = ZoneInfo("America/Chicago")

# Cloudflare returns 403 to Python's default urllib User-Agent; curl with a named client is accepted.
CURL_USER_AGENT = "cta-bus-analysis/0.1 (+https://github.com/inoueian/cta_bus_analysis)"

MAX_BRACKET_GAP_S = 180.0  # scorecard [T3] profiling: gaps > 180 s hide stand-stills; 0.34% of pairs
MAX_IMPLIED_MPH = 80.0  # scorecard [T6]: absolute backstop; a 50 mph cap deletes real LSD driving on 146
GEOMETRY_SLACK_FT = 1500.0  # scorecard [T5]: pdist jump must be <= 2 x GPS straight-line + this slack
STOP_PDIST_SOURCE = "getpatterns"  # fix-cloud projection prototype: 100 ft p50 spread, failed on low-volume pids

FT_PER_M = 3.28084
M_PER_DEG_LAT = 111_320.0
FT_PER_MILE = 5280.0

# QA reasons. Pair reasons are assigned in this priority order (first failing rule wins).
REASON_NULL_KEY = "null_run_key_or_pdist"
REASON_DUPLICATE_FIX = "duplicate_fix"
REASON_SPANS_KNOWN_GAP = "spans_known_gap"
REASON_GAP = "gap_over_max"
REASON_BACKWARD = "backward_pdist"
REASON_GEOMETRY = "geometry_unsupported"
REASON_SPEED = "speed_over_max"
REASON_LATER_CROSSING = "later_crossing"
PAIR_REASON_PRIORITY = (REASON_SPANS_KNOWN_GAP, REASON_GAP, REASON_BACKWARD, REASON_GEOMETRY, REASON_SPEED)

BUS_SCHEMA = {
    "ts": "BIGINT",
    "route": "VARCHAR",
    "pid": "VARCHAR",
    "vehicle_id": "VARCHAR",
    "destination": "VARCHAR",
    "lat": "DOUBLE",
    "lon": "DOUBLE",
    "pdist": "DOUBLE",
    "heading": "DOUBLE",
    "vehicle_ts": "BIGINT",
    "sched_start_sec": "INTEGER",
    "sched_start_date": "VARCHAR",
}

CLEAN_FIX_COLUMNS = ["route", "pid", "vehicle_id", "run_id", "service_date", "vehicle_ts", "pdist", "lat", "lon"]
PAIR_COLUMNS = ["route", "pid", "vehicle_id", "run_id", "service_date", "t0", "t1", "p0", "p1", "bracket_gap_s"]
ARRIVAL_COLUMNS = [
    "route", "pid", "vehicle_id", "run_id", "service_date", "stpid", "seq", "stop_rank", "rtdir", "stop_pdist_ft",
    "arrival_time", "bracket_gap_s",
]
QA_COLUMNS = ["stage", "rows_in", "rows_out", "reason", "count"]

RUN_ID_SQL = "vehicle_id || '-' || pid || '-' || sched_start_date || '-' || CAST(sched_start_sec AS VARCHAR)"


# --- index and files ------------------------------------------------------------------------------


def _q(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_curl(url: str, out: Path, *, max_time: int = 300) -> None:
    """Download ``url`` to ``out`` with curl. Tests monkeypatch this; nothing else touches the network."""
    subprocess.run(
        ["curl", "-fLsS", "--retry", "2", "--max-time", str(max_time), "-A", CURL_USER_AGENT, url, "-o", str(out)],
        check=True,
    )


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_index(location: str | Path = INDEX_URL, raw_dir: Path | None = None) -> dict:
    """Fetch the archive index (curl) or load a pinned local copy. Validates the archive timezone."""
    if str(location).startswith("https://"):
        if str(location) != INDEX_URL:
            raise ValueError("Use the canonical index URL or a pinned local index")
        if raw_dir is None:
            raise ValueError("raw_dir is required to download the index")
        raw_dir = Path(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / "index.download.json"
        run_curl(str(location), path, max_time=60)
    else:
        path = Path(location)
    index = json.loads(path.read_text())
    if index.get("timezone") not in (None, "America/Chicago"):
        raise ValueError("Unexpected archive timezone: " + str(index.get("timezone")))
    return index


def pin_index(index: dict, raw_dir: Path) -> Path:
    """Write the index used for a run next to the raw files, so ingests are reproducible."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / "index.pinned.json"
    path.write_text(json.dumps(index, indent=1) + "\n")
    return path


def day_file_meta(index: dict, day: str, kind: str = "bus") -> dict:
    """Manifest entry for one archive day: path, rows, bytes, sha256, plus kind and date."""
    lookup = {d["date"]: d["files"] for d in index["days"]}
    if day not in lookup or kind not in lookup[day]:
        raise ValueError(f"Archive not published for {kind} {day}; no other date substituted")
    m = dict(lookup[day][kind])
    if not re.fullmatch("[0-9a-f]{64}", str(m.get("sha256", ""))):
        raise ValueError("Invalid SHA-256 in index for " + day)
    if not isinstance(m.get("rows"), int) or m["rows"] < 0:
        raise ValueError("Invalid row count in index for " + day)
    if not isinstance(m.get("bytes"), int) or m["bytes"] < 0:
        raise ValueError("Invalid byte size in index for " + day)
    return dict(m, kind=kind, date=day)


def local_day_path(raw_dir: Path, meta: dict) -> Path:
    return Path(raw_dir) / f"{meta['kind']}-{meta['date']}.ndjson.gz"


def verify_day_file(path: Path, meta: dict) -> None:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size != meta["bytes"]:
        raise ValueError(f"byte size mismatch for {path}: {path.stat().st_size} != {meta['bytes']}")
    actual = file_sha256(path)
    if actual != meta["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {path}: {actual} != {meta['sha256']}")


def ensure_day_file(meta: dict, raw_dir: Path) -> Path:
    """Local verified copy of one archive day, downloading it with curl when missing or stale."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = local_day_path(raw_dir, meta)
    if path.exists():
        try:
            verify_day_file(path, meta)
            return path
        except ValueError:
            pass
    temp = path.with_suffix(".part")
    try:
        run_curl(ARCHIVE_ORIGIN + meta["path"], temp)
        verify_day_file(temp, meta)
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    return path


# --- database -------------------------------------------------------------------------------------


def open_archive_db(
    db_path: Path | None = None, *, threads: int | None = None, memory_limit: str | None = None
) -> duckdb.DuckDBPyConnection:
    """DuckDB connection (in-memory when ``db_path`` is None) with the archive tables created."""
    if duckdb.__version__.split(".")[0] != "2":
        raise RuntimeError("DuckDB 2.x required; actual version: " + duckdb.__version__)
    if db_path is not None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path) if db_path is not None else ":memory:")
    con.execute("SET TimeZone='UTC'")
    con.execute("SET threads=" + str(threads or min(8, os.cpu_count() or 1)))
    if memory_limit:
        con.execute("SET memory_limit=" + _q(memory_limit))
    _initialize(con)
    return con


def _initialize(con: duckdb.DuckDBPyConnection) -> None:
    fields = ",".join(f"{k} {t}" for k, t in BUS_SCHEMA.items())
    con.execute(f"CREATE TABLE IF NOT EXISTS positions_raw(archive_date DATE, {fields})")
    con.execute(
        """CREATE TABLE IF NOT EXISTS archive_ingest(
             archive_date DATE PRIMARY KEY, sha256 VARCHAR, source_path VARCHAR, local_path VARCHAR,
             rows BIGINT, bytes BIGINT, ingested_at TIMESTAMPTZ DEFAULT current_timestamp)"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS archive_qa(
             archive_date DATE, stage VARCHAR, rows_in BIGINT, rows_out BIGINT, reason VARCHAR, count BIGINT,
             seq INTEGER, recorded_at TIMESTAMPTZ DEFAULT current_timestamp)"""
    )


def _calendar_bounds_ms(day: str) -> tuple[int, int]:
    d = dt.date.fromisoformat(day)
    a = dt.datetime.combine(d, dt.time(), CHICAGO)
    b = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(), CHICAGO)
    return int(a.timestamp() * 1000), int(b.timestamp() * 1000)


def _record_qa(con, day: str, stage: str, rows_in: int, rows_out: int, reasons: dict[str, int]) -> None:
    con.execute("DELETE FROM archive_qa WHERE archive_date = ? AND stage = ?", [day, stage])
    items = [(r, int(c)) for r, c in reasons.items() if int(c) != 0] or [(None, 0)]
    for i, (reason, count) in enumerate(items):
        con.execute(
            "INSERT INTO archive_qa(archive_date, stage, rows_in, rows_out, reason, count, seq) VALUES (?,?,?,?,?,?,?)",
            [day, stage, int(rows_in), int(rows_out), reason, count, i],
        )
    total = sum(c for _, c in items)
    if total != rows_in - rows_out:
        raise AssertionError(f"QA stage {stage} on {day}: reasons sum to {total}, expected {rows_in - rows_out}")


def qa(con: duckdb.DuckDBPyConnection, day: str) -> pd.DataFrame:
    """QA table for one archive day: one row per (stage, reason); counts sum to rows_in - rows_out."""
    return con.execute(
        "SELECT stage, rows_in, rows_out, reason, count FROM archive_qa WHERE archive_date = ? "
        "ORDER BY recorded_at, stage, seq",
        [day],
    ).df()


def ingest_day(con: duckdb.DuckDBPyConnection, meta: dict, path: Path) -> dict:
    """Load one verified archive day into ``positions_raw``. Refuses a day whose published checksum changed."""
    path = Path(path).resolve()
    verify_day_file(path, meta)
    day = meta["date"]
    prior = con.execute("SELECT sha256, rows FROM archive_ingest WHERE archive_date = ?", [day]).fetchone()
    if prior:
        if prior != (meta["sha256"], meta["rows"]):
            raise ValueError(f"Published source for {day} changed since ingest; rebuild in a new database")
        return {"date": day, "status": "skipped", "rows": meta["rows"]}
    cols = "{" + ",".join(_q(k) + ":" + _q(v) for k, v in BUS_SCHEMA.items()) + "}"
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE stage AS SELECT DATE {_q(day)} archive_date, * FROM read_json("
        f"{_q(path)}, format='newline_delimited', compression='gzip', columns={cols})"
    )
    a, b = _calendar_bounds_ms(day)
    n, missing, invalid, wrong_date = con.execute(
        """SELECT count(*),
             count(*) FILTER (WHERE ts IS NULL OR route IS NULL OR trim(route) = '' OR vehicle_id IS NULL
                              OR trim(vehicle_id) = '' OR lat IS NULL OR lon IS NULL),
             count(*) FILTER (WHERE NOT isfinite(lat) OR NOT isfinite(lon) OR lat NOT BETWEEN -90 AND 90
                              OR lon NOT BETWEEN -180 AND 180),
             count(*) FILTER (WHERE ts < ? OR ts >= ?)
           FROM stage""",
        [a, b],
    ).fetchone()
    if n != meta["rows"] or missing or invalid or wrong_date:
        con.execute("DROP TABLE IF EXISTS stage")
        raise ValueError(
            f"Data validation failed for {day}: rows={n} expected={meta['rows']} missing={missing} "
            f"invalid_coordinates={invalid} wrong_date={wrong_date}"
        )
    con.execute("BEGIN")
    try:
        con.execute("INSERT INTO positions_raw SELECT * FROM stage ORDER BY route, ts, vehicle_id")
        con.execute(
            "INSERT INTO archive_ingest(archive_date, sha256, source_path, local_path, rows, bytes) VALUES (?,?,?,?,?,?)",
            [day, meta["sha256"], meta["path"], str(path), meta["rows"], meta["bytes"]],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.execute("DROP TABLE IF EXISTS stage")
    _record_qa(con, day, "ingest", n, n, {})
    return {"date": day, "status": "ingested", "rows": n}


def ingested_days(con: duckdb.DuckDBPyConnection) -> list[str]:
    return [str(r[0]) for r in con.execute("SELECT archive_date FROM archive_ingest ORDER BY 1").fetchall()]


# --- stages ---------------------------------------------------------------------------------------


def _epoch_ms(ts: pd.Series) -> pd.Series:
    """Epoch milliseconds from a tz-aware series, whatever its unit (pandas 3 is not always ns)."""
    utc = pd.to_datetime(ts, utc=True)
    return ((utc - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(milliseconds=1)).astype("int64")


def _pid_filter(con, pids: list[str] | None) -> str:
    if pids is None:
        return "TRUE"
    unique = list(dict.fromkeys(str(p) for p in pids))
    if not unique:
        return "FALSE"
    con.execute("CREATE OR REPLACE TEMP TABLE _pids AS SELECT * FROM (VALUES " + ",".join(f"({_q(p)})" for p in unique) + ") t(pid)")
    return "pid IN (SELECT pid FROM _pids)"


def clean_fixes(con: duckdb.DuckDBPyConnection, day: str, pids: list[str] | None = None) -> pd.DataFrame:
    """scorecard.sql steps 1-2: drop rows missing the trip key or pdist, keep one fix per (run, vehicle_ts).

    One row per (run_id, vehicle_ts), min(pdist) on duplicates (a frozen GPS repeats the same
    vehicle_ts on later polls). ``service_date`` is ``sched_start_date`` (post-midnight trips keep
    their scheduled date), not the archive file date.
    """
    where = f"archive_date = {_q(day)} AND " + _pid_filter(con, pids)
    rows_in = con.execute(f"SELECT count(*) FROM positions_raw WHERE {where}").fetchone()[0]
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE _nonnull AS
            SELECT route, pid, vehicle_id, {RUN_ID_SQL} run_id, sched_start_date service_date, vehicle_ts, pdist, lat, lon
            FROM positions_raw
            WHERE {where} AND pid IS NOT NULL AND pdist IS NOT NULL AND vehicle_ts IS NOT NULL
              AND sched_start_date IS NOT NULL AND sched_start_sec IS NOT NULL"""
    )
    n_nonnull = con.execute("SELECT count(*) FROM _nonnull").fetchone()[0]
    fixes = con.execute(
        """SELECT any_value(route) route, pid, vehicle_id, run_id, service_date,
                  to_timestamp(vehicle_ts / 1000.0) vehicle_ts, min(pdist) pdist,
                  arg_min(lat, pdist) lat, arg_min(lon, pdist) lon
           FROM _nonnull
           GROUP BY pid, vehicle_id, run_id, service_date, vehicle_ts
           ORDER BY run_id, vehicle_ts"""
    ).df()
    con.execute("DROP TABLE IF EXISTS _nonnull")
    fixes = fixes[CLEAN_FIX_COLUMNS]
    _record_qa(
        con, day, "clean", rows_in, len(fixes),
        {REASON_NULL_KEY: rows_in - n_nonnull, REASON_DUPLICATE_FIX: n_nonnull - len(fixes)},
    )
    return fixes


def fix_pairs(
    con: duckdb.DuckDBPyConnection,
    day: str,
    fixes: pd.DataFrame,
    known_gaps: pd.DataFrame | None = None,
    max_gap_s: float = MAX_BRACKET_GAP_S,
) -> pd.DataFrame:
    """Consecutive-fix pairs within a run, filtered as scorecard [T3]-[T6] plus known-gap spans.

    ``known_gaps`` is the ``cta.calendar.known_gaps`` table (UTC start/end). A pair is dropped for the
    first reason in ``PAIR_REASON_PRIORITY`` that applies, so the QA counts are additive. ``max_gap_s``
    is the [T3] cap; a source with a slower poll passes its own (``cta.mansueto_raw``, ADR-009).
    """
    con.register("_fixes", fixes[CLEAN_FIX_COLUMNS])
    if known_gaps is not None and len(known_gaps):
        gaps = pd.DataFrame(
            {"gap_start_ms": _epoch_ms(known_gaps["start"]), "gap_end_ms": _epoch_ms(known_gaps["end"])}
        )
    else:
        gaps = pd.DataFrame({"gap_start_ms": pd.Series(dtype="int64"), "gap_end_ms": pd.Series(dtype="int64")})
    con.register("_gaps", gaps)
    con.execute(
        f"""CREATE OR REPLACE TEMP TABLE _pairs AS
            WITH f AS (
              SELECT route, pid, vehicle_id, run_id, service_date, epoch_ms(vehicle_ts) ms, pdist, lat, lon FROM _fixes),
            pr AS (
              SELECT route, pid, vehicle_id, run_id, service_date,
                     lag(ms) OVER w t0_ms, ms t1_ms, lag(pdist) OVER w p0, pdist p1,
                     lag(lat) OVER w lat0, lat lat1, lag(lon) OVER w lon0, lon lon1
              FROM f WINDOW w AS (PARTITION BY run_id ORDER BY ms)),
            m AS (
              SELECT *, (t1_ms - t0_ms) / 1000.0 dt, p1 - p0 dd,
                     {FT_PER_M} * {M_PER_DEG_LAT} * sqrt(power(lat1 - lat0, 2) + power(cos(radians(lat1)) * (lon1 - lon0), 2)) crow,
                     EXISTS (SELECT 1 FROM _gaps g WHERE pr.t0_ms < g.gap_end_ms AND pr.t1_ms > g.gap_start_ms) spans_gap
              FROM pr WHERE t0_ms IS NOT NULL)
            SELECT *, CASE
                WHEN spans_gap THEN {_q(REASON_SPANS_KNOWN_GAP)}
                WHEN dt > {float(max_gap_s)} THEN {_q(REASON_GAP)}
                WHEN dd < 0 THEN {_q(REASON_BACKWARD)}
                WHEN dd > 2 * crow + {GEOMETRY_SLACK_FT} THEN {_q(REASON_GEOMETRY)}
                WHEN dt > 0 AND (dd / dt) * 3600 / {FT_PER_MILE} > {MAX_IMPLIED_MPH} THEN {_q(REASON_SPEED)}
                END reason
            FROM m"""
    )
    rows_in = con.execute("SELECT count(*) FROM _pairs").fetchone()[0]
    reasons = dict(con.execute("SELECT reason, count(*) FROM _pairs WHERE reason IS NOT NULL GROUP BY 1").fetchall())
    pairs = con.execute(
        """SELECT route, pid, vehicle_id, run_id, service_date,
                  to_timestamp(t0_ms / 1000.0) t0, to_timestamp(t1_ms / 1000.0) t1, p0, p1, dt bracket_gap_s
           FROM _pairs WHERE reason IS NULL ORDER BY run_id, t0_ms"""
    ).df()[PAIR_COLUMNS]
    con.execute("DROP TABLE IF EXISTS _pairs")
    con.unregister("_fixes")
    con.unregister("_gaps")
    _record_qa(con, day, "pairs", rows_in, len(pairs), {r: reasons.get(r, 0) for r in PAIR_REASON_PRIORITY})
    return pairs


def impute_arrivals(
    con: duckdb.DuckDBPyConnection, day: str, pairs: pd.DataFrame, pattern_stops: pd.DataFrame
) -> pd.DataFrame:
    """Linear interpolation of the time each run crossed each pattern stop; earliest crossing per (run, stop).

    ``pattern_stops`` is ``cta.bustracker.pattern_stops_table`` output (pid, rtdir, seq, stpid, pdist_ft,
    stop_rank; the dense rank is computed here when a hand-built table lacks it).
    A stop with p0 <= pdist < p1 is crossed in the pair (p0, t0) -> (p1, t1). Stops a run never
    crosses are absent, not NaT.
    """
    stops = bustracker.with_stop_rank(pattern_stops)
    con.register("_pairs_in", pairs[PAIR_COLUMNS])
    con.register("_stops", stops[["pid", "rtdir", "seq", "stop_rank", "stpid", "pdist_ft"]])
    con.execute(
        """CREATE OR REPLACE TEMP TABLE _cross AS
           SELECT p.route, p.pid, p.vehicle_id, p.run_id, p.service_date, s.stpid, s.seq, s.stop_rank, s.rtdir,
                  s.pdist_ft stop_pdist_ft,
                  epoch_ms(p.t0) + (epoch_ms(p.t1) - epoch_ms(p.t0)) * (s.pdist_ft - p.p0) / (p.p1 - p.p0) arr_ms,
                  p.bracket_gap_s
           FROM _pairs_in p JOIN _stops s ON s.pid = p.pid
           WHERE p.p1 > p.p0 AND p.p0 <= s.pdist_ft AND s.pdist_ft < p.p1"""
    )
    rows_in = con.execute("SELECT count(*) FROM _cross").fetchone()[0]
    arrivals = con.execute(
        """SELECT any_value(route) route, pid, any_value(vehicle_id) vehicle_id, run_id, any_value(service_date) service_date,
                  stpid, any_value(seq) seq, any_value(stop_rank) stop_rank, any_value(rtdir) rtdir,
                  any_value(stop_pdist_ft) stop_pdist_ft,
                  to_timestamp(min(arr_ms) / 1000.0) arrival_time, arg_min(bracket_gap_s, arr_ms) bracket_gap_s
           FROM _cross GROUP BY pid, run_id, stpid ORDER BY run_id, seq"""
    ).df()[ARRIVAL_COLUMNS]
    con.execute("DROP TABLE IF EXISTS _cross")
    con.unregister("_pairs_in")
    con.unregister("_stops")
    _record_qa(con, day, "impute", rows_in, len(arrivals), {REASON_LATER_CROSSING: rows_in - len(arrivals)})
    return arrivals
