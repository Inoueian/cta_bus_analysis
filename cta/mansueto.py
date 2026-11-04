"""Mansueto StopWatch (CloudFront) URL helpers: per-pattern parquet location and reachability.

The data itself (``trips_<pid>_full.parquet``, ``rt_to_pid.csv``) is described in ADR-001 / ADR-004;
the readers stay in ``cta.dlsd_run_quality`` / ``cta.michigan_ave_segment`` until the Mansueto
adapter spec. This module has no Bus Tracker dependency (specs/split-cta-api.md).
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request

BASE = "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch"
RT_TO_PID_URL = f"{BASE}/rt_to_pid.csv"

CLOUDFRONT_MIN_INTERVAL_SEC = 0.1

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
