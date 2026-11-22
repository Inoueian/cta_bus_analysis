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

--stop-validity builds only the day cuts of specs/mansueto-stop-validity.md, with their own manifest
mansueto_routes8_65_66.manifest.json (the shape of mansueto.manifest.json), leaving the files above and their manifest
untouched:
  mansueto_2025-10-14_routes8_65_66.parquet   rows of the getpatterns_ok pids of notebooks/routes_8_65_66_pids.json
  mansueto_2025-12-02_routes8_65_66.parquet   whose bus_stop_time falls on that Chicago day, 11 columns verbatim
Its sources pass the same bucket guards (regenerated on MANSUETO_DATA_EDGE; footer rows equal a scan). The last-row
check is not applied to them: it protects the 30-day window of the 6410 cut, and a minor pattern can stop running
before the freeze without the bucket having moved (route 65's 3213 ends 2026-07-26; owner, 2026-11-21). Each source's
last row is recorded in the manifest.

Examples:
  python scripts/build_mansueto_fixtures.py
  python scripts/build_mansueto_fixtures.py --stop-validity
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

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
# A run whose id carries the next date and whose first row in a day cut is at or after this Chicago hour is a late-evening
# start (owner, 2026-11-21): about 2% of all runs every month since 2022, 23% to 31% of those starting after 22:00; on
# 2025-10-14 and 2025-12-02 every such run starts at 22:17 or later. The 2026-07-27 cut has none: runs dated the 28th are
# past the freeze (docs/2026-11-21-mansueto-next-day-run-ids.md).
LATE_EVENING_HOUR = 22
DEFAULT_PIDS_FILE = REPO_ROOT / "notebooks" / "routes_8_65_66_pids.json"
PID_FLAG = "getpatterns_ok"  # the 24 pids the run-level view reads (specs/mansueto-stop-validity.md Fixtures)
STOP_VALIDITY_DAYS = ("2025-10-14", "2025-12-02")  # specs/mansueto-stop-validity.md: between the route 8 and 66 changes, and a week after the last
STOP_VALIDITY_SPEC = "specs/mansueto-stop-validity.md"
STOP_VALIDITY_MANIFEST = "mansueto_routes8_65_66.manifest.json"  # its own file: tests pin mansueto.manifest.json's source count

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


def ensure_source(pid: str, parquet_dir: Path, force: bool, check_last_row: bool = True) -> tuple[Path, dict]:
    """Local full parquet plus its metadata file, fetching either when missing.

    ``check_last_row`` refuses a file whose last row is more than ``MAX_EDGE_LAG_DAYS`` before the data edge; the
    dated cuts of ``--stop-validity`` skip it (module docstring). The ``Last-Modified`` guard always applies.
    """
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
    if last_row > edge or (check_last_row and last_row < edge - dt.timedelta(days=MAX_EDGE_LAG_DAYS)):
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


def cut_one_day(paths: list[Path], out: Path, day: str = ONE_DAY_DATE) -> dict:
    lo = pd.Timestamp(day)
    hi = lo + pd.Timedelta(days=1)  # wall-time bounds are the Chicago date only on a day without a DST transition
    tz = ZoneInfo(mansueto.MANSUETO_TZ)
    if lo.to_pydatetime().replace(tzinfo=tz).utcoffset() != hi.to_pydatetime().replace(tzinfo=tz).utcoffset():
        raise SystemExit(f"{day} has a DST transition in {mansueto.MANSUETO_TZ}: a wall-time cut is not one Chicago day")
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
    return {"date": day, "timezone": mansueto.MANSUETO_TZ}


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
    row for >= 99% of runs. Two exceptions are expected, counted apart and excused: a run embedding the previous
    date whose earliest row in the cut is before POST_MIDNIGHT_HOUR (a post-midnight continuation), and a run
    embedding the next date whose earliest row is at or after LATE_EVENING_HOUR (a late-evening start)."""
    df = pd.read_parquet(out, columns=["unique_trip_vehicle_day", "bus_stop_time"])
    first = df.groupby("unique_trip_vehicle_day")["bus_stop_time"].min()
    embedded = pd.to_datetime(first.index.to_series().str.extract(r"(\d{4}-\d{2}-\d{2})$")[0], errors="coerce")
    local_day = first.dt.normalize()
    same = embedded.values == local_day.values
    post_midnight = (embedded.values == (local_day - pd.Timedelta(days=1)).values) & (first.dt.hour < POST_MIDNIGHT_HOUR).values
    late_evening = (embedded.values == (local_day + pd.Timedelta(days=1)).values) & (first.dt.hour >= LATE_EVENING_HOUR).values
    unexplained = ~same & ~post_midnight & ~late_evening
    share = float((same | post_midnight | late_evening).mean()) if len(same) else 1.0
    report = pd.DataFrame({"embedded": embedded.dt.strftime("%Y-%m-%d").values, "earliest_in_cut": first.values}, index=first.index)
    print(
        f"{label}: embedded service date == Chicago date of earliest row for {int(same.sum())} of {len(same)} runs; "
        f"{int(post_midnight.sum())} post-midnight continuations of the previous date; {int(late_evening.sum())} late-evening "
        f"starts carrying the next date; {int(unexplained.sum())} unexplained"
    )
    if unexplained.any():
        print(report[unexplained].to_string())
    if share < MIN_EMBEDDED_DATE_SHARE:
        raise SystemExit(f"{label}: only {share:.2%} of runs embed the earliest-arrival date (< {MIN_EMBEDDED_DATE_SHARE:.0%})")
    return {
        "runs": int(len(same)),
        "embedded_date_matches_earliest_row": int(same.sum()),
        "post_midnight_continuations": int(post_midnight.sum()),
        "late_evening_next_day": int(late_evening.sum()),
        "unexplained": int(unexplained.sum()),
    }


def file_entry(out: Path, pids: list[str], **extra) -> dict:
    return {"pids": pids, "rows": int(pq.read_metadata(out).num_rows), "bytes": out.stat().st_size, "sha256": sha256(out), **extra}


def source_entry(info: dict, counts: dict) -> dict:
    return {
        "url": info["url"],
        "bytes": info["bytes"],
        "last_modified": info["last_modified"],
        "fetched_at": info["fetched_at"],
        "data_edge": {k: info[k] for k in ("url", "bytes", "last_modified", "rows", "min_bus_stop_time", "max_bus_stop_time")},
        "null_bus_stop_time": counts["null_bus_stop_time"],
        "null_run_id_or_stpid": counts["null_run_id_or_stpid"],
    }


def build_stop_validity(parquet_dir: Path, pids_file: Path, force: bool) -> None:
    """The day cuts of specs/mansueto-stop-validity.md and their manifest ``STOP_VALIDITY_MANIFEST``."""
    pids = [str(r["pid"]) for r in json.loads(pids_file.read_text())["pids"] if r.get(PID_FLAG)]
    con = duckdb.connect()
    sources, paths = {}, {}
    edge_lag = dt.date.fromisoformat(mansueto.MANSUETO_DATA_EDGE) - dt.timedelta(days=MAX_EDGE_LAG_DAYS)
    for pid in pids:
        path, info = ensure_source(pid, parquet_dir, force, check_last_row=False)
        counts = source_null_counts(con, path)
        if counts["rows"] != info["rows"]:
            raise SystemExit(f"pid {pid}: footer says {info['rows']} rows, scan says {counts['rows']}")
        paths[pid], sources[pid] = path, source_entry(info, counts)
    early = {p: sources[p]["data_edge"]["max_bus_stop_time"] for p in pids
             if dt.date.fromisoformat(sources[p]["data_edge"]["max_bus_stop_time"][:10]) < edge_lag}
    print(f"{len(pids)} sources regenerated on {mansueto.MANSUETO_DATA_EDGE}, footer rows equal scans; "
          f"last row more than {MAX_EDGE_LAG_DAYS} day before the edge (recorded, not refused): {early or 'none'}")

    manifest_path = FIXTURES / STOP_VALIDITY_MANIFEST
    if manifest_path.is_file():  # a rebuild: the sources must be the files the committed cuts came from
        before = json.loads(manifest_path.read_text())["sources"]
        moved = [p for p in pids if p in before and before[p]["last_modified"] != sources[p]["last_modified"]]
        if moved:
            raise SystemExit(f"pids {moved}: Last-Modified differs from {manifest_path.name}; the bucket moved, re-measure (ADR-007)")
    built_at = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest = {
        "title": f"Fixture manifest: Mansueto StopWatch day cuts of routes 8, 65 and 66 for {STOP_VALIDITY_SPEC}",
        "built_at": built_at,
        "builder": "scripts/build_mansueto_fixtures.py --stop-validity",
        "data_edge_constant": mansueto.MANSUETO_DATA_EDGE,
        "timezone": mansueto.MANSUETO_TZ,
        "sources": {},
        "files": {},
    }
    for day in STOP_VALIDITY_DAYS:
        name = f"mansueto_{day}_routes8_65_66.parquet"
        out = FIXTURES / name
        window = cut_one_day([paths[p] for p in pids], out, day=day)
        present = sorted({mansueto._id_str(v) for v in pq.read_table(out, columns=["pid"])["pid"].to_pylist()}, key=int)
        manifest["files"][name] = file_entry(
            out, pids, window=window, pids_with_rows=present,
            guards={"last_modified_on_data_edge": True, "footer_rows_equal_scan": True,
                    "last_row_within_edge_lag": "not applied to a dated cut (owner, 2026-11-21)",
                    "sources_ending_before_edge_lag": early},
            service_date_check=check_embedded_service_date(out, name),
        )
    manifest["sources"].update(sources)
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")
    for day in STOP_VALIDITY_DAYS:
        name = f"mansueto_{day}_routes8_65_66.parquet"
        e = manifest["files"][name]
        print(f"wrote {name}: {e['rows']:,} rows, {e['bytes']:,} bytes, sha256 {e['sha256'][:12]}..., "
              f"{len(e['pids_with_rows'])} of {len(pids)} pids have rows")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parquet-dir", type=Path, default=DEFAULT_PARQUET_DIR, help="where the full per-pattern files live")
    ap.add_argument("--force-fetch", action="store_true", help="re-download the full files even if present")
    ap.add_argument("--stop-validity", action="store_true", help="build only the day cuts of specs/mansueto-stop-validity.md")
    ap.add_argument("--pids-file", type=Path, default=DEFAULT_PIDS_FILE, help=f"pid list for --stop-validity (pids flagged {PID_FLAG})")
    args = ap.parse_args()
    parquet_dir = args.parquet_dir
    parquet_dir.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    if args.stop_validity:
        build_stop_validity(parquet_dir, args.pids_file, args.force_fetch)
        return

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
