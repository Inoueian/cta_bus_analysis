#!/usr/bin/env python3
"""Build the committed test fixtures for specs/mansueto-adapter.md from the public CloudFront files.

Writes under tests/fixtures/:
  mansueto_6410_last30d.parquet        every row of trips_6410_full.parquet with bus_stop_time >= max - 30 days
                                       (the cutoff of scripts/cache_dlsd_parquets.py), all 11 columns verbatim
  mansueto_2026-07-27_route3.parquet   rows of PIDs 18414 and 18415 whose bus_stop_time falls on 2026-07-27
                                       (America/Chicago wall time), 11 columns verbatim
  mansueto_rt_to_pid_route3.csv        the route 3 rows of rt_to_pid.csv
  mansueto_18414_footer.bin            the parquet footer plus 8-byte trailer cut from trips_18414_full.parquet
  mansueto.manifest.json               source URLs, data_edge dict and fetch time per pid, bytes / SHA-256 /
                                       rows per fixture file

The full per-pattern files (7 MB for 6410, ~400 MB each for 18414/18415) are fetched with
cta.mansueto.fetch_parquet into --parquet-dir (default data/mansueto, gitignored) unless already
there; each gets its trips_<pid>_full.meta.json. The builder refuses to write if any file was not
generated on cta.mansueto.MANSUETO_DATA_EDGE (Last-Modified) or its max(bus_stop_time) is more than
a day before it, because the self-consistency test assumes that window, and it asserts that the service date embedded in unique_trip_vehicle_day equals
the Chicago date of the run's earliest arrival for at least 99% of runs (printing the rest).

Example:
  python scripts/build_mansueto_fixtures.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cta import mansueto  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
DEFAULT_PARQUET_DIR = REPO_ROOT / "data" / "mansueto"

LAST30D_PID = "6410"
LAST30D_DAYS = 30
ONE_DAY_PIDS = ("18414", "18415")
ONE_DAY_DATE = "2026-07-27"  # the last full day before the data edge
FOOTER_PID = "18414"
ROUTE = "3"
MIN_EMBEDDED_DATE_SHARE = 0.99  # spec Method 6: post-midnight trips are the expected exceptions
# The data edge is a bucket-level date (every file regenerated 2026-07-28 ~10:15 UTC); a pattern's own last
# row can be earlier: PID 6410 (151 NB) ends 2026-07-27 18:19 while 18414/18415 run past midnight.
MAX_EDGE_LAG_DAYS = 1
# A run embedding the previous date whose first row in a day cut is before this Chicago hour is a post-midnight
# continuation (5 of 230 runs on 2026-07-27 for route 3; CTA service days roll over around 03:00-04:00).
POST_MIDNIGHT_HOUR = 4

LAST30D_FILE = f"mansueto_{LAST30D_PID}_last{LAST30D_DAYS}d.parquet"
ONE_DAY_FILE = f"mansueto_{ONE_DAY_DATE}_route{ROUTE}.parquet"
RT_FILE = f"mansueto_rt_to_pid_route{ROUTE}.csv"
FOOTER_FILE = f"mansueto_{FOOTER_PID}_footer.bin"
MANIFEST_FILE = "mansueto.manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_source(pid: str, parquet_dir: Path, force: bool) -> tuple[Path, dict]:
    """Local full parquet plus its metadata file, fetching either when missing."""
    path = mansueto.local_parquet_path(pid, parquet_dir)
    meta = mansueto.meta_path(path)
    if force or not path.is_file():
        print(f"fetching {mansueto.parquet_url(pid)} ...")
        mansueto.fetch_parquet(pid, parquet_dir)
    elif not meta.is_file():
        print(f"probing footer of {mansueto.parquet_url(pid)} for {meta.name} ...")
        mansueto.write_meta(pid, path, mansueto.data_edge(pid))
    info = json.loads(meta.read_text())
    if info["bytes"] != path.stat().st_size:
        raise SystemExit(f"{path} is {path.stat().st_size} bytes but the bucket reports {info['bytes']}; refetch with --force-fetch")
    edge = dt.date.fromisoformat(mansueto.MANSUETO_DATA_EDGE)
    last_row = dt.date.fromisoformat(info["max_bus_stop_time"][:10])
    if not (edge - dt.timedelta(days=MAX_EDGE_LAG_DAYS) <= last_row <= edge):
        raise SystemExit(
            f"pid {pid}: max(bus_stop_time) {info['max_bus_stop_time']} is not within {MAX_EDGE_LAG_DAYS} day of "
            f"MANSUETO_DATA_EDGE {mansueto.MANSUETO_DATA_EDGE}; re-measure the edge (ADR-007) before rebuilding fixtures"
        )
    if (info.get("last_modified") or "")[:10] != mansueto.MANSUETO_DATA_EDGE:
        raise SystemExit(
            f"pid {pid}: Last-Modified {info.get('last_modified')} is not the generation run of MANSUETO_DATA_EDGE "
            f"{mansueto.MANSUETO_DATA_EDGE}; the bucket moved, re-measure the edge (ADR-007)"
        )
    return path, info


def source_null_counts(con: duckdb.DuckDBPyConnection, path: Path) -> dict:
    n, null_time, null_key = con.execute(
        "SELECT count(*), count(*) FILTER (WHERE bus_stop_time IS NULL), "
        "count(*) FILTER (WHERE unique_trip_vehicle_day IS NULL OR stpid IS NULL) FROM read_parquet(?)",
        [str(path)],
    ).fetchone()
    return {"rows": int(n), "null_bus_stop_time": int(null_time), "null_run_id_or_stpid": int(null_key)}


def _ts_scalar(ts: pd.Timestamp, typ: pa.DataType) -> pa.Scalar:
    """Exact timestamp scalar of the column's type (no nanosecond truncation through datetime)."""
    return pa.scalar(int(ts.value), type=pa.timestamp("ns")).cast(typ)


def _write_sorted(table: pa.Table, out: Path) -> None:
    table = table.sort_by([("unique_trip_vehicle_day", "ascending"), ("stop_sequence", "ascending"), ("bus_stop_time", "ascending")])
    pq.write_table(table, out, compression="zstd")


def cut_last30d(path: Path, out: Path) -> dict:
    src = pq.read_table(path)  # 7 MB file; keeps the schema verbatim
    col = src["bus_stop_time"]
    max_ts = pd.Timestamp(pa.compute.max(col).as_py())
    cutoff = max_ts - pd.Timedelta(days=LAST30D_DAYS)
    mask = pa.compute.greater_equal(col, _ts_scalar(cutoff, col.type))
    _write_sorted(src.filter(mask), out)
    return {"cutoff": cutoff.isoformat(), "max_bus_stop_time": max_ts.isoformat(), "days": LAST30D_DAYS}


def cut_one_day(paths: list[Path], out: Path) -> dict:
    lo = pd.Timestamp(ONE_DAY_DATE)
    hi = lo + pd.Timedelta(days=1)  # no DST transition on this day, so wall-time bounds are the Chicago date
    parts = []
    for path in paths:
        f = pq.ParquetFile(path)
        for i in range(f.num_row_groups):  # one row group at a time: the files are ~400 MB, 15M rows
            rg = f.read_row_group(i)
            col = rg["bus_stop_time"]
            mask = pa.compute.and_(
                pa.compute.greater_equal(col, _ts_scalar(lo, col.type)), pa.compute.less(col, _ts_scalar(hi, col.type))
            )
            part = rg.filter(mask)
            if part.num_rows:
                parts.append(part)
    _write_sorted(pa.concat_tables(parts), out)
    return {"date": ONE_DAY_DATE, "timezone": mansueto.MANSUETO_TZ}


def cut_footer(path: Path, out: Path) -> dict:
    size = path.stat().st_size
    with path.open("rb") as f:
        f.seek(size - 8)
        trailer = f.read(8)
        footer_len = int.from_bytes(trailer[:4], "little")
        f.seek(size - footer_len - 8)
        out.write_bytes(f.read(footer_len + 8))
    summary = mansueto.footer_summary(out.read_bytes())
    return {"offset": size - footer_len - 8, "footer_len": footer_len, **summary}


def check_embedded_service_date(out: Path, label: str) -> dict:
    """Spec Method 6: the date embedded in unique_trip_vehicle_day is the Chicago date of the run's earliest
    row for >= 99% of runs. A run embedding the previous date whose earliest row in the cut is before
    POST_MIDNIGHT_HOUR is a post-midnight continuation (the expected exception, printed, not counted)."""
    df = pd.read_parquet(out, columns=["unique_trip_vehicle_day", "bus_stop_time"])
    first = df.groupby("unique_trip_vehicle_day")["bus_stop_time"].min()
    embedded = pd.to_datetime(first.index.to_series().str.extract(r"(\d{4}-\d{2}-\d{2})$")[0], errors="coerce")
    local_day = first.dt.normalize()
    same = embedded.values == local_day.values
    post_midnight = (embedded.values == (local_day - pd.Timedelta(days=1)).values) & (first.dt.hour < POST_MIDNIGHT_HOUR).values
    unexplained = ~same & ~post_midnight
    share = float((same | post_midnight).mean()) if len(same) else 1.0
    report = pd.DataFrame({"embedded": embedded.dt.strftime("%Y-%m-%d").values, "earliest_in_cut": first.values}, index=first.index)
    print(
        f"{label}: embedded service date == Chicago date of earliest row for {int(same.sum())} of {len(same)} runs; "
        f"{int(post_midnight.sum())} post-midnight continuations of the previous date; {int(unexplained.sum())} unexplained"
    )
    if (~same).any():
        print(report[~same].to_string())
    if share < MIN_EMBEDDED_DATE_SHARE:
        raise SystemExit(f"{label}: only {share:.2%} of runs embed the earliest-arrival date (< {MIN_EMBEDDED_DATE_SHARE:.0%})")
    return {
        "runs": int(len(same)),
        "embedded_date_matches_earliest_row": int(same.sum()),
        "post_midnight_continuations": int(post_midnight.sum()),
        "unexplained": int(unexplained.sum()),
    }


def file_entry(out: Path, pids: list[str], **extra) -> dict:
    return {"pids": pids, "rows": int(pq.read_metadata(out).num_rows), "bytes": out.stat().st_size, "sha256": sha256(out), **extra}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parquet-dir", type=Path, default=DEFAULT_PARQUET_DIR, help="where the full per-pattern files live")
    ap.add_argument("--force-fetch", action="store_true", help="re-download the full files even if present")
    args = ap.parse_args()
    parquet_dir = args.parquet_dir
    parquet_dir.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    sources = {}
    paths = {}
    for pid in (LAST30D_PID, *ONE_DAY_PIDS):
        path, info = ensure_source(pid, parquet_dir, args.force_fetch)
        paths[pid] = path
        counts = source_null_counts(con, path)
        if counts["rows"] != info["rows"]:
            raise SystemExit(f"pid {pid}: footer says {info['rows']} rows, scan says {counts['rows']}")
        sources[pid] = {
            "url": info["url"],
            "bytes": info["bytes"],
            "last_modified": info["last_modified"],
            "fetched_at": info["fetched_at"],
            "data_edge": {k: info[k] for k in ("url", "bytes", "last_modified", "rows", "min_bus_stop_time", "max_bus_stop_time")},
            "null_bus_stop_time": counts["null_bus_stop_time"],
            "null_run_id_or_stpid": counts["null_run_id_or_stpid"],
        }
        print(f"pid {pid}: {info['rows']:,} rows, {info['bytes']:,} bytes, edge {info['max_bus_stop_time']}, nulls {counts}")

    files = {}
    out = FIXTURES / LAST30D_FILE
    window = cut_last30d(paths[LAST30D_PID], out)
    files[LAST30D_FILE] = file_entry(out, [LAST30D_PID], window=window, service_date_check=check_embedded_service_date(out, LAST30D_FILE))
    out = FIXTURES / ONE_DAY_FILE
    window = cut_one_day([paths[p] for p in ONE_DAY_PIDS], out)
    files[ONE_DAY_FILE] = file_entry(out, list(ONE_DAY_PIDS), window=window, service_date_check=check_embedded_service_date(out, ONE_DAY_FILE))

    rt_local = parquet_dir / "rt_to_pid.csv"
    if args.force_fetch or not rt_local.is_file():
        mansueto.download(mansueto.RT_TO_PID_URL, rt_local)
    cat = pd.read_csv(rt_local, dtype=str)
    rows = cat[cat["rt"].str.strip() == ROUTE]
    out = FIXTURES / RT_FILE
    rows.to_csv(out, index=False)
    files[RT_FILE] = {"pids": rows["pid"].tolist(), "rows": int(len(rows)), "bytes": out.stat().st_size, "sha256": sha256(out), "source_url": mansueto.RT_TO_PID_URL}

    out = FIXTURES / FOOTER_FILE
    footer = cut_footer(paths[FOOTER_PID], out)
    files[FOOTER_FILE] = {"pids": [FOOTER_PID], "bytes": out.stat().st_size, "sha256": sha256(out), **footer}

    manifest = {
        "title": "Fixture manifest: Mansueto StopWatch per-pattern parquet cuts for specs/mansueto-adapter.md",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "builder": "scripts/build_mansueto_fixtures.py",
        "data_edge_constant": mansueto.MANSUETO_DATA_EDGE,
        "timezone": mansueto.MANSUETO_TZ,
        "sources": sources,
        "files": files,
    }
    (FIXTURES / MANIFEST_FILE).write_text(json.dumps(manifest, indent=1) + "\n")
    for name, entry in files.items():
        print(f"wrote {name}: {entry.get('rows', '-')} rows, {entry['bytes']:,} bytes, sha256 {entry['sha256'][:12]}...")


if __name__ == "__main__":
    main()
