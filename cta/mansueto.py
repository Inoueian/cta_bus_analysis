"""Mansueto StopWatch adapter: CloudFront URL helpers, per-pattern parquet reader, cleaning stages with QA,
data-edge probe and verified download (specs/mansueto-adapter.md, ADR-001, ADR-004, ADR-007).

The per-pattern files ``trips_<pid>_full.parquet`` hold imputed stop arrivals from ~5 min pings
(one row per trip x stop) with ``bus_stop_time`` as tz-naive America/Chicago wall time
(``docs/2026-11-04-mansueto-data-edge.md``). ``read_trips`` normalizes names and types, drops nothing;
``clean_trips`` runs the four stages (read, dedup, pattern_join, order), each recording one reason per
dropped row so that reason counts sum to rows_in - rows_out; ``cta.views.run_level_from_mansueto``
assembles the ADR-003 run-level view from the result.

The bucket publishes no manifest or checksum, so ``data_edge`` measures each file's row count and
time range from the parquet footer (HTTP range requests) and ``fetch_parquet`` records that next to
the download in ``trips_<pid>_full.meta.json``. The bucket has been frozen at ``MANSUETO_DATA_EDGE``
since at least 2026-11-04 (ADR-007).

This module has no Bus Tracker dependency (specs/split-cta-api.md); the stop table it joins to is
``cta.bustracker.pattern_stops_table`` output passed in by the caller.
Identifiers are strings; timestamps are tz-aware UTC at every function boundary.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import json
import re
import shutil
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE = "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch"
RT_TO_PID_URL = f"{BASE}/rt_to_pid.csv"

CLOUDFRONT_MIN_INTERVAL_SEC = 0.1

# Named client for the bucket's access logs (CloudFront, unlike the archive's Cloudflare, accepts urllib's
# default User-Agent too). Same string as cta.archive.CURL_USER_AGENT.
USER_AGENT = "cta-bus-analysis/0.1 (+https://github.com/inoueian/cta_bus_analysis)"

MANSUETO_DATA_EDGE = "2026-07-28"  # footer probe 2026-11-04 on PIDs 18414, 18415, 6414 (ADR-007, docs/2026-11-04-mansueto-data-edge.md)
MANSUETO_TZ = "America/Chicago"  # bus_stop_time is naive wall time: clock-hour profile of PID 18414's last row group (data-edge doc)
SOURCE_MANSUETO = "mansueto"  # ADR-004 source column
MAX_SELF_CONSISTENCY_DEVIATION = 0.02  # adapter vs legacy pipeline read the same rows; observed 0.000 on PID 6410 (docs/2026-11-04-mansueto-adapter-qa.md)
MIN_RUNS_FOR_RATIO = 30  # ADR-006: fewer runs make medians noisy
MAX_MEDIAN_RATIO_DEVIATION = 0.20  # ADR-006, for the deferred same-day archive check only

PARQUET_COLUMNS = ["unique_trip_vehicle_day", "rt", "pid", "vid", "stpid", "stop_sequence", "bus_stop_time"]
TRIP_COLUMNS = ["run_id", "route", "pid", "vehicle_id", "stpid", "stop_sequence", "bus_stop_time"]
CLEAN_COLUMNS = TRIP_COLUMNS + ["seq", "stop_rank", "rtdir", "service_date"]
QA_COLUMNS = ["stage", "rows_in", "rows_out", "reason", "count"]  # same as cta.archive.QA_COLUMNS
STAGES = ("read", "dedup", "pattern_join", "order")

REASON_NULL_KEY_OR_TIME = "null_key_or_time"
REASON_DST_AMBIGUOUS = "dst_ambiguous_time"
REASON_DUPLICATE_STOP_VISIT = "duplicate_stop_visit"
REASON_STOP_NOT_IN_PATTERN = "stop_not_in_pattern"
REASON_NONMONOTONE_TIME = "nonmonotone_time"

# read_trips records how many source rows had a null bus_stop_time here, so clean_trips can tell them
# from the NaT that DST localization produces (both are NaT once the column is tz-aware).
ATTR_NULL_TIME_ROWS = "null_bus_stop_time"

_TRAILING_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})$")
_PARQUET_MAGIC = b"PAR1"

_last_cloudfront_call_monotonic: float = 0.0


def _throttle_cloudfront() -> None:
    global _last_cloudfront_call_monotonic
    now = time.monotonic()
    elapsed = now - _last_cloudfront_call_monotonic
    if _last_cloudfront_call_monotonic > 0 and elapsed < CLOUDFRONT_MIN_INTERVAL_SEC:
        time.sleep(CLOUDFRONT_MIN_INTERVAL_SEC - elapsed)
    _last_cloudfront_call_monotonic = time.monotonic()


# --- URLs and HTTP primitives (tests replace the three network functions) --------------------------


def parquet_url(pid: str) -> str:
    return f"{BASE}/processed_by_pid/trips_{pid}_full.parquet"


def _request(url: str, method: str = "GET", headers: dict | None = None):
    _throttle_cloudfront()
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=120)  # honours HTTPS_PROXY / SSL_CERT_FILE of the environment


def parquet_http_status(pid: str) -> int:
    try:
        with _request(parquet_url(pid), "HEAD") as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _http_date_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    return email.utils.parsedate_to_datetime(value).astimezone(dt.timezone.utc).isoformat()


def http_head(url: str) -> dict:
    """``{"bytes": Content-Length, "last_modified": ISO-8601 UTC or None}`` for ``url``."""
    with _request(url, "HEAD") as resp:
        return {"bytes": int(resp.headers["Content-Length"]), "last_modified": _http_date_to_iso(resp.headers.get("Last-Modified"))}


def http_range(url: str, start: int, end: int) -> bytes:
    """Bytes ``start``..``end`` (inclusive) of ``url`` via one HTTP range request."""
    with _request(url, headers={"Range": f"bytes={start}-{end}"}) as resp:
        if resp.status != 206:
            raise ValueError(f"range request not honoured for {url}: HTTP {resp.status}")
        data = resp.read()
    if len(data) != end - start + 1:
        raise ValueError(f"short range response for {url}: {len(data)} bytes, expected {end - start + 1}")
    return data


def download(url: str, out: Path) -> None:
    """Stream ``url`` to ``out``."""
    with _request(url) as resp, Path(out).open("wb") as f:
        shutil.copyfileobj(resp, f, 1 << 20)


# --- catalog ---------------------------------------------------------------------------------------


def _id_str(value) -> str:
    """Identifier as a string; integral floats (legacy casts pid through float) lose the '.0'."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    if re.fullmatch(r"-?\d+\.0+", s):
        return s.split(".")[0]
    return s


def pids_for_route(route: str, rt_to_pid: pd.DataFrame | str | Path) -> list[str]:
    """PIDs of ``route`` in ``rt_to_pid`` (DataFrame, path or URL of ``rt_to_pid.csv``), catalog order, as strings.

    Exact string match: route "3" does not match "30". Empty when the route is absent (route 10 is).
    """
    cat = rt_to_pid if isinstance(rt_to_pid, pd.DataFrame) else pd.read_csv(rt_to_pid, dtype=str)
    rt = cat["rt"].map(_id_str)
    return [_id_str(p) for p in cat.loc[rt == _id_str(route), "pid"]]


# --- data edge and download ------------------------------------------------------------------------


def parquet_footer(url: str, size: int) -> bytes:
    """Footer metadata plus the 8-byte trailer of a remote parquet, by two range requests (no full download)."""
    if size < 12:
        raise ValueError(f"{url}: {size} bytes is not a parquet file")
    trailer = http_range(url, size - 8, size - 1)
    if trailer[-4:] != _PARQUET_MAGIC:
        raise ValueError(f"{url}: missing parquet magic in trailer")
    footer_len = struct.unpack("<I", trailer[:4])[0]
    if footer_len + 8 > size:
        raise ValueError(f"{url}: footer length {footer_len} exceeds file size {size}")
    return http_range(url, size - footer_len - 8, size - 1)


def footer_summary(footer: bytes) -> dict:
    """Rows and ``bus_stop_time`` min/max (naive wall-time ISO strings) from parquet footer statistics."""
    md = pq.read_metadata(pa.BufferReader(footer))
    mins, maxs = [], []
    for i in range(md.num_row_groups):
        rg = md.row_group(i)
        for j in range(rg.num_columns):
            col = rg.column(j)
            if col.path_in_schema == "bus_stop_time" and col.statistics is not None and col.statistics.has_min_max:
                mins.append(pd.Timestamp(col.statistics.min))
                maxs.append(pd.Timestamp(col.statistics.max))
    if not mins:
        raise ValueError("no bus_stop_time statistics in parquet footer")
    return {
        "rows": int(md.num_rows),
        "row_groups": int(md.num_row_groups),
        "min_bus_stop_time": min(mins).isoformat(),
        "max_bus_stop_time": max(maxs).isoformat(),
    }


def data_edge(pid: str) -> dict:
    """Size, Last-Modified, rows and ``bus_stop_time`` range of ``trips_<pid>_full.parquet`` from its footer only."""
    url = parquet_url(str(pid))
    head = http_head(url)
    summary = footer_summary(parquet_footer(url, head["bytes"]))
    return {
        "url": url,
        "bytes": int(head["bytes"]),
        "last_modified": head["last_modified"],
        "rows": summary["rows"],
        "min_bus_stop_time": summary["min_bus_stop_time"],
        "max_bus_stop_time": summary["max_bus_stop_time"],
    }


def local_parquet_path(pid: str, dest_dir: Path) -> Path:
    return Path(dest_dir) / f"trips_{pid}_full.parquet"


def meta_path(parquet_path: Path) -> Path:
    parquet_path = Path(parquet_path)
    return parquet_path.with_name(parquet_path.stem + ".meta.json")


def write_meta(pid: str, parquet_path: Path, edge: dict) -> Path:
    """Download metadata file (the ``data_edge`` dict plus ``fetched_at``) next to ``parquet_path``."""
    meta = {"pid": str(pid), **edge, "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "local_bytes": Path(parquet_path).stat().st_size}
    path = meta_path(parquet_path)
    path.write_text(json.dumps(meta, indent=1) + "\n")
    return path


def fetch_parquet(pid: str, dest_dir: Path) -> Path:
    """Download ``trips_<pid>_full.parquet`` into ``dest_dir`` and write ``trips_<pid>_full.meta.json`` beside it.

    Refuses an empty download. No checksum is verified because the bucket publishes none; the metadata
    file (footer row count and time range, fetch time) is what the calendar freshness check reads.
    """
    pid = str(pid)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = local_parquet_path(pid, dest_dir)
    temp = path.with_suffix(".part")
    try:
        download(parquet_url(pid), temp)
        if temp.stat().st_size == 0:
            raise ValueError(f"empty download for pid {pid}")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    write_meta(pid, path, data_edge(pid))
    return path


# --- read -----------------------------------------------------------------------------------------


def _str_sql(col: str) -> str:
    """VARCHAR form of an identifier column: numeric values (string or float) without a trailing '.0'."""
    return f"COALESCE(CAST(TRY_CAST(TRY_CAST({col} AS DOUBLE) AS BIGINT) AS VARCHAR), CAST({col} AS VARCHAR))"


def to_utc(ts: pd.Series) -> pd.Series:
    """tz-aware UTC from naive America/Chicago wall time (ambiguous/nonexistent -> NaT) or any tz-aware series."""
    ts = pd.to_datetime(ts)
    if ts.dt.tz is None:
        return ts.dt.tz_localize(MANSUETO_TZ, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    return ts.dt.tz_convert("UTC")


def _bound_utc(value) -> pd.Timestamp | None:
    if value is None:
        return None
    t = pd.Timestamp(value)
    return t.tz_localize(MANSUETO_TZ) if t.tzinfo is None else t.tz_convert("UTC")


def read_trips(
    path: Path, *, pid: str, start=None, end=None, con: duckdb.DuckDBPyConnection | None = None
) -> pd.DataFrame:
    """Rows of ``pid`` in a StopWatch parquet with normalized names and types; nothing is cleaned.

    Projects the seven needed columns through DuckDB (files run to 15M rows), casts identifiers to
    strings (``pid`` through int when numeric) and converts ``bus_stop_time`` to UTC, leaving NaT where
    a naive time is DST-ambiguous. ``start``/``end`` (naive = America/Chicago wall time, ``end``
    exclusive) are applied after the read; the whole file is scanned either way because row groups
    are not time-ordered.
    """
    pid = str(pid)
    own = con is None
    con = con or duckdb.connect()
    try:
        df = con.execute(
            f"""SELECT CAST(unique_trip_vehicle_day AS VARCHAR) run_id, {_str_sql('rt')} route, {_str_sql('pid')} pid,
                       {_str_sql('vid')} vehicle_id, {_str_sql('stpid')} stpid, CAST(stop_sequence AS BIGINT) stop_sequence,
                       bus_stop_time
                FROM read_parquet(?) WHERE {_str_sql('pid')} = ?""",
            [str(path), pid],
        ).df()
    finally:
        if own:
            con.close()
    null_time = int(df["bus_stop_time"].isna().sum())
    df["bus_stop_time"] = to_utc(df["bus_stop_time"])
    if df["stop_sequence"].isna().any():
        df["stop_sequence"] = df["stop_sequence"].astype("Int64")
    else:
        df["stop_sequence"] = df["stop_sequence"].astype("int64")
    lo, hi = _bound_utc(start), _bound_utc(end)
    if lo is not None or hi is not None:
        keep = df["bus_stop_time"].isna()  # NaT rows stay so clean_trips can count them
        if lo is not None:
            keep |= df["bus_stop_time"] >= lo
        if hi is not None:
            keep &= df["bus_stop_time"].isna() | (df["bus_stop_time"] < hi)
        df = df[keep]
    df = df[TRIP_COLUMNS].reset_index(drop=True)
    df.attrs[ATTR_NULL_TIME_ROWS] = null_time
    return df


def parquet_files_for_pid(parquet_dir: Path, pid: str) -> list[Path]:
    """``trips_<pid>_full.parquet`` under ``parquet_dir`` when present, else every parquet there (fixtures hold several pids)."""
    parquet_dir = Path(parquet_dir)
    canonical = local_parquet_path(str(pid), parquet_dir)
    if canonical.is_file():
        return [canonical]
    files = sorted(p for p in parquet_dir.glob("*.parquet") if p.is_file())
    if not files:
        raise FileNotFoundError(f"no parquet files under {parquet_dir}")
    return files


# --- clean ----------------------------------------------------------------------------------------


def qa_rows(stage: str, rows_in: int, rows_out: int, reasons: dict[str, int]) -> list[dict]:
    """QA rows for one stage, one per non-zero reason (one ``None`` row when nothing was dropped). Asserts additivity."""
    items = [(r, int(c)) for r, c in reasons.items() if int(c) != 0] or [(None, 0)]
    total = sum(c for _, c in items)
    if total != rows_in - rows_out:
        raise AssertionError(f"QA stage {stage}: reasons sum to {total}, expected {rows_in - rows_out}")
    return [{"stage": stage, "rows_in": int(rows_in), "rows_out": int(rows_out), "reason": r, "count": c} for r, c in items]


def _with_stop_rank(stops: pd.DataFrame) -> pd.DataFrame:
    """Dense 0-based rank by ``seq`` within pid when a hand-built table lacks it (same rule as cta.bustracker.with_stop_rank)."""
    if "stop_rank" in stops.columns:
        return stops
    out = stops.copy()
    out["stop_rank"] = (out.groupby("pid")["seq"].rank(method="first") - 1).astype("int64")
    return out


def _epoch_ns(ts: pd.Series) -> pd.Series:
    return (ts - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(1, "ns")


def _empty_clean() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="object") for c in CLEAN_COLUMNS})
    for c in ("stop_sequence", "seq", "stop_rank"):
        df[c] = df[c].astype("int64")
    df["bus_stop_time"] = pd.to_datetime(df["bus_stop_time"], utc=True)
    return df


def clean_trips(trips: pd.DataFrame, pattern_stops: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The four cleaning stages on ``read_trips`` output (or a hand-built frame with ``TRIP_COLUMNS``).

    read          null run_id / stpid / bus_stop_time (``null_key_or_time``); DST-ambiguous or nonexistent
                  naive times (``dst_ambiguous_time``). A tz-aware input converts with zero DST drops.
    dedup         one row per (run_id, stpid), earliest bus_stop_time kept (``duplicate_stop_visit``).
    pattern_join  inner join to ``pattern_stops`` on (pid, stpid) for rtdir, seq and stop_rank; stops not
                  in the current pattern are dropped (``stop_not_in_pattern``).
    order         within a run sorted by seq, a time earlier than the running maximum of the preceding
                  rows is dropped (``nonmonotone_time``; owner decision 2026-11-04, drop not flag).
    service_date  trailing YYYY-MM-DD of run_id; else the America/Chicago date of the run's earliest time.
    Returns (clean rows with ``CLEAN_COLUMNS``, QA table with ``QA_COLUMNS``).
    """
    missing = [c for c in TRIP_COLUMNS if c not in trips.columns]
    if missing:
        raise ValueError(f"trips is missing columns {missing}")
    qa: list[dict] = []
    df = trips[TRIP_COLUMNS].copy()

    # read
    n_in = len(df)
    naive = pd.to_datetime(df["bus_stop_time"]).dt.tz is None
    pre_null_time = df["bus_stop_time"].isna()
    utc = to_utc(df["bus_stop_time"])
    key_null = df["run_id"].isna() | df["stpid"].isna()
    if naive:
        null_rows = key_null | pre_null_time
    else:
        src_null = int(trips.attrs.get(ATTR_NULL_TIME_ROWS, 0))
        nat_with_keys = utc.isna() & ~key_null
        first_n = nat_with_keys & (nat_with_keys.cumsum() <= src_null)
        null_rows = key_null | first_n
    dst_rows = utc.isna() & ~null_rows
    df["bus_stop_time"] = utc
    df = df[~(null_rows | dst_rows)]
    qa += qa_rows("read", n_in, len(df), {REASON_NULL_KEY_OR_TIME: null_rows.sum(), REASON_DST_AMBIGUOUS: dst_rows.sum()})

    # dedup
    n_in = len(df)
    df = df.sort_values(["run_id", "stpid", "bus_stop_time"], kind="stable").drop_duplicates(["run_id", "stpid"], keep="first")
    qa += qa_rows("dedup", n_in, len(df), {REASON_DUPLICATE_STOP_VISIT: n_in - len(df)})

    # pattern_join
    n_in = len(df)
    stops = _with_stop_rank(pattern_stops)[["pid", "stpid", "seq", "rtdir", "stop_rank"]].copy()
    stops["pid"] = stops["pid"].map(_id_str)
    stops["stpid"] = stops["stpid"].map(_id_str)
    stops = stops.sort_values(["pid", "seq"], kind="stable").drop_duplicates(["pid", "stpid"], keep="first")
    df = df.merge(stops, on=["pid", "stpid"], how="inner")
    qa += qa_rows("pattern_join", n_in, len(df), {REASON_STOP_NOT_IN_PATTERN: n_in - len(df)})

    # order
    n_in = len(df)
    df = df.sort_values(["run_id", "seq"], kind="stable").reset_index(drop=True)
    if len(df):
        ns = _epoch_ns(df["bus_stop_time"])
        prev_max = ns.groupby(df["run_id"]).cummax().groupby(df["run_id"]).shift()
        bad = (ns < prev_max).fillna(False).astype(bool)
        df = df[~bad]
    else:
        bad = pd.Series(dtype=bool)
    qa += qa_rows("order", n_in, len(df), {REASON_NONMONOTONE_TIME: int(bad.sum())})

    qa_df = pd.DataFrame(qa, columns=QA_COLUMNS)
    if df.empty:
        return _empty_clean(), qa_df

    embedded = df["run_id"].astype(str).str.extract(_TRAILING_DATE)[0]
    valid = pd.to_datetime(embedded, format="%Y-%m-%d", errors="coerce").notna()
    earliest = df.groupby("run_id")["bus_stop_time"].transform("min").dt.tz_convert(MANSUETO_TZ).dt.strftime("%Y-%m-%d")
    df["service_date"] = embedded.where(valid, earliest).astype(str)
    df["seq"] = df["seq"].astype("int64")
    df["stop_rank"] = df["stop_rank"].astype("int64")
    df["rtdir"] = df["rtdir"].astype(str)
    return df[CLEAN_COLUMNS].reset_index(drop=True), qa_df
