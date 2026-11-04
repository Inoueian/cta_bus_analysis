"""Bus Tracker ``getpatterns`` stop lists, read from the on-disk cache (no network here).

The cache files ``getpatterns_<pid>.json`` are written by ``notebooks/cta_api.batch_pattern_stops``
(moving to ``cta/`` with specs/package-migration.md), which owns the API key, budget and throttle.
This module only parses them into the stop table the archive imputation needs (STOP_PDIST_SOURCE).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PATTERN_STOP_COLUMNS = ["pid", "rtdir", "seq", "stpid", "stpnm", "lat", "lon", "pdist_ft"]


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_cache_dir() -> Path:
    return repo_root() / "data" / "cta_api_cache"


def cache_path(pid: str, cache_dir: Path) -> Path:
    return Path(cache_dir) / f"getpatterns_{pid}.json"


def load_getpatterns(pid: str, cache_dir: Path | None = None) -> dict | None:
    """Cached ``bustime-response`` root for one pid, or None when not cached."""
    path = cache_path(str(pid), cache_dir or default_cache_dir())
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def stops_from_getpatterns(root: dict) -> pd.DataFrame:
    """Stop points (``typ == 'S'``) of every pattern in a getpatterns response, one row per stop."""
    ptr = root.get("ptr", [])
    if isinstance(ptr, dict):
        ptr = [ptr]
    rows = []
    for p in ptr:
        pts = p.get("pt", [])
        if isinstance(pts, dict):
            pts = [pts]
        for pt in pts:
            if pt.get("typ") != "S":
                continue
            rows.append(
                {
                    "pid": str(p["pid"]),
                    "rtdir": str(p.get("rtdir", "")),
                    "seq": int(pt["seq"]),
                    "stpid": str(pt["stpid"]),
                    "stpnm": pt.get("stpnm"),
                    "lat": float(pt["lat"]),
                    "lon": float(pt["lon"]),
                    "pdist_ft": float(pt.get("pdist", 0)),
                }
            )
    df = pd.DataFrame(rows, columns=PATTERN_STOP_COLUMNS)
    return df.sort_values(["pid", "seq"]).reset_index(drop=True)


def pattern_stops_table(pids: list[str], cache_dir: Path | None = None) -> pd.DataFrame:
    """Stop table for ``pids`` from the cache. Raises ``FileNotFoundError`` naming any pid not cached."""
    cache_dir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
    frames = []
    missing = []
    for pid in dict.fromkeys(str(p) for p in pids):
        root = load_getpatterns(pid, cache_dir)
        if root is None:
            missing.append(pid)
            continue
        df = stops_from_getpatterns(root)
        frames.append(df[df["pid"] == pid])
    if missing:
        raise FileNotFoundError(
            f"no getpatterns cache under {cache_dir} for {len(missing)} pids: {missing}; "
            "fetch them with cta_api.batch_pattern_stops(pids, cache_dir=...)"
        )
    if not frames:
        return pd.DataFrame(columns=PATTERN_STOP_COLUMNS)
    return pd.concat(frames, ignore_index=True)
