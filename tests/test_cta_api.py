"""Tests for notebooks/cta_api.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

NOTEBOOKS = Path(__file__).resolve().parent.parent / "notebooks"
if str(NOTEBOOKS) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKS))

import cta_api  # noqa: E402


def test_module_imports():
    import cta_api as _m  # noqa: F401


def test_parquet_url_basic():
    url = cta_api.parquet_url("6662")
    assert url.endswith("trips_6662_full.parquet")
    assert "cloudfront.net" in url


def test_ptr_to_stops_df_filters_waypoints_and_sorts():
    ptr = {
        "rtdir": "Northbound",
        "pt": [
            {"typ": "W", "seq": 1, "stpid": "1", "stpnm": "wp", "lat": 0, "lon": 0},
            {"typ": "S", "seq": 2, "stpid": "99", "stpnm": "Michigan & Roosevelt", "lat": 41.87, "lon": -87.62, "pdist": 100},
            {"typ": "S", "seq": 3, "stpid": "100", "stpnm": "Michigan & Ida B Wells", "lat": 41.88, "lon": -87.62, "pdist": 500},
        ],
    }
    df = cta_api.ptr_to_stops_df(ptr)
    assert len(df) == 2
    assert list(df["seq"]) == [2, 3]
    assert df.iloc[0]["stpid"] == "99"


def test_daily_counter_increments_and_resets_by_date(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    today = cta_api._chicago_today()
    cta_api._save_request_log(cache_dir, {"date": today, "count": 0})

    assert cta_api.daily_api_request_count(cache_dir) == 0
    cta_api._increment_daily_counter(cache_dir)
    assert cta_api.daily_api_request_count(cache_dir) == 1

    yesterday = "2000-01-01"
    cta_api._save_request_log(cache_dir, {"date": yesterday, "count": 999})
    assert cta_api.daily_api_request_count(cache_dir) == 0


def test_cta_api_get_throttles_between_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("CTA_API_KEY", "test-key")
    monkeypatch.setattr(cta_api, "_last_api_call_monotonic", 1000.0)

    times = iter([1000.0, 1000.0, 1000.1, 1000.1, 1000.1, 1000.1])
    monkeypatch.setattr(cta_api.time, "monotonic", lambda: next(times, 1000.1))
    sleeps: list[float] = []
    monkeypatch.setattr(cta_api.time, "sleep", lambda s: sleeps.append(s))

    payload = json.dumps({"bustime-response": {"ptr": []}}).encode()

    def fake_urlopen(req, timeout=60):
        class Resp:
            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return Resp()

    monkeypatch.setattr(cta_api.urllib.request, "urlopen", fake_urlopen)

    cta_api.cta_api_get("getpatterns", pid="1", cache_dir=cache_dir)
    cta_api.cta_api_get("getpatterns", pid="2", cache_dir=cache_dir)

    assert sleeps, "expected throttle sleep before second live API call"
    assert sleeps[0] >= cta_api.CTA_API_MIN_INTERVAL_SEC - 0.1


def test_batch_pattern_stops_uses_cache_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache_dir = tmp_path / "cache"
    pid = "4509"
    root = {"ptr": [{"pid": pid, "rtdir": "Northbound", "pt": [{"typ": "S", "seq": 1, "stpid": "1", "stpnm": "A", "lat": 0, "lon": 0, "pdist": 0}]}]}
    cta_api._save_getpatterns_cache(pid, cache_dir, root)

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("urlopen should not run on cache hit")

    monkeypatch.setattr(cta_api.urllib.request, "urlopen", fail_urlopen)

    result = cta_api.batch_pattern_stops([pid], use_cache=True, cache_dir=cache_dir, progress_every=0)
    assert pid in result
    assert result[pid][0] == "Northbound"
    assert len(result[pid][1]) == 1
