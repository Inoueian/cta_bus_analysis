"""CTA Bus Tracker API and Mansueto CloudFront helpers for notebooks.

Daily Bus Tracker budget uses America/Chicago calendar dates (default cap 10,000
live requests/day per API key). Use ``getpatterns`` disk cache to avoid repeat calls.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

CHICAGO = ZoneInfo("America/Chicago")

BASE = "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch"
RT_TO_PID_URL = f"{BASE}/rt_to_pid.csv"
CTA_API_BASE = "http://www.ctabustracker.com/bustime/api/v3"

CTA_API_MIN_INTERVAL_SEC = 0.25
CTA_API_DAILY_WARN = 9_500
CTA_API_DAILY_MAX = 10_000
CLOUDFRONT_MIN_INTERVAL_SEC = 0.1

CTA_API_MAX_RETRIES = 3
CTA_API_RETRY_BASE_SEC = 2.0

LAST_CTA_REQUEST_URL: str | None = None

_last_api_call_monotonic: float = 0.0
_last_cloudfront_call_monotonic: float = 0.0


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def api_cache_dir() -> Path:
    return repo_root() / "data" / "cta_api_cache"


def load_dotenv(env_path: Path | None = None) -> None:
    path = env_path or repo_root() / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _chicago_today() -> str:
    return datetime.now(CHICAGO).date().isoformat()


def _request_log_path(cache_dir: Path | None = None) -> Path:
    root = cache_dir or api_cache_dir()
    return root / "request_log.json"


def daily_api_request_count(cache_dir: Path | None = None) -> int:
    path = _request_log_path(cache_dir)
    if not path.is_file():
        return 0
    data = json.loads(path.read_text())
    if data.get("date") != _chicago_today():
        return 0
    return int(data.get("count", 0))


def _load_request_log(cache_dir: Path) -> dict:
    path = _request_log_path(cache_dir)
    today = _chicago_today()
    if path.is_file():
        data = json.loads(path.read_text())
        if data.get("date") == today:
            return data
    return {"date": today, "count": 0}


def _save_request_log(cache_dir: Path, data: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    _request_log_path(cache_dir).write_text(json.dumps(data) + "\n")


def _check_daily_budget(cache_dir: Path, allow_over_budget: bool) -> None:
    data = _load_request_log(cache_dir)
    count = int(data["count"])
    if count >= CTA_API_DAILY_WARN and count < CTA_API_DAILY_MAX:
        print(
            f"Warning: CTA Bus Tracker API usage today is {count}/{CTA_API_DAILY_MAX} "
            f"(Chicago date {data['date']})."
        )
    if count >= CTA_API_DAILY_MAX and not allow_over_budget:
        raise RuntimeError(
            f"CTA Bus Tracker daily request cap ({CTA_API_DAILY_MAX}) reached for "
            f"{data['date']}. Use disk cache (use_cache=True), wait until tomorrow, "
            "or pass allow_over_budget=True if your key limit was raised."
        )


def _increment_daily_counter(cache_dir: Path) -> int:
    data = _load_request_log(cache_dir)
    data["count"] = int(data["count"]) + 1
    _save_request_log(cache_dir, data)
    return int(data["count"])


def _throttle_api() -> None:
    global _last_api_call_monotonic
    now = time.monotonic()
    elapsed = now - _last_api_call_monotonic
    if _last_api_call_monotonic > 0 and elapsed < CTA_API_MIN_INTERVAL_SEC:
        time.sleep(CTA_API_MIN_INTERVAL_SEC - elapsed)
    _last_api_call_monotonic = time.monotonic()


def _throttle_cloudfront() -> None:
    global _last_cloudfront_call_monotonic
    now = time.monotonic()
    elapsed = now - _last_cloudfront_call_monotonic
    if _last_cloudfront_call_monotonic > 0 and elapsed < CLOUDFRONT_MIN_INTERVAL_SEC:
        time.sleep(CLOUDFRONT_MIN_INTERVAL_SEC - elapsed)
    _last_cloudfront_call_monotonic = time.monotonic()


def _is_retryable_cta_message(msg: str) -> bool:
    lower = str(msg).lower()
    return any(token in lower for token in ("limit", "rate", "busy", "overload"))


def _is_retryable_http(code: int) -> bool:
    return code in (429, 503)


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


def cta_api_get(
    endpoint: str,
    *,
    allow_over_budget: bool = False,
    cache_dir: Path | None = None,
    **params: str,
) -> dict:
    """Call Bus Tracker API v3; enforces daily budget and min spacing."""
    global LAST_CTA_REQUEST_URL

    cache_root = cache_dir or api_cache_dir()
    _check_daily_budget(cache_root, allow_over_budget)

    api_key = os.environ.get("CTA_API_KEY")
    if not api_key:
        raise RuntimeError("Set CTA_API_KEY in .env at the repo root")

    params = {**params, "key": api_key, "format": "json"}
    query = urllib.parse.urlencode(params)
    url = f"{CTA_API_BASE}/{endpoint}?{query}"
    redacted = urllib.parse.urlencode({**params, "key": "***"})
    LAST_CTA_REQUEST_URL = f"{CTA_API_BASE}/{endpoint}?{redacted}"

    last_error: Exception | None = None
    for attempt in range(CTA_API_MAX_RETRIES):
        _throttle_api()
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = exc
            if _is_retryable_http(exc.code) and attempt < CTA_API_MAX_RETRIES - 1:
                time.sleep(CTA_API_RETRY_BASE_SEC * (2**attempt))
                continue
            raise
        root = payload.get("bustime-response", payload)
        if "error" in root:
            err = root["error"]
            if isinstance(err, list):
                err = err[0]
            msg = err.get("msg", err) if isinstance(err, dict) else err
            msg_s = str(msg)
            if _is_retryable_cta_message(msg_s) and attempt < CTA_API_MAX_RETRIES - 1:
                time.sleep(CTA_API_RETRY_BASE_SEC * (2**attempt))
                continue
            raise RuntimeError(f"CTA API {endpoint}: {msg}")
        _increment_daily_counter(cache_root)
        return root

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"CTA API {endpoint}: request failed after retries")


def ptr_to_stops_df(ptr: dict) -> pd.DataFrame:
    pts = ptr.get("pt", [])
    if isinstance(pts, dict):
        pts = [pts]
    rows = []
    for pt in pts:
        if pt.get("typ") != "S":
            continue
        rows.append(
            {
                "seq": int(pt["seq"]),
                "stpid": str(pt["stpid"]),
                "stpnm": pt.get("stpnm"),
                "lat": float(pt["lat"]),
                "lon": float(pt["lon"]),
                "pdist_ft": float(pt.get("pdist", 0)),
            }
        )
    return pd.DataFrame(rows).sort_values("seq").reset_index(drop=True)


def pattern_stops_from_ptr(ptr: dict) -> tuple[str, pd.DataFrame]:
    return ptr["rtdir"], ptr_to_stops_df(ptr)


def pattern_records(pid: str, **cta_kwargs) -> list[dict]:
    root = cta_api_get("getpatterns", pid=str(pid), **cta_kwargs)
    ptr = root.get("ptr", [])
    if isinstance(ptr, dict):
        ptr = [ptr]
    return ptr


def _getpatterns_cache_path(pid: str, cache_dir: Path) -> Path:
    return cache_dir / f"getpatterns_{pid}.json"


def _load_getpatterns_cache(pid: str, cache_dir: Path) -> dict | None:
    path = _getpatterns_cache_path(pid, cache_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def _save_getpatterns_cache(pid: str, cache_dir: Path, root: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    _getpatterns_cache_path(pid, cache_dir).write_text(json.dumps(root) + "\n")


def batch_pattern_stops(
    pids: list[str],
    *,
    use_cache: bool = True,
    cache_dir: Path | None = None,
    max_requests: int | None = None,
    allow_over_budget: bool = False,
    progress_every: int = 10,
) -> dict[str, tuple[str, pd.DataFrame]]:
    """Fetch pattern stops per PID; optional disk cache; one live API call per PID."""
    cache_root = cache_dir or api_cache_dir()
    result: dict[str, tuple[str, pd.DataFrame]] = {}
    skipped: list[str] = []
    live_calls = 0
    cached_hits = 0
    unique_pids = list(dict.fromkeys(str(p) for p in pids))
    cta_kw = {"allow_over_budget": allow_over_budget, "cache_dir": cache_root}

    for i, pid in enumerate(unique_pids, start=1):
        root: dict | None = None
        if use_cache:
            root = _load_getpatterns_cache(pid, cache_root)
            if root is not None:
                cached_hits += 1

        if root is None:
            if max_requests is not None and live_calls >= max_requests:
                raise RuntimeError(
                    f"max_requests={max_requests} reached in batch_pattern_stops "
                    f"(stopped before PID {pid})"
                )
            try:
                root = cta_api_get("getpatterns", pid=pid, **cta_kw)
            except RuntimeError:
                skipped.append(pid)
                continue
            live_calls += 1
            if use_cache:
                _save_getpatterns_cache(pid, cache_root, root)

        ptr = root.get("ptr", [])
        if isinstance(ptr, dict):
            ptr = [ptr]
        for p in ptr:
            result[str(p["pid"])] = pattern_stops_from_ptr(p)

        if progress_every > 0 and i % progress_every == 0:
            usage = daily_api_request_count(cache_root)
            print(
                f"  batch_pattern_stops: {i}/{len(unique_pids)} PIDs "
                f"(live={live_calls}, cached={cached_hits}, API today={usage}/{CTA_API_DAILY_MAX})"
            )

    if skipped:
        print(f"  Skipped {len(skipped)} PIDs not in live API: {skipped}")
    if unique_pids:
        usage = daily_api_request_count(cache_root)
        print(
            f"  batch_pattern_stops done: live={live_calls}, cached={cached_hits}, "
            f"API today={usage}/{CTA_API_DAILY_MAX}"
        )
    return result
