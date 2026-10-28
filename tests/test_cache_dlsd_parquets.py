"""Tests for scripts.cache_dlsd_parquets."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd


def test_module_imports():
    import scripts.cache_dlsd_parquets  # noqa: F401


def test_load_michigan_pids_from_snapshot():
    from scripts.cache_dlsd_parquets import load_michigan_pids

    rt_df = pd.DataFrame(
        {
            "rt": ["1", "1", "10", "66"],
            "pid": [100, 101, 999, 6662],
        }
    )
    with patch("scripts.cache_dlsd_parquets.pd.read_csv", return_value=rt_df):
        with patch(
            "scripts.cache_dlsd_parquets.json.loads",
            return_value={"candidate_routes": ["1", "10"]},
        ):
            pids = load_michigan_pids()
    assert pids == ["100", "101", "999"]


def test_parquet_url_basic():
    from scripts.cache_dlsd_parquets import parquet_url

    assert parquet_url("1234").endswith("trips_1234_full.parquet")
