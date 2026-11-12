#!/usr/bin/env python3
"""Build the committed Mansueto raw-positions fixture for specs/mansueto-raw-adapter.md.

Writes under tests/fixtures/:
  mansueto_raw_2026-10-22_michigan.csv.gz   header plus every line of full_day_data/2026-10-22.csv whose
                                            pid is one of the 45 in notebooks/michigan_ave_kept_pids.json,
                                            byte-for-byte, in source order; gzip with mtime 0 and no file name
  mansueto_raw.manifest.json                source URL, HEAD bytes / Last-Modified, fetch time; rows / bytes /
                                            SHA-256 / cut and self-checks for the fixture

The source day file (44 MB) is downloaded into --csv-dir (default data/mansueto_raw, gitignored) unless
already there. The bucket publishes no manifest (ADR-009), so the guard is the HEAD recorded below: the
builder refuses if the bucket's Content-Length or Last-Modified differs from SOURCE_BYTES /
SOURCE_LAST_MODIFIED, or if the local copy's size differs from SOURCE_BYTES.

Example:
  python scripts/build_mansueto_raw_fixtures.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cta import mansueto  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
DEFAULT_CSV_DIR = REPO_ROOT / "data" / "mansueto_raw"
KEPT_PIDS = REPO_ROOT / "notebooks" / "michigan_ave_kept_pids.json"

DAY = "2026-10-22"  # a Thursday in both sources, outside archive known_gaps and missing CSV days (spec Fixtures)
SOURCE_BYTES = 43_877_441  # HEAD 2026-11-10 and 2026-11-11 (specs/mansueto-raw-adapter.md Fixtures)
SOURCE_LAST_MODIFIED = "2026-10-23T10:02:16+00:00"  # same HEADs
SOURCE_ROWS = 212_797  # data rows, docs/2026-11-10-mansueto-raw-day-profile.md
PID_COLUMN = "pid"
MAX_FIXTURE_BYTES = 1_000_000  # CLAUDE.md Rule 3 per-file budget

FIXTURE_FILE = f"mansueto_raw_{DAY}_michigan.csv.gz"
MANIFEST_FILE = "mansueto_raw.manifest.json"


def source_url(day: str) -> str:
    return f"{mansueto.BASE}/full_day_data/{day}.csv"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_source(csv_dir: Path, force: bool) -> tuple[Path, dict]:
    """Local copy of the day file; refuses if the bucket's HEAD moved from the recorded values (ADR-009)."""
    url = source_url(DAY)
    head = mansueto.http_head(url)
    if head["bytes"] != SOURCE_BYTES or head["last_modified"] != SOURCE_LAST_MODIFIED:
        raise SystemExit(
            f"{url} moved: bucket says bytes={head['bytes']} Last-Modified={head['last_modified']}, builder records "
            f"bytes={SOURCE_BYTES} Last-Modified={SOURCE_LAST_MODIFIED}. Re-measure (ADR-009, "
            "docs/2026-11-10-mansueto-raw-day-profile.md) before rebuilding."
        )
    csv_dir.mkdir(parents=True, exist_ok=True)
    path = csv_dir / f"{DAY}.csv"
    fetched_at = None
    if force or not path.is_file():
        print(f"fetching {url} ...")
        temp = path.with_suffix(".part")
        try:
            mansueto.download(url, temp)
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    if path.stat().st_size != SOURCE_BYTES:
        raise SystemExit(f"{path} is {path.stat().st_size} bytes, expected {SOURCE_BYTES}; refetch with --force-fetch")
    if fetched_at is None:
        fetched_at = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()
    return path, {"url": url, "bytes": head["bytes"], "last_modified": head["last_modified"], "fetched_at": fetched_at}


def cut(source: Path, pids: set[str], out: Path) -> dict:
    """Header plus lines whose pid is in ``pids``, verbatim, source order; returns self-checks."""
    rows_in = rows_out = 0
    pids_seen: set[str] = set()
    with source.open("rb") as f, out.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz:
            header = f.readline()
            columns = header.decode().rstrip("\r\n").split(",")
            idx = columns.index(PID_COLUMN)
            gz.write(header)
            for line in f:
                rows_in += 1
                fields = line.decode().split(",")
                if len(fields) != len(columns):
                    raise SystemExit(f"line {rows_in + 1} has {len(fields)} fields, header has {len(columns)}")
                if fields[idx] in pids:
                    gz.write(line)
                    rows_out += 1
                    pids_seen.add(fields[idx])
    if rows_in != SOURCE_ROWS:
        raise SystemExit(f"source has {rows_in} data rows, expected {SOURCE_ROWS}")
    return {
        "source_rows": rows_in,
        "rows": rows_out,
        "pids_requested": len(pids),
        "pids_present": len(pids_seen),
        "pids_absent": sorted(pids - pids_seen),
        "columns": columns,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR, help="where the full day file is cached")
    parser.add_argument("--force-fetch", action="store_true", help="download the day file even if cached")
    args = parser.parse_args(argv)

    source, source_meta = ensure_source(args.csv_dir, args.force_fetch)
    pids = {str(r["pid"]) for r in json.loads(KEPT_PIDS.read_text())["pids"]}
    out = FIXTURES / FIXTURE_FILE
    checks = cut(source, pids, out)
    size = out.stat().st_size
    if size > MAX_FIXTURE_BYTES:
        raise SystemExit(f"{out} is {size} bytes, over the {MAX_FIXTURE_BYTES} byte budget")
    manifest = {
        "title": "Fixture manifest: Mansueto raw day-CSV cut for specs/mansueto-raw-adapter.md",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "builder": "scripts/build_mansueto_raw_fixtures.py",
        "timezone": "America/Chicago",
        "sources": {DAY: source_meta},
        "files": {
            FIXTURE_FILE: {
                "rows": checks["rows"],
                "bytes": size,
                "sha256": sha256(out),
                "cut": {
                    "day": DAY,
                    "pids_from": "notebooks/michigan_ave_kept_pids.json",
                    "pids": sorted(pids),
                    "lines": "header plus lines whose pid column is in pids, verbatim, source order",
                    "gzip": "mtime 0, no file name, level 9",
                },
                "self_checks": {k: v for k, v in checks.items() if k != "rows"},
            }
        },
    }
    (FIXTURES / MANIFEST_FILE).write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{out.relative_to(REPO_ROOT)}: {checks['rows']} rows, {size} bytes, sha256 {manifest['files'][FIXTURE_FILE]['sha256']}")
    print(f"pids present {checks['pids_present']} of {checks['pids_requested']}; absent: {checks['pids_absent']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
