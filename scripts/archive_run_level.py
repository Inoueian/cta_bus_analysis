#!/usr/bin/env python3
"""Build the ADR-003 run-level view from Transit Alerts archive days (specs/archive-adapter.md).

Ingests each requested day into a DuckDB cache (checksum-verified against the archive index, pinned
next to the raw files), imputes stop arrivals from the cached getpatterns stop lists, and writes the
view as parquet plus a per-day QA table as CSV.

Examples:
  python scripts/archive_run_level.py --days 2026-10-29 --out data/archive/michigan_2026-10-29.parquet
  python scripts/archive_run_level.py --start 2026-10-01 --end 2026-10-31 --out data/archive/michigan_oct.parquet
  python scripts/archive_run_level.py --days 2026-10-29 --index data/archive/raw/index.pinned.json ...

Needs: the getpatterns cache for every pid (data/cta_api_cache/getpatterns_<pid>.json, fetched once by
cta.bustracker.batch_pattern_stops) and curl for the archive. Never run against tests/fixtures/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from cta import archive, bustracker, views  # noqa: E402

DEFAULT_PIDS_FILE = REPO_ROOT / "notebooks" / "michigan_ave_kept_pids.json"
DEFAULT_DB = REPO_ROOT / "data" / "archive" / "positions.duckdb"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "archive" / "raw"


def day_range(start: str, end: str) -> list[str]:
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def load_pids(path: Path) -> list[str]:
    data = json.loads(path.read_text())
    records = data["pids"] if isinstance(data, dict) else data
    return [str(r["pid"] if isinstance(r, dict) else r) for r in records]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--days", nargs="+", metavar="YYYY-MM-DD", help="archive days to include")
    g.add_argument("--start", metavar="YYYY-MM-DD", help="first day of an inclusive range (with --end)")
    ap.add_argument("--end", metavar="YYYY-MM-DD", help="last day of the range")
    ap.add_argument("--pids", nargs="+", help="pattern ids (default: --pids-file)")
    ap.add_argument("--pids-file", type=Path, default=DEFAULT_PIDS_FILE, help="JSON with a 'pids' list of {pid: ...}")
    ap.add_argument("--index", default=archive.INDEX_URL, help="archive index URL or a pinned local copy")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="DuckDB cache of ingested days")
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="where day files and the pinned index go")
    ap.add_argument("--pattern-cache", type=Path, default=None, help="getpatterns cache dir (default data/cta_api_cache)")
    ap.add_argument("--out", type=Path, required=True, help="parquet path for the run-level view")
    ap.add_argument("--qa-out", type=Path, default=None, help="CSV path for the QA table (default: <out>.qa.csv)")
    args = ap.parse_args()

    if args.start and not args.end:
        ap.error("--start needs --end")
    days = args.days or day_range(args.start, args.end)
    pids = args.pids or load_pids(args.pids_file)

    index = archive.fetch_index(args.index, args.raw_dir)
    pinned = archive.pin_index(index, args.raw_dir)
    print(f"index pinned at {pinned} ({len(index['days'])} days, {len(index.get('known_gaps', []))} known gaps)")
    stops = bustracker.pattern_stops_table(pids, args.pattern_cache)
    print(f"pattern stops: {len(stops)} rows for {stops['pid'].nunique()} pids")

    con = archive.open_archive_db(args.db)
    try:
        view = views.run_level_from_archive(
            days, pids, con=con, index=index, raw_dir=args.raw_dir, pattern_stops=stops
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        view.to_parquet(args.out, index=False)
        print(f"wrote {args.out}: {len(view):,} (run, stop) rows, {view['run_id'].nunique():,} runs, {len(days)} days")
        qa_frames = []
        for day in days:
            q = archive.qa(con, day)
            q.insert(0, "day", day)
            qa_frames.append(q)
        qa_path = args.qa_out or args.out.with_suffix(".qa.csv")
        qa = pd.concat(qa_frames, ignore_index=True)
        qa.to_csv(qa_path, index=False)
        print(f"wrote {qa_path}")
        print(qa.to_string(index=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
