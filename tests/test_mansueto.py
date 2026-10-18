"""Tests for cta_bus.mansueto."""

from __future__ import annotations

from cta_bus import mansueto


def test_parquet_url_basic():
    url = mansueto.parquet_url("6662")
    assert url.endswith("trips_6662_full.parquet")
    assert "cloudfront.net" in url
