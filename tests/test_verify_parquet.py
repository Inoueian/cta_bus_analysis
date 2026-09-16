"""Unit tests for scripts.verify_parquet (no network)."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest


@pytest.fixture
def mock_rt_csv():
    rt_df = pd.DataFrame({"rt": [66, 77], "pid": [6662, 1000]})
    with patch("scripts.verify_parquet.pd.read_csv", return_value=rt_df):
        yield


def _minimal_verify_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unique_trip_vehicle_day": ["t1", "t1", "t2", "t2"],
            "stpid": ["100", "101", "100", "101"],
            "bus_stop_time": pd.to_datetime(
                [
                    "2024-01-01 08:00:00",
                    "2024-01-01 08:05:00",
                    "2024-01-02 08:00:00",
                    "2024-01-02 08:05:00",
                ]
            ),
            "stop_sequence": [1, 2, 1, 2],
            "rt": ["66", "66", "66", "66"],
            "pid": ["6662", "6662", "6662", "6662"],
            "seg_combined": [1.0, 2.0, 1.0, 2.0],
            "typ": ["S", "S", "S", "S"],
            "speed_mph": [10.0, 10.0, 10.0, 10.0],
            "vid": ["1", "1", "2", "2"],
            "p_stp_id": ["6662-100", "6662-101", "6662-100", "6662-101"],
        }
    )


def test_module_imports():
    from scripts import verify_parquet  # noqa: F401


def test_parquet_url_basic():
    from scripts.verify_parquet import parquet_url

    url = parquet_url("1234")
    assert url.endswith("trips_1234_full.parquet")
    assert "d2v7z51jmtm0iq.cloudfront.net" in url


def test_pids_for_route_found(mock_rt_csv):
    from scripts.verify_parquet import pids_for_route

    result = pids_for_route("66")
    assert "6662" in result


def test_pids_for_route_not_found(mock_rt_csv):
    from scripts.verify_parquet import pids_for_route

    with pytest.raises(SystemExit):
        pids_for_route("9999")


def test_verify_passes_clean_df(capsys):
    from scripts.verify_parquet import verify

    verify(_minimal_verify_df(), pid="6662", route="66")
    captured = capsys.readouterr()
    assert "OK: checklist passed" in captured.out


def test_verify_exits_on_missing_trip_column():
    from scripts.verify_parquet import verify

    df = pd.DataFrame({"wrong_col": [1]})
    with pytest.raises(SystemExit):
        verify(df, pid="6662", route="66")


def test_verify_exits_on_missing_required_columns():
    from scripts.verify_parquet import verify

    df = pd.DataFrame(
        {
            "unique_trip_vehicle_day": ["t1"],
            "stpid": ["100"],
            "bus_stop_time": pd.to_datetime(["2024-01-01"]),
        }
    )
    with pytest.raises(SystemExit):
        verify(df, pid="6662", route="66")
