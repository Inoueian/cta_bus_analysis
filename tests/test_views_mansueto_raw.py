"""Acceptance tests for specs/mansueto-raw-adapter.md: cta.views.run_level_from_mansueto_raw and its QA table."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from cta import archive, bustracker, mansueto, mansueto_raw, views
from tests.test_mansueto_raw import csv_row, stops_table, write_csv

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DAY = "2026-10-22"
GETPATTERNS_DIR = FIXTURES / "getpatterns"
KEPT = [str(r["pid"]) for r in json.loads((Path(__file__).resolve().parent.parent / "notebooks" / "michigan_ave_kept_pids.json").read_text())["pids"]]

# Measured on the committed fixture; the spec's estimates are in brackets.
EXPECTED_VIEW_ROWS = 97_663  # ~97,663
EXPECTED_VIEW_RUNS = 1_532  # ~1,532
EXPECTED_PAIRS_IN = 21_834  # ~21,834
EXPECTED_PAIR_REASONS = {  # ~85, ~30, ~23
    archive.REASON_GAP: 85, archive.REASON_BACKWARD: 30, archive.REASON_GEOMETRY: 23,
}
EXPECTED_LATER_CROSSING = 5  # ~5
EXPECTED_MEDIAN_GAP_S = 300.0  # estimate in the spec


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(url, *args, **kwargs):
        raise AssertionError(f"network call attempted in tests: {url}")

    monkeypatch.setattr(mansueto, "_request", _refuse)


@pytest.fixture(scope="module")
def view_and_qa():
    stops = bustracker.pattern_stops_table(KEPT, GETPATTERNS_DIR)
    return views.run_level_from_mansueto_raw_with_qa([DAY], KEPT, csv_dir=FIXTURES, pattern_stops=stops)


def test_run_level_view(view_and_qa):
    view, _ = view_and_qa
    assert list(view.columns) == views.RUN_LEVEL_COLUMNS
    assert (view["source"] == "mansueto_raw").all()
    assert len(view) == EXPECTED_VIEW_ROWS
    assert view["run_id"].nunique() == EXPECTED_VIEW_RUNS
    assert not view.duplicated(["run_id", "stop_id"]).any()
    assert view["bracket_gap_s"].notna().all()
    assert view["bracket_gap_s"].max() <= mansueto_raw.MAX_RAW_BRACKET_GAP_S
    assert view["bracket_gap_s"].median() == EXPECTED_MEDIAN_GAP_S
    ordered = view.sort_values(["run_id", "arrival_time", "stop_sequence_index"])
    assert (ordered.groupby("run_id")["stop_sequence_index"].diff().dropna() > 0).all()
    assert (view["service_date"] == DAY).all()
    assert (view["calendar_flag"] == "").all()
    assert str(view["arrival_time"].dt.tz) == "UTC"
    for c in ("run_id", "route", "pattern_id", "stop_id", "vehicle_id"):
        assert view[c].map(type).eq(str).all(), c
    assert view.equals(views.run_level_from_mansueto_raw([DAY], KEPT, csv_dir=FIXTURES, pattern_stops=bustracker.pattern_stops_table(KEPT, GETPATTERNS_DIR)))


def test_qa_table(view_and_qa):
    _, qa = view_and_qa
    assert list(qa.columns) == ["day"] + archive.QA_COLUMNS
    assert (qa["day"] == DAY).all()
    assert list(dict.fromkeys(qa["stage"])) == list(mansueto_raw.STAGES)
    for stage, g in qa.groupby("stage"):
        assert g["rows_in"].nunique() == 1 and g["rows_out"].nunique() == 1
        assert g["count"].sum() == g["rows_in"].iloc[0] - g["rows_out"].iloc[0], stage
    stage = {s: g for s, g in qa.groupby("stage")}
    fixes_out = stage["clean"]["rows_out"].iloc[0]
    pairs_in = stage["pairs"]["rows_in"].iloc[0]
    assert pairs_in == EXPECTED_PAIRS_IN
    p = stage["pairs"]
    assert dict(zip(p["reason"], p["count"])) == EXPECTED_PAIR_REASONS
    i = stage["impute"]
    assert dict(zip(i["reason"], i["count"])) == {archive.REASON_LATER_CROSSING: EXPECTED_LATER_CROSSING}
    assert stage["read"]["rows_in"].iloc[0] == stage["read"]["rows_out"].iloc[0]
    assert fixes_out > pairs_in  # pairs = fixes - runs


def test_two_days_no_shared_runs(tmp_path: Path):
    d1, d2 = "2026-09-15", "2026-09-16"
    write_csv(tmp_path / f"{d1}.csv", [
        csv_row("1", "20260915 08:00", 0, d1), csv_row("1", "20260915 08:05", 3000, d1),
        csv_row("1", "20260915 08:10", 6000, d1),
    ])
    write_csv(tmp_path / f"{d2}.csv", [
        csv_row("1", "20260915 23:55", 3000, d1), csv_row("1", "20260915 23:58", 6000, d1),  # stale fixes of day 1's trip
        csv_row("2", "20260916 08:00", 0, d2, trip="88"), csv_row("2", "20260916 08:05", 3000, d2, trip="88"),
        csv_row("2", "20260916 08:10", 6000, d2, trip="88"),
    ])
    view, qa = views.run_level_from_mansueto_raw_with_qa([d1, d2], ["9001"], csv_dir=tmp_path, pattern_stops=stops_table())
    clean2 = qa[(qa["day"] == d2) & (qa["stage"] == "clean")]
    assert dict(zip(clean2["reason"], clean2["count"])) == {mansueto_raw.REASON_OTHER_DATA_DATE: 2}
    assert not view.duplicated(["run_id", "stop_id"]).any()
    assert len(view) == 4
    for run_id, g in view.groupby("run_id"):
        assert g["service_date"].nunique() == 1
        assert run_id.endswith(g["service_date"].iloc[0])
    assert set(view["service_date"]) == {d1, d2}
    assert (view[view["vehicle_id"] == "1"]["arrival_time"] < pd.Timestamp("2026-09-15 14:00", tz="UTC")).all()


def test_views_pass_source_to_calendar_flag(monkeypatch: pytest.MonkeyPatch):
    """specs/calendar-module.md: the raw view flags rows on a declared-missing day."""
    from cta import calendar

    monkeypatch.setattr(calendar, "MANSUETO_RAW_MISSING_DAYS", calendar.MANSUETO_RAW_MISSING_DAYS + (DAY,))
    pids = ["6414", "18414"]
    stops = bustracker.pattern_stops_table(pids, GETPATTERNS_DIR)
    view = views.run_level_from_mansueto_raw([DAY], pids, csv_dir=FIXTURES, pattern_stops=stops)
    assert len(view) > 0
    assert view["calendar_flag"].str.endswith(calendar.FLAG_COVERAGE_GAP).all()
