"""Tests for cta/dlsd_run_quality.py hour masking helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

from cta.dlsd_run_quality import (
    ALL_DAY_DLSD_ROUTES,
    dlsd_runs_from_view,
    load_dlsd_boundaries,
    MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY,
    RUSH_ROUTES,
    day_slice_mask,
    hour_dlsd_stats,
    hour_run_counts,
    local_parquet_path,
    parquet_url,
    routes_for_day_slice,
    valid_rush_plot_cells,
    DEFAULT_PLOT_HOURS,
)


def test_module_imports():
    from cta import dlsd_run_quality  # noqa: F401


def test_local_parquet_path_cache_variant():
    assert parquet_url("6582") == local_parquet_path(
        "6582", prefer_local=False, cache_variant="last365d"
    )
    cached = (
        REPO_ROOT / "data" / "mansueto" / "trips_6582_last365d.parquet"
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


# ---- specs/dlsd-runs-from-view.md acceptance tests ----------------------------------------------

import json

from cta import archive, bustracker, dlsd_run_quality, mansueto, views

FIXTURES = REPO_ROOT / "tests" / "fixtures"
GETPATTERNS_DIR = FIXTURES / "getpatterns"
DAY = "2026-10-29"
DAY_FILE = FIXTURES / f"archive_{DAY}_michigan.ndjson.gz"
DAY_INDEX = FIXTURES / f"archive_{DAY}_michigan.index.json"
LAST30D = FIXTURES / "mansueto_6410_last30d.parquet"
KEPT_PIDS = REPO_ROOT / "notebooks" / "michigan_ave_kept_pids.json"
KEPT = [str(r["pid"]) for r in json.loads(KEPT_PIDS.read_text())["pids"]]
needs_archive_fixture = pytest.mark.skipif(
    not (DAY_FILE.is_file() and DAY_INDEX.is_file())
    or any(not (GETPATTERNS_DIR / f"getpatterns_{p}.json").is_file() for p in KEPT),
    reason="archive fixture day or getpatterns fixtures missing; run scripts/build_archive_fixtures.py",
)

HAND_BOUNDARIES = {
    "p1": {"route": "1", "rtdir": "Northbound", "entry_stpid": "e", "exit_stpid": "x", "hop_feet": 5280.0},
    "p2": {"route": "2", "rtdir": "Southbound", "entry_stpid": "e2", "exit_stpid": "x2", "hop_feet": 5280.0},
}


def _hand_view() -> pd.DataFrame:
    def row(run, stop, idx, t, gap=60.0, source="archive"):
        return {
            "run_id": run, "route": "1", "direction": "Northbound", "pattern_id": "p1", "stop_id": stop,
            "stop_sequence_index": idx, "arrival_time": pd.Timestamp(t, tz="UTC"), "bracket_gap_s": gap,
            "vehicle_id": "v", "service_date": "2026-07-07", "calendar_flag": "", "source": source,
        }

    rows = [
        row("A", "s4", 4, "2026-07-07 13:00"), row("A", "e", 5, "2026-07-07 13:10"),
        row("A", "x", 6, "2026-07-07 13:20"), row("A", "s7", 7, "2026-07-07 13:30"),
        row("B", "s4", 4, "2026-07-07 13:00"), row("B", "e", 5, "2026-07-07 13:10"),
        row("C", "e", 5, "2026-07-07 13:10"), row("C", "x", 7, "2026-07-07 13:25"),
        row("D", "e", 5, "2026-07-07 13:10", gap=np.nan, source="mansueto"),
        row("D", "x", 6, "2026-07-07 13:20", gap=np.nan, source="mansueto"),
    ]
    return pd.DataFrame(rows)[views.RUN_LEVEL_COLUMNS]


def test_dlsd_runs_from_view_hand_built():
    runs, _ = dlsd_runs_from_view(_hand_view(), HAND_BOUNDARIES)
    assert sorted(runs["run_id"]) == ["A", "C", "D"]  # B lacks x
    r = runs.set_index("run_id")
    a = r.loc["A"]
    assert a["dlsd_minutes"] == 10.0
    assert a["hour"] == 8 and a["day_of_week"] == 1 and bool(a["is_weekday"])
    assert a["bracket_minutes"] == 30.0
    assert bool(a["analysis_ok"])
    assert a["hop_feet"] == 5280.0
    assert str(runs["entry_time"].dt.tz) == "UTC"
    assert not bool(r.loc["C", "ok_consecutive"]) and not bool(r.loc["C", "analysis_ok"])
    assert np.isnan(r.loc["D", "entry_bracket_gap_s"]) and bool(r.loc["D", "analysis_ok"])
    assert r.loc["D", "source"] == "mansueto"
    assert runs["entry_sequence"].dtype == "int64"


def test_dlsd_runs_from_view_qa_sums():
    _, qa = dlsd_runs_from_view(_hand_view(), HAND_BOUNDARIES)
    assert list(qa.columns) == views.MANSUETO_QA_COLUMNS
    p1 = qa[qa["pid"] == "p1"]
    assert set(p1["stage"]) == {"endpoints"}
    assert p1["rows_in"].iloc[0] == 4 and p1["rows_out"].iloc[0] == 3
    assert dict(zip(p1["reason"], p1["count"])) == {"missing_exit_stop": 1}
    assert p1["count"].sum() == p1["rows_in"].iloc[0] - p1["rows_out"].iloc[0]
    p2 = qa[qa["pid"] == "p2"]
    assert (p2["rows_in"] == 0).all() and (p2["rows_out"] == 0).all() and (p2["count"] == 0).all()


@pytest.fixture(scope="module")
def fixture_day_runs():
    index = json.loads(DAY_INDEX.read_text())
    con = archive.open_archive_db()
    try:
        archive.ingest_day(con, archive.day_file_meta(index, DAY), DAY_FILE)
        boundaries = load_dlsd_boundaries()
        pids = list(boundaries)
        stops = bustracker.pattern_stops_table(
            [p for p in pids if (GETPATTERNS_DIR / f"getpatterns_{p}.json").is_file()], GETPATTERNS_DIR
        )
        present = sorted(set(stops["pid"].astype(str)))
        view = views.run_level_from_archive([DAY], present, con=con, index=index, pattern_stops=stops)
    finally:
        con.close()
    runs, qa = dlsd_runs_from_view(view, boundaries)
    return runs, qa, boundaries


@needs_archive_fixture
def test_dlsd_runs_from_view_archive_fixture_day(fixture_day_runs):
    runs, qa, boundaries = fixture_day_runs
    assert len(runs) == 445
    assert runs.groupby("route").size().to_dict() == {"143": 32, "146": 203, "147": 168, "148": 42}
    assert runs["pid"].nunique() == 22
    assert runs["analysis_ok"].all() and runs["ok_consecutive"].all()
    assert (runs["entry_bracket_gap_s"] <= archive.MAX_BRACKET_GAP_S).all()
    assert (runs["source"] == "archive").all() and (runs["calendar_flag"] == "").all()
    med = runs.groupby("pid")["dlsd_minutes"].median()
    assert med["4524"] == pytest.approx(9.99, abs=0.05)
    assert med["6582"] == pytest.approx(6.86, abs=0.05)
    assert qa["pid"].nunique() == 29 == len(boundaries)
    zero = qa[qa["rows_in"] == 0]["pid"].unique()
    assert len(zero) == 7


@needs_archive_fixture
def test_dlsd_runs_from_view_legacy_helpers_run(fixture_day_runs):
    runs, _, _ = fixture_day_runs
    cells = valid_rush_plot_cells(runs)
    assert isinstance(cells, pd.DataFrame)
    counts = hour_run_counts(runs, day_slice="weekday")
    routes = {"146", "147", "143", "148"}
    expected = runs[runs["analysis_ok"] & runs["day_of_week"].le(3) & runs["route"].isin(routes)]
    assert hour_run_counts(runs, routes=routes, day_slice="weekday")["n_runs"].sum() == len(expected)
    assert counts["n_runs"].sum() >= len(expected)
    sub = runs[(runs["route"] == "146") & (runs["rtdir"] == "Northbound")]
    stats = hour_dlsd_stats(sub, DEFAULT_PLOT_HOURS, route="146", rtdir="Northbound")
    assert len(stats) == len(DEFAULT_PLOT_HOURS)


@needs_archive_fixture
def test_dlsd_hours_are_chicago(fixture_day_runs):
    runs, _, _ = fixture_day_runs
    local = runs["entry_time"].dt.tz_convert("America/Chicago").dt.hour
    assert (runs["hour"] == local).all()
    assert (runs["hour"] != runs["entry_time"].dt.hour).all()


@pytest.mark.skipif(not LAST30D.is_file(), reason="Mansueto 6410 fixture missing; run scripts/build_mansueto_fixtures.py")
def test_dlsd_runs_from_view_matches_legacy_on_mansueto_cut(monkeypatch):
    boundaries = {"6410": {"route": "151", "rtdir": "Northbound", "entry_stpid": "1119", "exit_stpid": "1128", "hop_feet": 5000}}
    monkeypatch.setattr(dlsd_run_quality, "local_parquet_path", lambda *a, **k: LAST30D)
    legacy = dlsd_run_quality.build_dlsd_runs(boundaries)
    stops = bustracker.pattern_stops_table(["6410"], GETPATTERNS_DIR)
    view = views.run_level_from_mansueto(["6410"], parquet_dir=FIXTURES, pattern_stops=stops)
    new, _ = dlsd_runs_from_view(view, boundaries)
    assert len(legacy) == len(new) == 110
    m = legacy.merge(new, left_on="unique_trip_vehicle_day", right_on="run_id", suffixes=("_l", "_n"))
    assert len(m) == 110
    assert np.allclose(m["dlsd_minutes_l"], m["dlsd_minutes_n"], atol=1e-6)
    assert m["pre_dlsd_time_l"].notna().sum() == m["pre_dlsd_time_n"].notna().sum() == 110
    # spec: count unknown, measured 2026-11-07 on this fixture: 110 on both sides
    assert m["post_dlsd_time_l"].notna().sum() == m["post_dlsd_time_n"].notna().sum() == 110
    assert (m["hour_l"] == m["hour_n"]).all()
