#!/usr/bin/env python3
"""Cache last N days of Mansueto parquets for DLSD pattern IDs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
BOUNDARIES_PATH = REPO_ROOT / "notebooks" / "dlsd_boundaries_snapshot.json"
DATA_DIR = REPO_ROOT / "data" / "mansueto"
BASE = "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch"

COLS = [
    "bus_stop_time",
    "unique_trip_vehicle_day",
    "stpid",
    "pid",
    "stop_sequence",
    "speed_mph",
    "seg_combined",
]


def parquet_url(pid: str) -> str:
    return f"{BASE}/processed_by_pid/trips_{pid}_full.parquet"


def load_pids() -> list[str]:
    data = json.loads(BOUNDARIES_PATH.read_text())
    return sorted(data.keys(), key=lambda x: int(x))


def cache_pid(pid: str, days: int, force: bool) -> tuple[str, int, int] | None:
    out = DATA_DIR / f"trips_{pid}_last{days}d.parquet"
    if out.exists() and not force:
        size = out.stat().st_size
        rows = len(pd.read_parquet(out, columns=["stpid"]))
        return pid, rows, size

    url = parquet_url(pid)
    print(f"  Downloading {pid} from CloudFront ...")
    try:
        df = pd.read_parquet(url, columns=COLS)
    except Exception as exc:
        print(f"  ERROR pid={pid}: {exc}", file=sys.stderr)
        return None

    if df.empty:
        print(f"  WARN pid={pid}: empty remote file", file=sys.stderr)
        return None

    max_ts = df["bus_stop_time"].max()
    cutoff = max_ts - pd.Timedelta(days=days)
    df = df[df["bus_stop_time"] >= cutoff].copy()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return pid, len(df), out.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Calendar days before max(bus_stop_time) to keep (default: 30)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if local cache exists",
    )
    args = parser.parse_args()

    if not BOUNDARIES_PATH.is_file():
        raise SystemExit(f"Missing {BOUNDARIES_PATH}")

    pids = load_pids()
    print(f"Caching {len(pids)} PIDs -> {DATA_DIR} (last {args.days} days)")

    total_rows = 0
    total_bytes = 0
    ok = 0
    for pid in pids:
        result = cache_pid(pid, args.days, args.force)
        if result is None:
            continue
        pid, rows, size = result
        ok += 1
        total_rows += rows
        total_bytes += size
        print(f"  {pid}: {rows:,} rows, {size / 1e6:.1f} MB -> {DATA_DIR.name}/trips_{pid}_last{args.days}d.parquet")

    print(f"\nDone: {ok}/{len(pids)} files, {total_rows:,} rows, {total_bytes / 1e6:.1f} MB total")


if __name__ == "__main__":
    main()
