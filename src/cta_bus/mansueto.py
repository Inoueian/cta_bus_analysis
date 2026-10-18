"""Mansueto CTA Stop Watch CloudFront URLs, parquet columns, and local cache lookup."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path

from cta_bus.paths import MANSUETO_CACHE_DIR

BASE = "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch"
RT_TO_PID_URL = f"{BASE}/rt_to_pid.csv"

CLOUDFRONT_MIN_INTERVAL_SEC = 0.1

PARQUET_COLS = [
    "bus_stop_time",
    "unique_trip_vehicle_day",
    "stpid",
    "pid",
    "stop_sequence",
    "speed_mph",
    "seg_combined",
]

_last_cloudfront_call_monotonic: float = 0.0


def _throttle_cloudfront() -> None:
    global _last_cloudfront_call_monotonic
    now = time.monotonic()
    elapsed = now - _last_cloudfront_call_monotonic
    if _last_cloudfront_call_monotonic > 0 and elapsed < CLOUDFRONT_MIN_INTERVAL_SEC:
        time.sleep(CLOUDFRONT_MIN_INTERVAL_SEC - elapsed)
    _last_cloudfront_call_monotonic = time.monotonic()


def parquet_url(pid: str) -> str:
    return f"{BASE}/processed_by_pid/trips_{pid}_full.parquet"


def parquet_http_status(pid: str) -> int:
    _throttle_cloudfront()
    req = urllib.request.Request(parquet_url(pid), method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def local_parquet_path(
    pid: str,
    *,
    prefer_local: bool = True,
    cache_variant: str = "last30d",
) -> str | Path:
    """Prefer cached file under data/mansueto/ when prefer_local (e.g. last30d, last365d)."""
    if prefer_local:
        cached = MANSUETO_CACHE_DIR / f"trips_{pid}_{cache_variant}.parquet"
        if cached.is_file():
            return cached
    return parquet_url(pid)
