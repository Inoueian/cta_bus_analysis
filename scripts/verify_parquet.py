#!/usr/bin/env python3
"""Verify Mansueto trips_<PID>_full.parquet schema and trip-id behavior.

See knowledge-vault: 2026-09-15-processed-parquet-verification-checklist.md
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from cta_bus.cta_api import RT_TO_PID_URL, parquet_url

# ADR-003 assumed names -> verified Mansueto columns (PID 6662, route 66, 2026-09-15)
EXPECTED_MAPPING = {
    "run_id (trip_id)": "unique_trip_vehicle_day",
    "route": "rt",
    "pattern_id": "pattern_id -> pid",
    "stop_id": "stpid",
    "stop_sequence_index": "stop_sequence",
    "arrival_time": "bus_stop_time",
    "direction": "(not in parquet; join from GTFS/pattern metadata at ingestion)",
}

MANSUETO_EXTRA = ["seg_combined", "typ", "speed_mph", "vid", "p_stp_id"]


def pids_for_route(route: str) -> list[str]:
    rt_df = pd.read_csv(RT_TO_PID_URL)
    rt_df["rt"] = rt_df["rt"].astype(str)
    pids = rt_df.loc[rt_df["rt"] == str(route), "pid"].astype(str).tolist()
    if not pids:
        raise SystemExit(f"No PIDs found for route {route} in {RT_TO_PID_URL}")
    return pids


def verify(df: pd.DataFrame, pid: str, route: str) -> None:
    trip_col = "unique_trip_vehicle_day"
    stop_col = "stpid"
    time_col = "bus_stop_time"

    print(f"PID={pid} route={route} rows={len(df):,} columns={len(df.columns)}")
    print("\n## 1. Column names")
    print(df.columns.tolist())
    print("\nADR-003 mapping (verified on route 66 / PID 6662):")
    for logical, physical in EXPECTED_MAPPING.items():
        print(f"  {logical}: {physical}")
    print("Extra Mansueto columns:", MANSUETO_EXTRA)

    print("\n## 2. Trip ID")
    if trip_col not in df.columns:
        print(f"ERROR: missing {trip_col}")
        sys.exit(1)
    print(f"nulls: {df[trip_col].isna().sum()}")
    print("samples:", df[trip_col].head(5).tolist())

    print("\n## 3. One row per (trip, stop)")
    dup = df.groupby([trip_col, stop_col]).size()
    n_dup = int((dup > 1).sum())
    print(f"duplicate (trip, stop) keys: {n_dup}")
    if n_dup:
        print(dup[dup > 1].head())

    stops = df.groupby(trip_col)[stop_col].nunique()
    print(stops.describe())

    print("\n## 4. Date range")
    print(f"{time_col} min: {df[time_col].min()}")
    print(f"{time_col} max: {df[time_col].max()}")

    print("\n## 5. Stop coverage (relative)")
    print(stops.describe())

    print("\n## 6. dtypes")
    print(df.dtypes)

    missing = {trip_col, stop_col, time_col, "stop_sequence", "rt", "pid"}
    absent = missing - set(df.columns)
    if absent:
        print(f"\nERROR: expected columns missing: {sorted(absent)}")
        sys.exit(1)
    print("\nOK: checklist passed for core columns.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Mansueto processed parquet.")
    parser.add_argument("--route", default="66", help="CTA route number (default: 66)")
    parser.add_argument(
        "--pid",
        default=None,
        help="Pattern ID (default: first PID for route from rt_to_pid.csv)",
    )
    args = parser.parse_args()

    pids = pids_for_route(args.route)
    pid = args.pid or pids[0]
    if args.pid is None:
        print(f"Route {args.route} PIDs (first 10): {pids[:10]}")

    url = parquet_url(pid)
    print(f"Loading {url} ...")
    df = pd.read_parquet(url)
    verify(df, pid=pid, route=args.route)


if __name__ == "__main__":
    main()
