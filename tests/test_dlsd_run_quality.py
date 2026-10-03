"""Tests for notebooks/dlsd_run_quality.py hour masking helpers."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

NOTEBOOKS = Path(__file__).resolve().parent.parent / "notebooks"
if str(NOTEBOOKS) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKS))

from dlsd_run_quality import (  # noqa: E402
    ALL_DAY_DLSD_ROUTES,
    MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY,
    RUSH_ROUTES,
    day_slice_mask,
    hour_dlsd_stats,
    hour_run_counts,
    local_parquet_path,
    parquet_url,
    routes_for_day_slice,
    valid_rush_plot_cells,
)


def test_module_imports():
    import dlsd_run_quality  # noqa: F401


def test_local_parquet_path_cache_variant():
    assert parquet_url("6582") == local_parquet_path(
        "6582", prefer_local=False, cache_variant="last365d"
    )
    cached = (
        NOTEBOOKS.parent / "data" / "mansueto" / "trips_6582_last365d.parquet"
    )
    resolved = local_parquet_path(
        "6582", prefer_local=True, cache_variant="last365d"
    )
    if cached.is_file():
        assert resolved == cached
    else:
        assert resolved == parquet_url("6582")


def _sample_runs() -> pd.DataFrame:
    base = datetime(2026, 7, 7, 8, 0, 0)  # Tuesday
    rows = []
    for i in range(8):
        rows.append(
            {
                "route": "134" if i < 4 else "146",
                "rtdir": "Northbound",
                "hour": 8 if i < 2 else 9,
                "dlsd_minutes": 10.0 + i,
                "implied_dlsd_mph": 30.0 + i,
                "entry_time": pd.Timestamp(base) + pd.Timedelta(hours=i % 2),
                "day_of_week": 2,
                "analysis_ok": True,
            }
        )
    return pd.DataFrame(rows)


def test_day_slice_mask_weekday():
    df = _sample_runs()
    assert day_slice_mask(df, "weekday").all()
    assert not day_slice_mask(df, "weekend").any()


def test_hour_run_counts_groups():
    df = _sample_runs()
    counts = hour_run_counts(df, routes={"134"}, day_slice="weekday")
    assert (counts["route"] == "134").all()
    assert counts["n_runs"].sum() == 4


def test_hour_dlsd_stats_masks_rush_below_threshold():
    df = _sample_runs()
    sub = df[(df["route"] == "134") & (df["hour"] == 8)]
    stats = hour_dlsd_stats(
        sub,
        [8, 9],
        route="134",
        min_runs=5,
        apply_min_to_routes=RUSH_ROUTES,
    )
    row8 = stats.loc[stats["hour"] == 8].iloc[0]
    assert row8["n_runs"] == 2
    assert np.isnan(row8["median_min"])

    stats146 = hour_dlsd_stats(
        df[df["route"] == "146"],
        [8, 9],
        route="146",
        min_runs=5,
        apply_min_to_routes=RUSH_ROUTES,
    )
    assert stats146.loc[stats146["hour"] == 9, "median_min"].notna().all()


def _weekday_runs_at_hour(n: int, *, hour: int = 10, route: str = "134") -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "route": route,
                "rtdir": "Northbound",
                "hour": hour,
                "dlsd_minutes": 10.0,
                "implied_dlsd_mph": 30.0,
                "entry_time": pd.Timestamp("2026-07-07 08:00") + pd.Timedelta(minutes=i),
                "day_of_week": i % 4,
                "analysis_ok": True,
            }
        )
    return pd.DataFrame(rows)


def test_valid_rush_plot_cells_uses_weekday_only():
    eligible = _weekday_runs_at_hour(30, hour=10)
    ineligible = _weekday_runs_at_hour(29, hour=11)
    friday_only = pd.DataFrame(
        [
            {
                "route": "134",
                "rtdir": "Northbound",
                "hour": 12,
                "dlsd_minutes": 10.0,
                "implied_dlsd_mph": 30.0,
                "entry_time": pd.Timestamp("2026-07-11 08:00"),
                "day_of_week": 4,
                "analysis_ok": True,
            }
        ]
        * 50
    )
    df = pd.concat([eligible, ineligible, friday_only], ignore_index=True)
    valid = valid_rush_plot_cells(df, min_runs=30)
    assert len(valid) == 1
    assert valid.iloc[0]["hour"] == 10
    assert valid.iloc[0]["n_runs"] == 30


def test_hour_dlsd_stats_valid_cells_friday_not_refiltered_by_n_runs():
    valid = pd.DataFrame(
        [{"route": "134", "rtdir": "Northbound", "hour": 8, "n_runs": 40}]
    )
    friday = pd.DataFrame(
        [
            {
                "route": "134",
                "rtdir": "Northbound",
                "hour": 8,
                "dlsd_minutes": 10.0,
                "implied_dlsd_mph": 30.0,
                "entry_time": pd.Timestamp("2026-07-11 08:00"),
                "day_of_week": 4,
                "analysis_ok": True,
            },
            {
                "route": "134",
                "rtdir": "Northbound",
                "hour": 8,
                "dlsd_minutes": 11.0,
                "implied_dlsd_mph": 31.0,
                "entry_time": pd.Timestamp("2026-07-11 08:05"),
                "day_of_week": 4,
                "analysis_ok": True,
            },
            {
                "route": "134",
                "rtdir": "Northbound",
                "hour": 9,
                "dlsd_minutes": 12.0,
                "implied_dlsd_mph": 32.0,
                "entry_time": pd.Timestamp("2026-07-11 09:00"),
                "day_of_week": 4,
                "analysis_ok": True,
            },
        ]
    )
    sub = friday.loc[day_slice_mask(friday, "friday")]
    stats = hour_dlsd_stats(
        sub,
        [8, 9],
        route="134",
        rtdir="Northbound",
        valid_cells=valid,
    )
    row8 = stats.loc[stats["hour"] == 8].iloc[0]
    row9 = stats.loc[stats["hour"] == 9].iloc[0]
    assert row8["n_runs"] == 2
    assert not np.isnan(row8["median_min"])
    assert row9["n_runs"] == 1
    assert np.isnan(row9["median_min"])


def test_day_slice_mask_mon_fri():
    rows = []
    for dow in range(7):
        rows.append(
            {
                "route": "134",
                "rtdir": "Northbound",
                "hour": 8,
                "dlsd_minutes": 10.0,
                "implied_dlsd_mph": 30.0,
                "entry_time": pd.Timestamp("2026-07-07"),
                "day_of_week": dow,
                "analysis_ok": True,
            }
        )
    df = pd.DataFrame(rows)
    mon_fri = day_slice_mask(df, "mon_fri")
    assert mon_fri.sum() == 5
    assert mon_fri.iloc[:5].all()
    assert not mon_fri.iloc[5:].any()
    assert day_slice_mask(df, "weekday").le(mon_fri).all()


def test_routes_for_day_slice():
    assert routes_for_day_slice("weekend") == ALL_DAY_DLSD_ROUTES
    assert routes_for_day_slice("weekday") == RUSH_ROUTES | ALL_DAY_DLSD_ROUTES
    assert routes_for_day_slice("mon_fri") == RUSH_ROUTES | ALL_DAY_DLSD_ROUTES
    assert MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY == 30
