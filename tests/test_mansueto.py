"""Tests for cta/mansueto.py (specs/split-cta-api.md)."""

from __future__ import annotations

from cta import mansueto


def test_parquet_url_basic():
    url = mansueto.parquet_url("6662")
    assert url.endswith("trips_6662_full.parquet")
    assert "cloudfront.net" in url


def test_rt_to_pid_url_under_base():
    assert mansueto.RT_TO_PID_URL == f"{mansueto.BASE}/rt_to_pid.csv"
    assert mansueto.parquet_url("6662").startswith(mansueto.BASE + "/processed_by_pid/")
