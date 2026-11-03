#!/usr/bin/env python3
"""Prototype: stop-arrival imputation from one Transit Alerts archive day (Michigan Ave corridor).

Evidence for ADR-004 and specs/archive-adapter.md; see docs/2026-11-03-archive-imputation-prototype.md.
Not the production implementation (that belongs in cta/). Requires duckdb, pandas, numpy.

Example:
  python scripts/proto_archive_imputation.py data/archive/bus-2026-10-29.ndjson.gz \
      --out data/archive/michigan_arrivals_2026-10-29.parquet

Steps
 1. Load one day of bus positions into DuckDB.
 2. Clean fixes as scorecard.sql steps 1-2 (dedup on trip key + vehicle_ts; trip key).
 3. Derive each corridor stop's pdist per pattern by projecting the stop onto the fix cloud
    (median pdist of fixes within --radius-m of the stop). Fallback only: production uses getpatterns.
 4. Impute the vehicle_ts at which each run crossed each stop pdist (linear interpolation between
    bracketing fixes, bracket gap <= --max-gap-s).
 5. Corridor minutes (entry -> exit) per run per pattern; compare with Mansueto medians.
 6. Headways at one stop as a wait-time sample.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STOPS = REPO_ROOT / "notebooks" / "michigan_ave_stops_snapshot.json"
DEFAULT_KEPT = REPO_ROOT / "notebooks" / "michigan_ave_kept_pids.json"

RADIUS_M = 40.0        # stop-to-fix match radius for the pdist projection fallback
MAX_GAP_S = 180.0      # scorecard profiling [T3]: longer gaps hide stand-stills and outages
MIN_PROJ_FIXES = 8     # fewer nearby fixes than this and the projected pdist is unreliable
HEADWAY_STOP = "1126"  # Michigan & Chicago NB

ARCHIVE_COLUMNS = {
    "ts": "BIGINT", "route": "VARCHAR", "pid": "VARCHAR", "vehicle_id": "VARCHAR", "lat": "DOUBLE",
    "lon": "DOUBLE", "pdist": "DOUBLE", "vehicle_ts": "BIGINT", "sched_start_sec": "INTEGER",
    "sched_start_date": "VARCHAR", "destination": "VARCHAR", "heading": "INTEGER",
}


def q1(con: duckdb.DuckDBPyConnection, sql: str):
    """First row of a query (DuckDB 2.x needs the result fully consumed before the next call)."""
    return con.execute(sql).fetchall()[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archive_day", type=Path, help="bus YYYY-MM-DD.ndjson.gz from the archive")
    ap.add_argument("--stops", type=Path, default=DEFAULT_STOPS)
    ap.add_argument("--kept", type=Path, default=DEFAULT_KEPT)
    ap.add_argument("--out", type=Path, help="optional parquet of imputed (run, stop) arrivals")
    ap.add_argument("--radius-m", type=float, default=RADIUS_M)
    ap.add_argument("--max-gap-s", type=float, default=MAX_GAP_S)
    args = ap.parse_args()

    stops = pd.DataFrame(json.load(open(args.stops))["stops"])
    stops["stpid"] = stops["stpid"].astype(str)
    kept = pd.DataFrame(json.load(open(args.kept))["pids"])
    kept["pid"] = kept["pid"].astype(str)
    pids = kept["pid"].tolist()

    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    cols = "{" + ",".join(f"'{k}':'{v}'" for k, v in ARCHIVE_COLUMNS.items()) + "}"
    con.execute(f"""
        CREATE TABLE raw AS
        SELECT ts, route, pid, vehicle_id vid, lat, lon, pdist, vehicle_ts vts,
               sched_start_sec sss, sched_start_date ssd, destination
        FROM read_json('{args.archive_day.resolve()}', format='newline_delimited', compression='gzip', columns={cols})""")
    n, nv, nr, np_ = q1(con, "SELECT count(*), count(DISTINCT vid), count(DISTINCT route), count(DISTINCT pid) FROM raw")
    print(f"rows={n:,} vehicles={nv} routes={nr} pids={np_}")

    sp = q1(con, """
        WITH f AS (SELECT DISTINCT route, vid, pid, ssd, sss, vts FROM raw),
             d AS (SELECT (vts - lag(vts) OVER (PARTITION BY route, vid, pid, ssd, sss ORDER BY vts))/1000.0 dt FROM f)
        SELECT quantile_cont(dt, [0.05, 0.25, 0.5, 0.75, 0.95]) FROM d WHERE dt IS NOT NULL AND dt < 600""")[0]
    print("fix spacing seconds p5/p25/p50/p75/p95:", [round(x, 1) for x in sp])
    pi = q1(con, """WITH p AS (SELECT DISTINCT ts FROM raw), d AS (SELECT (ts - lag(ts) OVER (ORDER BY ts))/1000.0 dt FROM p)
        SELECT quantile_cont(dt, [0.05, 0.5, 0.95]) FROM d WHERE dt IS NOT NULL""")[0]
    print("poll interval seconds p5/p50/p95:", [round(x, 1) for x in pi])

    # Step 2: clean fixes on the kept patterns.
    con.execute("CREATE TABLE pids AS SELECT * FROM (VALUES " + ",".join(f"('{p}')" for p in pids) + ") t(pid)")
    con.execute("""
        CREATE TABLE f AS
        SELECT route, vid, pid, ssd, sss, vts, min(pdist) pdist, any_value(lat) lat, any_value(lon) lon
        FROM raw WHERE pid IN (SELECT pid FROM pids) AND pdist IS NOT NULL AND vts IS NOT NULL
        GROUP BY ALL""")
    print("clean fixes on kept pids (rows, runs):", q1(con, "SELECT count(*), count(DISTINCT (vid, pid, ssd, sss)) FROM f"))

    # Step 3: project corridor stops onto each pattern's fix cloud (fallback for getpatterns pdist).
    con.register("stops", stops[["stpid", "stpnm", "lat", "lon", "rtdirs"]])
    proj = con.execute(f"""
        SELECT f.pid, s.stpid, s.stpnm, count(*) n_fixes, median(f.pdist) stop_pdist,
               quantile_cont(f.pdist, 0.1) p10, quantile_cont(f.pdist, 0.9) p90
        FROM f JOIN stops s
          ON 111320 * sqrt(power(f.lat - s.lat, 2) + power(cos(radians(s.lat)) * (f.lon - s.lon), 2)) <= {args.radius_m}
        GROUP BY ALL HAVING count(*) >= {MIN_PROJ_FIXES}""").df()
    proj["spread_ft"] = proj.p90 - proj.p10
    print(f"\nstop projections: {len(proj)} (pid, stop) pairs; spread p50={proj.spread_ft.median():.0f} ft p90={proj.spread_ft.quantile(.9):.0f} ft")
    dirs = kept.set_index("pid")["rtdir"].to_dict()
    rtdirs = stops.set_index("stpid")["rtdirs"]
    proj = proj[[dirs[p] in str(r) for p, r in zip(proj.pid, proj.stpid.map(rtdirs))]]
    con.register("proj", proj[["pid", "stpid", "stpnm", "stop_pdist"]])

    # Step 4: impute arrival vehicle_ts at each stop for each run.
    con.execute(f"""
        CREATE TABLE arrivals AS
        WITH pr AS (
          SELECT route, vid, pid, ssd, sss, lag(vts) OVER w t0, vts t1, lag(pdist) OVER w p0, pdist p1
          FROM f WINDOW w AS (PARTITION BY route, vid, pid, ssd, sss ORDER BY vts))
        SELECT pr.route, pr.vid, pr.pid, pr.ssd, pr.sss, s.stpid, s.stpnm, s.stop_pdist,
               (t1 - t0) / 1000.0 gap_s, t0 + (t1 - t0) * (s.stop_pdist - p0) / (p1 - p0) arr_ms
        FROM pr JOIN proj s ON s.pid = pr.pid
        WHERE p0 IS NOT NULL AND p1 > p0 AND p0 <= s.stop_pdist AND s.stop_pdist < p1
          AND (t1 - t0) / 1000.0 <= {args.max_gap_s}""")
    con.execute("""CREATE TABLE arr AS SELECT route, vid, pid, ssd, sss, stpid, stpnm, stop_pdist,
        min(arr_ms) arr_ms, min(gap_s) gap_s, count(*) n_cross FROM arrivals GROUP BY ALL""")
    a_n, a_runs, multi = q1(con, "SELECT count(*), count(DISTINCT (vid,pid,ssd,sss)), count(*) FILTER (WHERE n_cross > 1) FROM arr")
    print(f"imputed arrivals: {a_n:,} rows over {a_runs:,} runs; (run,stop) with >1 crossing: {multi}")
    print("bracket gap seconds p50/p90/p99:", [round(x, 1) for x in q1(con, "SELECT quantile_cont(gap_s,[0.5,0.9,0.99]) FROM arr")[0]])

    # Step 5: corridor minutes per run vs Mansueto medians in the kept list.
    con.register("kept", kept[["pid", "route", "rtdir", "entry_stpid", "exit_stpid", "n_trips", "median_minutes", "p25_minutes", "p75_minutes"]])
    corr = con.execute("""
        WITH e AS (SELECT a.pid, a.vid, a.ssd, a.sss, a.arr_ms entry_ms FROM arr a JOIN kept k ON k.pid=a.pid AND k.entry_stpid=a.stpid),
             x AS (SELECT a.pid, a.vid, a.ssd, a.sss, a.arr_ms exit_ms FROM arr a JOIN kept k ON k.pid=a.pid AND k.exit_stpid=a.stpid)
        SELECT k.pid, k.route, k.rtdir, count(x.exit_ms) n_runs_archive,
               median((x.exit_ms - e.entry_ms)/60000.0) median_min_archive,
               quantile_cont((x.exit_ms - e.entry_ms)/60000.0, 0.25) p25_archive,
               quantile_cont((x.exit_ms - e.entry_ms)/60000.0, 0.75) p75_archive,
               k.n_trips n_trips_mansueto_30d, k.median_minutes median_min_mansueto, k.p25_minutes p25_mansueto, k.p75_minutes p75_mansueto
        FROM kept k LEFT JOIN e USING (pid) LEFT JOIN x ON x.pid=e.pid AND x.vid=e.vid AND x.ssd=e.ssd AND x.sss=e.sss
        GROUP BY ALL ORDER BY k.route, k.rtdir, k.pid""").df()
    pd.set_option("display.width", 200)
    print("\nCorridor minutes, archive day vs Mansueto last-30d medians:")
    print(corr.round(1).to_string(index=False))
    ok = corr.dropna(subset=["median_min_archive"])
    print(f"\nratio archive/Mansueto median: p50={np.median(ok.median_min_archive/ok.median_min_mansueto):.3f}, "
          f"pids with archive runs={len(ok)}/{len(corr)}")

    # Step 6: headways at one stop.
    for label, where in [("route 151 NB", "route='151'"), ("all kept NB routes", "TRUE")]:
        hw = con.execute(f"""
            WITH t AS (SELECT arr_ms FROM arr WHERE stpid='{HEADWAY_STOP}' AND {where}),
                 d AS (SELECT (arr_ms - lag(arr_ms) OVER (ORDER BY arr_ms))/60000.0 headway_min,
                              hour(timezone('America/Chicago', to_timestamp(arr_ms/1000.0))) hr FROM t)
            SELECT count(*) n, round(quantile_cont(headway_min,0.5),1) p50, round(quantile_cont(headway_min,0.9),1) p90,
                   round(max(headway_min),1) max_min FROM d WHERE headway_min IS NOT NULL AND hr BETWEEN 7 AND 19""").df()
        print(f"\nHeadways at stop {HEADWAY_STOP}, 7am-8pm, {label}:")
        print(hw.to_string(index=False))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY (SELECT * FROM arr ORDER BY pid, vid, ssd, sss, stop_pdist) TO '{args.out.resolve()}' (FORMAT PARQUET)")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
