#!/usr/bin/env python3
"""Build the committed test fixtures for specs/archive-adapter.md.

Two independent parts, each off by default:

  --day-file      Download one archive day (verified against the index), keep only the rows whose pid
                  is in --pids-file, and write tests/fixtures/archive_<day>_michigan.ndjson.gz plus a
                  manifest archive_<day>_michigan.index.json (rows, bytes, sha256, known_gaps) that
                  cta.archive.ingest_day verifies against. Deterministic gzip (mtime 0).
  --getpatterns   Fetch Bus Tracker getpatterns for the same pids through notebooks/cta_api (uses the
                  daily budget counter under data/cta_api_cache, cache hits cost nothing) and copy the
                  JSON into tests/fixtures/getpatterns/. Needs CTA_API_KEY in .env.

Examples:
  python scripts/build_archive_fixtures.py --day 2026-10-29 --day-file
  python scripts/build_archive_fixtures.py --getpatterns
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cta import archive  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
DEFAULT_PIDS_FILE = REPO_ROOT / "notebooks" / "michigan_ave_kept_pids.json"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "archive" / "raw"


def load_pids(path: Path) -> list[str]:
    return [str(r["pid"]) for r in json.loads(path.read_text())["pids"]]


def build_day_fixture(day: str, index_location: str, raw_dir: Path, pids: list[str], label: str, pids_file: Path) -> None:
    index = archive.fetch_index(index_location, raw_dir)
    meta = archive.day_file_meta(index, day)
    src = archive.ensure_day_file(meta, raw_dir)
    keep = set(pids)
    out = FIXTURES / f"archive_{day}_{label}.ndjson.gz"
    buf = io.BytesIO()
    n = 0
    with gzip.open(src, "rt") as f, gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, filename="") as g:
        for line in f:
            if json.loads(line).get("pid") in keep:
                g.write(line.encode())
                n += 1
    FIXTURES.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf.getvalue())
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    manifest = {
        "title": f"Fixture manifest: Transit Alerts bus archive day {day} filtered to {len(keep)} {label} pids",
        "source_index_generated_at": index.get("generated_at"),
        "timezone": index.get("timezone", "America/Chicago"),
        "source_day": {"date": day, "files": {"bus": {k: meta[k] for k in ("path", "rows", "bytes", "sha256")}}},
        "filter": {"pids_file": str(pids_file.resolve().relative_to(REPO_ROOT)), "n_pids": len(keep)},
        "known_gaps": index.get("known_gaps", []),
        "days": [
            {
                "date": day,
                "files": {"bus": {"path": out.name, "rows": n, "bytes": out.stat().st_size, "sha256": sha}},
            }
        ],
    }
    (FIXTURES / f"archive_{day}_{label}.index.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"wrote {out} ({n:,} rows, {out.stat().st_size:,} bytes, sha256 {sha})")


def build_getpatterns_fixture(pids: list[str]) -> None:
    notebooks = REPO_ROOT / "notebooks"
    if str(notebooks) not in sys.path:
        sys.path.insert(0, str(notebooks))
    import cta_api  # noqa: E402  (moves to cta/ with specs/package-migration.md)

    cta_api.load_dotenv()
    cache_dir = cta_api.api_cache_dir()
    before = cta_api.daily_api_request_count(cache_dir)
    result = cta_api.batch_pattern_stops(pids, use_cache=True, cache_dir=cache_dir, progress_every=0)
    after = cta_api.daily_api_request_count(cache_dir)
    dest = FIXTURES / "getpatterns"
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for pid in pids:
        src = cache_dir / f"getpatterns_{pid}.json"
        if src.is_file():
            shutil.copy(src, dest / src.name)
            copied += 1
    missing = [p for p in pids if p not in result]
    print(f"getpatterns: {copied}/{len(pids)} pids copied to {dest}; live calls this run: {after - before}; missing: {missing}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", default="2026-10-29", help="archive day for --day-file")
    ap.add_argument("--day-file", action="store_true", help="build the filtered day file and manifest")
    ap.add_argument("--getpatterns", action="store_true", help="fetch/copy getpatterns JSON for the pids")
    ap.add_argument("--pids-file", type=Path, default=DEFAULT_PIDS_FILE)
    ap.add_argument("--label", default="michigan", help="fixture name suffix")
    ap.add_argument("--index", default=archive.INDEX_URL, help="archive index URL or pinned local copy")
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = ap.parse_args()
    if not (args.day_file or args.getpatterns):
        ap.error("nothing to do: pass --day-file and/or --getpatterns")
    pids = load_pids(args.pids_file)
    if args.day_file:
        build_day_fixture(args.day, args.index, args.raw_dir, pids, args.label, args.pids_file)
    if args.getpatterns:
        build_getpatterns_fixture(pids)


if __name__ == "__main__":
    main()
