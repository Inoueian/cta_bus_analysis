"""scripts/route_run_level.py on the committed fixtures: the per-pid, per-year and per-day outputs equal one
call of the existing views, and the QA tables add up. No network; everything is written under tmp_path."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from cta import bustracker, calendar, mansueto, views
from scripts import route_run_level as rrl

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GETPATTERNS_DIR = FIXTURES / "getpatterns"
LAST30D = FIXTURES / "mansueto_6410_last30d.parquet"
PID = "6410"
RAW_DAY = "2026-10-22"
RAW_PIDS = [str(r["pid"]) for r in json.loads((rrl.REPO_ROOT / "notebooks" / "michigan_ave_kept_pids.json").read_text())["pids"]]
SORT = ["service_date", "pattern_id", "run_id", "stop_sequence_index"]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(*args, **kwargs):
        raise AssertionError(f"network call attempted in tests: {args[:1]}")

    for name in ("http_head", "http_range", "download"):
        monkeypatch.setattr(mansueto, name, _refuse)


@pytest.fixture()
def two_year_parquet(tmp_path: Path) -> Path:
    """The PID 6410 fixture with every other run moved back 200 days, so runs start in 2025 and in 2026."""
    df = pd.read_parquet(LAST30D)
    runs = sorted(df["unique_trip_vehicle_day"].unique())
    early = df["unique_trip_vehicle_day"].isin(runs[::2])
    df.loc[early, "bus_stop_time"] = df.loc[early, "bus_stop_time"] - pd.Timedelta(days=200)
    src = tmp_path / "src"
    src.mkdir()
    df.to_parquet(src / f"trips_{PID}_full.parquet", index=False)
    return src


def read_view(out_dir: Path, source: str) -> pd.DataFrame:
    files = sorted((out_dir / f"source={source}").rglob("*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True).sort_values(SORT).reset_index(drop=True)


def test_mansueto_pieces_equal_one_call(two_year_parquet: Path, tmp_path: Path):
    stops = bustracker.pattern_stops_table([PID], GETPATTERNS_DIR)
    whole, whole_qa = views.run_level_from_mansueto_with_qa([PID], parquet_dir=two_year_parquet, pattern_stops=stops)
    out = tmp_path / "out"
    qa = rrl.build_mansueto([PID], parquet_dir=two_year_parquet, pattern_stops=stops, out_dir=out)

    assert sorted(p.name for p in (out / "source=mansueto" / f"pid={PID}").iterdir()) == ["year=2025.parquet", "year=2026.parquet"]
    got = read_view(out, "mansueto")
    want = whole.sort_values(SORT).reset_index(drop=True)
    assert list(got.columns) == views.RUN_LEVEL_COLUMNS
    pd.testing.assert_frame_equal(got, want, check_dtype=False)

    assert list(qa.columns) == rrl.MANSUETO_QA_COLUMNS
    totals = rrl.stage_totals(qa, ["pid"], ["pid", "year"])
    one = rrl.stage_totals(whole_qa.assign(year="all"), ["pid"], ["pid", "year"])
    assert totals[["rows_in", "rows_out"]].equals(one[["rows_in", "rows_out"]])
    for reason in [c for c in one.columns if c not in ("rows_in", "rows_out")]:
        assert totals[reason].equals(one[reason])
    assert int(totals.loc[(PID, "order"), "rows_out"]) == len(got)


def test_split_keeps_runs_whole(two_year_parquet: Path, tmp_path: Path):
    pieces = rrl.split_by_run_year([two_year_parquet / f"trips_{PID}_full.parquet"], PID, tmp_path / "cut")
    frames = {y: pd.concat([pd.read_parquet(f) for f in d.glob("*.parquet")]) for y, d in pieces.items()}
    assert set(frames) == {"2025", "2026"}
    assert not set(frames["2025"]["unique_trip_vehicle_day"]) & set(frames["2026"]["unique_trip_vehicle_day"])
    assert sum(len(f) for f in frames.values()) == len(pd.read_parquet(LAST30D))
    assert "run_year" not in frames["2025"].columns and "first_time" not in frames["2025"].columns


def test_rows_by_month_and_pid_lists(two_year_parquet: Path):
    months = rrl.rows_by_month([PID, "999"], [PID], two_year_parquet)
    assert list(months.columns) == rrl.ROWS_BY_MONTH_COLUMNS
    assert int(months["rows"].sum()) == len(pd.read_parquet(LAST30D))
    assert months["in_view"].all() and set(months["pid"]) == {PID}

    pid_file = rrl.load_pid_file(rrl.DEFAULT_PIDS_FILE)
    assert len(rrl.pids_where(pid_file, "usable_mansueto")) == 24
    assert len(rrl.pids_where(pid_file, "getpatterns_ok")) == 24
    assert len(rrl.retired_parquet_pids(pid_file)) == 17
    assert rrl.today_geometry_first_day(pid_file) == {"6662": "2025-09-27", "6665": "2025-11-24", "9368": "2025-11-25", "9376": "2025-11-23"}


def test_detour_stop_arrivals(tmp_path: Path):
    """Two stops from day one, a third added on day 100; arrivals at it before today's geometry are counted."""
    days = pd.date_range("2025-01-01", periods=200).strftime("%Y-%m-%d")
    rows = [{"stop_id": s, "service_date": d} for d in days for s in ("a", "b")]
    rows += [{"stop_id": "c", "service_date": d} for d in days[100:]]
    target = tmp_path / "source=mansueto" / "pid=1"
    target.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(target / "year=2025.parquet", index=False)
    got = rrl.detour_stop_arrivals(tmp_path, {"1": days[150], "2": days[150]})
    assert list(got.columns) == rrl.DETOUR_COLUMNS
    assert got.to_dict("records") == [{
        "pid": "1", "first_day_today_geometry": days[150], "added_stops": 1,
        "arrivals_before_today_geometry": 50, "rows_in_period": 150, "share_pct": 33.33,
    }]


def test_raw_day_equals_one_call_and_missing_day(tmp_path: Path):
    stops = bustracker.pattern_stops_table(RAW_PIDS, GETPATTERNS_DIR)
    want, want_qa = views.run_level_from_mansueto_raw_with_qa([RAW_DAY], RAW_PIDS, csv_dir=FIXTURES, pattern_stops=stops)
    lengths_mi = rrl.pattern_lengths_mi(RAW_PIDS, GETPATTERNS_DIR)
    qa, lengths = rrl.build_mansueto_raw(
        [RAW_DAY, "2026-10-17"], RAW_PIDS, csv_dir=FIXTURES, pattern_stops=stops, out_dir=tmp_path, lengths_mi=lengths_mi
    )
    got = read_view(tmp_path, "mansueto_raw")
    pd.testing.assert_frame_equal(got, want.sort_values(SORT).reset_index(drop=True), check_dtype=False)

    ingested = qa[qa["day"] == RAW_DAY].reset_index(drop=True)
    pd.testing.assert_frame_equal(ingested, want_qa.reset_index(drop=True), check_dtype=False)
    missing = qa[qa["day"] == "2026-10-17"]
    assert missing[["stage", "reason"]].values.tolist() == [[calendar.COVERAGE_STAGE, calendar.REASON_MISSING_DAY_FILE]]

    assert list(lengths.columns) == rrl.LENGTH_COLUMNS
    assert set(lengths["pid"]) <= set(RAW_PIDS) and (lengths["day"] == RAW_DAY).all()
    assert (lengths["diff_mi"] == (lengths["max_pdist_mi"] - lengths["pattern_mi"]).round(3)).all()
    assert (lengths["over_pattern_length"] == (lengths["diff_mi"] > rrl.MAX_PATTERN_LENGTH_DIFF_MI)).all()
