#!/usr/bin/env python3
"""Run-level view (ADR-003) for the patterns of a route list, from the Mansueto parquets or the raw day CSVs.

TODO.md Phase 1 "Run-level view for routes 8, 65, & 66". Reads the pid list the EDA notebook committed
(notebooks/routes_8_65_66_pids.json), calls the existing views (cta.views.run_level_from_mansueto_with_qa,
run_level_from_mansueto_raw_with_qa) and writes parquet plus QA tables as CSV under --out-dir:

  source=mansueto/pid=<pid>/year=<YYYY>.parquet   the view, one file per pid and year of the run's first arrival
  qa_mansueto.csv                                 pid, year, stage, rows_in, rows_out, reason, count
  mansueto_rows_by_month.csv                      rows per pid and month for every local parquet, with in_view
  detour_stop_arrivals.csv                        arrivals at stops added to a changed pattern, before today's geometry
  source=mansueto_raw/<day>.parquet               the view, one file per raw day
  qa_mansueto_raw.csv                             day, stage, rows_in, rows_out, reason, count (missing days included)
  raw_pattern_length.csv                          longest pdist per pid and day against the cached pattern length

Nothing is dropped or flagged here beyond what the adapters do: arrivals at detour stops the bus was not
serving stay in the view and are only counted (a flag is a schema change, for the stop-level spec).

Examples:
  python scripts/route_run_level.py --source mansueto --fetch
  python scripts/route_run_level.py --source mansueto_raw --fetch
  python scripts/route_run_level.py --source mansueto_raw --start 2026-09-15 --end 2026-09-15

--fetch downloads what is missing (about 2 GB of parquet, about 40 MB per raw day, one getpatterns call per
uncached pid; needs CTA_API_KEY in .env). Without it the script reads local caches only. The archive is not
a source here yet (TODO.md Foundation, "Archive adapter reads the v2 manifest").
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from cta import bustracker, calendar, mansueto, mansueto_raw, views  # noqa: E402

DEFAULT_PIDS_FILE = REPO_ROOT / "notebooks" / "routes_8_65_66_pids.json"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "route_run_level"
DEFAULT_PARQUET_DIR = REPO_ROOT / "data" / "mansueto"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "mansueto_raw"

EPOCH_SLACK_DAYS = 45  # notebooks/eda_routes_8_65_66.ipynb 6.1: a stop first seen later than this after the pid's first day was added
MAX_PATTERN_LENGTH_DIFF_MI = 0.05  # playbook "A detour keeps the pid and changes its geometry": further apart means another geometry
FEET_PER_MILE = 5280.0
REASON_MISSING_DAY_FILE = calendar.REASON_MISSING_DAY_FILE

MANSUETO_QA_COLUMNS = ["pid", "year"] + mansueto.QA_COLUMNS
ROWS_BY_MONTH_COLUMNS = ["pid", "month", "rows", "in_view"]
DETOUR_COLUMNS = ["pid", "first_day_today_geometry", "added_stops", "arrivals_before_today_geometry", "rows_in_period", "share_pct"]
LENGTH_COLUMNS = ["day", "pid", "pings", "max_pdist_mi", "pattern_mi", "diff_mi", "over_pattern_length"]


# --- pid list -------------------------------------------------------------------------------------


def load_pid_file(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def pids_where(pid_file: dict, flag: str) -> list[str]:
    """Pids of the committed list whose record has ``flag`` true (``usable_mansueto``, ``usable_archive``)."""
    return [str(r["pid"]) for r in pid_file["pids"] if r.get(flag)]


def retired_parquet_pids(pid_file: dict) -> list[str]:
    """Pids with a published parquet that getpatterns no longer serves: their rows cannot enter the view."""
    return [str(r["pid"]) for r in pid_file["pids"] if r.get("parquet_http_status") == 200 and not r.get("getpatterns_ok")]


def today_geometry_first_day(pid_file: dict) -> dict[str, str]:
    """Per pid, the first day of the geometry that is still current (the last ``geometry_changes`` entry)."""
    out: dict[str, str] = {}
    for change in pid_file.get("geometry_changes", []):
        pid = str(change["pid"])
        out[pid] = max(out.get(pid, ""), str(change["first_day_new"]))
    return out


def day_range(start: str, end: str) -> list[str]:
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


# --- QA helpers -----------------------------------------------------------------------------------


def stage_totals(qa: pd.DataFrame, by: list[str], call_keys: list[str]) -> pd.DataFrame:
    """Sum a per-call QA table over calls: rows in/out per stage and one column per reason; asserts additivity.

    ``call_keys`` identify one adapter call (pid and year, or day); ``by`` is the grouping to report.
    """
    stage = qa.drop_duplicates(call_keys + ["stage"]).groupby(by + ["stage"], sort=False)[["rows_in", "rows_out"]].sum()
    reasons = qa.dropna(subset=["reason"]).pivot_table(index=by + ["stage"], columns="reason", values="count", aggfunc="sum", fill_value=0)
    out = stage.join(reasons).fillna(0).astype("int64")
    reason_cols = [c for c in out.columns if c not in ("rows_in", "rows_out")]
    assert ((out["rows_in"] - out["rows_out"]) == out[reason_cols].sum(axis=1)).all(), "QA reasons do not sum to rows dropped"
    return out


# --- Mansueto parquet -----------------------------------------------------------------------------


def split_by_run_year(files: list[Path], pid: str, dest: Path) -> dict[str, Path]:
    """Copy the rows of ``pid`` into one directory per year of the run's first arrival; returns {year: dir}.

    Runs stay whole (a run that crosses New Year is in the year it started), so cleaning the pieces drops
    exactly what cleaning the whole file would. Rows of a run with no usable time go under year "none".
    """
    con = duckdb.connect()
    try:
        con.execute(
            f"""COPY (
                    SELECT * EXCLUDE (first_time), COALESCE(CAST(year(first_time) AS VARCHAR), 'none') AS run_year
                    FROM (SELECT *, min(bus_stop_time) OVER (PARTITION BY unique_trip_vehicle_day) AS first_time
                          FROM read_parquet(?) WHERE {mansueto._str_sql('pid')} = ?)
                ) TO '{dest}' (FORMAT parquet, PARTITION_BY (run_year))""",
            [[str(f) for f in files], str(pid)],
        )
    finally:
        con.close()
    return {p.name.split("=", 1)[1]: p for p in sorted(Path(dest).glob("run_year=*")) if p.is_dir()}


def build_mansueto(pids: list[str], *, parquet_dir: Path, pattern_stops: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    """Write the view per pid and year under ``out_dir/source=mansueto`` and return the QA table (pid, year, stage rows)."""
    target = Path(out_dir) / f"source={views.SOURCE_MANSUETO}"
    qas = []
    for pid in pids:
        pid_dir = target / f"pid={pid}"
        if pid_dir.exists():
            shutil.rmtree(pid_dir)
        pid_dir.mkdir(parents=True)
        stops = pattern_stops[pattern_stops["pid"] == pid]
        with tempfile.TemporaryDirectory(dir=target) as tmp:
            pieces = split_by_run_year(mansueto.parquet_files_for_pid(parquet_dir, pid), pid, Path(tmp) / "cut")
            for year, piece in pieces.items():
                view, qa = views.run_level_from_mansueto_with_qa([pid], parquet_dir=piece, pattern_stops=stops)
                qa.insert(1, "year", year)
                qas.append(qa)
                if len(view):
                    view.to_parquet(pid_dir / f"year={year}.parquet", index=False)
        done = pd.concat([q for q in qas if (q["pid"] == pid).any()])
        kept = int(done.loc[done["stage"] == mansueto.STAGES[-1]].drop_duplicates(["year"])["rows_out"].sum())
        print(f"  pid {pid}: {kept:,} view rows over {len(pieces)} years", flush=True)
    if not qas:
        return pd.DataFrame(columns=MANSUETO_QA_COLUMNS)
    return pd.concat(qas, ignore_index=True)[MANSUETO_QA_COLUMNS]


def rows_by_month(pids: list[str], view_pids: list[str], parquet_dir: Path) -> pd.DataFrame:
    """Published rows per pid and calendar month (Chicago wall time), for every pid with a local parquet."""
    con = duckdb.connect()
    parts = []
    try:
        for pid in pids:
            path = mansueto.local_parquet_path(pid, parquet_dir)
            if not path.is_file():
                continue
            part = con.execute(
                "SELECT strftime(bus_stop_time, '%Y-%m') AS month, count(*) AS rows FROM read_parquet(?) GROUP BY 1 ORDER BY 1",
                [str(path)],
            ).df()
            part.insert(0, "pid", pid)
            parts.append(part)
    finally:
        con.close()
    if not parts:
        return pd.DataFrame(columns=ROWS_BY_MONTH_COLUMNS)
    out = pd.concat(parts, ignore_index=True)
    out["in_view"] = out["pid"].isin(view_pids)
    return out[ROWS_BY_MONTH_COLUMNS]


def detour_stop_arrivals(out_dir: Path, today_first_day: dict[str, str]) -> pd.DataFrame:
    """Count view rows at stops added to a changed pattern, dated before the pattern took today's geometry.

    A stop is "added" when its first service date is more than ``EPOCH_SLACK_DAYS`` after the pid's first.
    The period runs from the first added stop's first day to the day before ``today_first_day[pid]``.
    Nothing is dropped: the parquet has these arrivals although the bus was not serving the stops
    (docs/2026-11-13-routes-8-65-66-eda.md).
    """
    con = duckdb.connect()
    rows = []
    try:
        for pid, first_today in sorted(today_first_day.items()):
            files = sorted((Path(out_dir) / f"source={views.SOURCE_MANSUETO}" / f"pid={pid}").glob("year=*.parquet"))
            if not files:
                continue
            con.execute("CREATE OR REPLACE TEMP TABLE v AS SELECT stop_id, CAST(service_date AS DATE) AS d FROM read_parquet(?)", [[str(f) for f in files]])
            added, start = con.execute(
                f"""WITH s AS (SELECT stop_id, min(d) AS first_day FROM v GROUP BY 1)
                    SELECT count(*), min(first_day) FROM s
                    WHERE first_day > (SELECT min(d) FROM v) + INTERVAL {EPOCH_SLACK_DAYS} DAY"""
            ).fetchone()
            if not added:
                rows.append({"pid": pid, "first_day_today_geometry": first_today, "added_stops": 0,
                             "arrivals_before_today_geometry": 0, "rows_in_period": 0, "share_pct": 0.0})
                continue
            at_added, in_period = con.execute(
                f"""WITH s AS (SELECT stop_id, min(d) AS first_day FROM v GROUP BY 1),
                         a AS (SELECT stop_id FROM s WHERE first_day > (SELECT min(d) FROM v) + INTERVAL {EPOCH_SLACK_DAYS} DAY)
                    SELECT count(*) FILTER (WHERE stop_id IN (SELECT stop_id FROM a)), count(*)
                    FROM v WHERE d >= ? AND d < CAST(? AS DATE)""",
                [start, first_today],
            ).fetchone()
            rows.append({"pid": pid, "first_day_today_geometry": first_today, "added_stops": int(added),
                         "arrivals_before_today_geometry": int(at_added), "rows_in_period": int(in_period),
                         "share_pct": round(100 * at_added / max(in_period, 1), 2)})
    finally:
        con.close()
    return pd.DataFrame(rows, columns=DETOUR_COLUMNS)


# --- Mansueto raw day CSVs ------------------------------------------------------------------------


def pattern_lengths_mi(pids: list[str], cache_dir: Path | None = None) -> dict[str, float]:
    """Cached getpatterns length (``ln``, feet) per pid, in miles."""
    out = {}
    for pid in pids:
        root = bustracker.load_getpatterns(pid, cache_dir or bustracker.api_cache_dir())
        ptrs = root["ptr"] if isinstance(root["ptr"], list) else [root["ptr"]]
        ptr = next(p for p in ptrs if str(p["pid"]) == pid)
        out[pid] = float(ptr["ln"]) / FEET_PER_MILE
    return out


def raw_pattern_length(day: str, path: Path, lengths_mi: dict[str, float]) -> pd.DataFrame:
    """Longest reported ``pdist`` per pid on one raw day against the cached pattern length.

    ``over_pattern_length`` (longer than the pattern by more than ``MAX_PATTERN_LENGTH_DIFF_MI``) means the
    day ran on another geometry. A shorter maximum proves nothing on a pid with few 5-minute pings.
    """
    con = duckdb.connect()
    try:
        got = con.execute(
            f"""SELECT {mansueto._str_sql('pid')} AS pid, count(*) AS pings, max(TRY_CAST(pdist AS DOUBLE)) AS max_pdist
                FROM read_csv(?, header=true, all_varchar=true) GROUP BY 1""",
            [str(path)],
        ).df()
    finally:
        con.close()
    got = got[got["pid"].isin(list(lengths_mi))].copy()
    got["day"] = day
    got["max_pdist_mi"] = (got["max_pdist"] / FEET_PER_MILE).round(3)
    got["pattern_mi"] = got["pid"].map(lengths_mi).round(3)
    got["diff_mi"] = (got["max_pdist_mi"] - got["pattern_mi"]).round(3)
    got["over_pattern_length"] = got["diff_mi"] > MAX_PATTERN_LENGTH_DIFF_MI
    return got.sort_values("pid")[LENGTH_COLUMNS].reset_index(drop=True)


def build_mansueto_raw(
    days: list[str], pids: list[str], *, csv_dir: Path, pattern_stops: pd.DataFrame, out_dir: Path,
    lengths_mi: dict[str, float] | None = None, fetch: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write the view per day under ``out_dir/source=mansueto_raw``; returns (QA table, pattern-length table).

    A day with no file is a coverage gap: one QA row with stage ``coverage`` and reason ``missing_day_file``.
    """
    target = Path(out_dir) / f"source={views.SOURCE_MANSUETO_RAW}"
    target.mkdir(parents=True, exist_ok=True)
    qas, lengths = [], []
    for day in days:
        try:
            path = mansueto_raw.fetch_day(day, csv_dir) if fetch else mansueto_raw.day_file(csv_dir, day)
        except FileNotFoundError:
            qas.append(pd.DataFrame([{"day": day, "stage": calendar.COVERAGE_STAGE, "rows_in": 0, "rows_out": 0,
                                      "reason": REASON_MISSING_DAY_FILE, "count": 0}]))
            print(f"  {day}: no day file", flush=True)
            continue
        view, qa = views.run_level_from_mansueto_raw_with_qa([day], pids, csv_dir=path.parent, pattern_stops=pattern_stops)
        view.to_parquet(target / f"{day}.parquet", index=False)
        qas.append(qa)
        if lengths_mi:
            lengths.append(raw_pattern_length(day, path, lengths_mi))
        print(f"  {day}: {len(view):,} view rows, {view['run_id'].nunique():,} runs", flush=True)
    qa_table = pd.concat(qas, ignore_index=True)[views.MANSUETO_RAW_QA_COLUMNS] if qas else pd.DataFrame(columns=views.MANSUETO_RAW_QA_COLUMNS)
    length_table = pd.concat(lengths, ignore_index=True) if lengths else pd.DataFrame(columns=LENGTH_COLUMNS)
    return qa_table, length_table


# --- CLI ------------------------------------------------------------------------------------------


def ensure_patterns(pids: list[str], cache_dir: Path | None, fetch: bool) -> pd.DataFrame:
    if fetch:
        bustracker.load_dotenv()
        bustracker.batch_pattern_stops(pids, cache_dir=cache_dir, max_requests=len(pids), progress_every=0)
    return bustracker.pattern_stops_table(pids, cache_dir)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, choices=[views.SOURCE_MANSUETO, views.SOURCE_MANSUETO_RAW])
    ap.add_argument("--pids-file", type=Path, default=DEFAULT_PIDS_FILE, help="pid list written by the EDA notebook")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--parquet-dir", type=Path, default=DEFAULT_PARQUET_DIR, help="trips_<pid>_full.parquet cache")
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="raw day CSV cache")
    ap.add_argument("--pattern-cache", type=Path, default=None, help="getpatterns cache dir (default data/cta_api_cache)")
    ap.add_argument("--start", metavar="YYYY-MM-DD", default=calendar.MANSUETO_RAW_FIRST_DAY, help="first raw day (mansueto_raw)")
    ap.add_argument("--end", metavar="YYYY-MM-DD", default=calendar.MANSUETO_RAW_EDGE, help="last raw day (mansueto_raw)")
    ap.add_argument("--fetch", action="store_true", help="download missing parquets, day files and patterns")
    args = ap.parse_args()

    pid_file = load_pid_file(args.pids_file)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.source == views.SOURCE_MANSUETO:
        pids = pids_where(pid_file, "usable_mansueto")
        retired = retired_parquet_pids(pid_file)
        stops = ensure_patterns(pids, args.pattern_cache, args.fetch)
        if args.fetch:
            for pid in pids + retired:
                if not mansueto.local_parquet_path(pid, args.parquet_dir).is_file():
                    mansueto.fetch_parquet(pid, args.parquet_dir)
                    print(f"  fetched pid {pid}", flush=True)
        qa = build_mansueto(pids, parquet_dir=args.parquet_dir, pattern_stops=stops, out_dir=args.out_dir)
        qa.to_csv(args.out_dir / "qa_mansueto.csv", index=False)
        rows_by_month(pids + retired, pids, args.parquet_dir).to_csv(args.out_dir / "mansueto_rows_by_month.csv", index=False)
        detour = detour_stop_arrivals(args.out_dir, today_geometry_first_day(pid_file))
        detour.to_csv(args.out_dir / "detour_stop_arrivals.csv", index=False)
        route = {str(r["pid"]): str(r["route"]) for r in pid_file["pids"]}
        print(stage_totals(qa.assign(route=qa["pid"].map(route)), ["route"], ["pid", "year"]).to_string())
        print(detour.to_string(index=False))
    else:
        pids = pids_where(pid_file, "usable_archive")
        stops = ensure_patterns(pids, args.pattern_cache, args.fetch)
        qa, lengths = build_mansueto_raw(
            day_range(args.start, args.end), pids, csv_dir=args.raw_dir, pattern_stops=stops, out_dir=args.out_dir,
            lengths_mi=pattern_lengths_mi(pids, args.pattern_cache), fetch=args.fetch,
        )
        qa.to_csv(args.out_dir / "qa_mansueto_raw.csv", index=False)
        lengths.to_csv(args.out_dir / "raw_pattern_length.csv", index=False)
        ingested = qa[qa["stage"] != calendar.COVERAGE_STAGE]
        if len(ingested):
            print(stage_totals(ingested.assign(all="all"), ["all"], ["day"]).to_string())
        print(f"days without a file: {sorted(qa.loc[qa['stage'] == calendar.COVERAGE_STAGE, 'day'])}")
        print(f"pid-days over the pattern length by more than {MAX_PATTERN_LENGTH_DIFF_MI} mi: {int(lengths['over_pattern_length'].sum())}")
    print(f"wrote {args.out_dir}")


if __name__ == "__main__":
    main()
