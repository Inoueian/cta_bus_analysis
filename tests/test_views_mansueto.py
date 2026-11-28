"""Acceptance tests for specs/mansueto-adapter.md: cta.views.run_level_from_mansueto on the committed fixtures.

The fixtures (tests/fixtures/mansueto_*.parquet, manifest mansueto.manifest.json) are built by
scripts/build_mansueto_fixtures.py from the public CloudFront files; the getpatterns fixtures for the
three pids are shared with tests/test_views_archive.py. Tests skip, with the reason, if a fixture is missing.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cta import bustracker, mansueto, views

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MANIFEST = FIXTURES / "mansueto.manifest.json"
ONE_DAY = FIXTURES / "mansueto_2026-07-27_route3.parquet"
LAST30D = FIXTURES / "mansueto_6410_last30d.parquet"
GETPATTERNS_DIR = FIXTURES / "getpatterns"
KEPT_PIDS = Path(__file__).resolve().parent.parent / "notebooks" / "michigan_ave_kept_pids.json"
ONE_DAY_PIDS = ["18414", "18415"]
ONE_DAY_DATE = "2026-07-27"

needs_fixtures = pytest.mark.skipif(
    not (MANIFEST.is_file() and ONE_DAY.is_file() and LAST30D.is_file()),
    reason="Mansueto fixtures missing; run scripts/build_mansueto_fixtures.py",
)

MAX_RUN_COUNT_DEVIATION = 0.05  # spec acceptance: run count within 5% of the legacy n_trips


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(*args, **kwargs):
        raise AssertionError(f"network call attempted in tests: {args[:1]}")

    monkeypatch.setattr(mansueto, "http_head", _refuse)
    monkeypatch.setattr(mansueto, "http_range", _refuse)
    monkeypatch.setattr(mansueto, "download", _refuse)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


@pytest.fixture(scope="module")
def one_day_stops() -> pd.DataFrame:
    return bustracker.pattern_stops_table(ONE_DAY_PIDS, GETPATTERNS_DIR)


@pytest.fixture(scope="module")
def one_day(one_day_stops) -> tuple[pd.DataFrame, pd.DataFrame]:
    return views.run_level_from_mansueto_with_qa(ONE_DAY_PIDS, parquet_dir=FIXTURES, pattern_stops=one_day_stops)


@needs_fixtures
def test_run_level_one_day_schema_and_invariants(one_day):
    view, _ = one_day
    assert list(view.columns) == views.RUN_LEVEL_COLUMNS
    assert len(view) > 10_000
    assert (view["source"] == mansueto.SOURCE_MANSUETO).all()
    assert view["bracket_gap_s"].isna().all()
    assert view["bracket_gap_s"].dtype == "float64"
    assert not view.duplicated(["run_id", "stop_id"]).any()
    assert set(view["direction"]) == {"Northbound", "Southbound"}
    assert set(view["pattern_id"]) == set(ONE_DAY_PIDS)
    assert (view["route"] == "3").all()
    assert str(view["arrival_time"].dt.tz) == "UTC"
    assert view["stop_sequence_index"].dtype == "int64"
    assert (view["calendar_flag"] == "").all()  # 2026-07-27: no holiday; archive known_gaps never apply
    for col in ("run_id", "route", "direction", "pattern_id", "stop_id", "vehicle_id", "service_date"):
        assert all(isinstance(v, str) for v in view[col].head(3)), col


@needs_fixtures
def test_run_level_one_day_service_date(one_day):
    """Mansueto's own service day: rows of post-midnight continuations keep the previous date.

    The spec expected every row on 2026-07-27; the day cut (rows by bus_stop_time date, as specified)
    also catches the first stops after midnight of 5 of 230 runs whose trip id embeds 2026-07-26.
    """
    view, _ = one_day
    assert set(view["service_date"]) <= {"2026-07-26", ONE_DAY_DATE}
    assert (view["service_date"] == ONE_DAY_DATE).mean() >= 0.97
    prev = view[view["service_date"] == "2026-07-26"]
    assert prev["run_id"].str.endswith("2026-07-26").all()
    assert (prev["arrival_time"].dt.tz_convert(mansueto.MANSUETO_TZ).dt.hour < 4).all()
    assert view.loc[view["run_id"].str.endswith(ONE_DAY_DATE), "service_date"].eq(ONE_DAY_DATE).all()


@needs_fixtures
def test_run_level_matches_plain_wrapper(one_day, one_day_stops):
    view, _ = one_day
    plain = views.run_level_from_mansueto(ONE_DAY_PIDS, parquet_dir=FIXTURES, pattern_stops=one_day_stops)
    pd.testing.assert_frame_equal(plain, view)


@needs_fixtures
def test_run_level_window_filter(one_day_stops):
    view = views.run_level_from_mansueto(
        ONE_DAY_PIDS, parquet_dir=FIXTURES, pattern_stops=one_day_stops,
        start="2026-07-27 07:00", end="2026-07-27 09:00",
    )
    local = view["arrival_time"].dt.tz_convert(mansueto.MANSUETO_TZ)
    assert 0 < len(view)
    assert local.min() >= pd.Timestamp("2026-07-27 07:00", tz=mansueto.MANSUETO_TZ)
    assert local.max() < pd.Timestamp("2026-07-27 09:00", tz=mansueto.MANSUETO_TZ)


def test_hand_built_run_id_without_date_uses_earliest_arrival(one_day_stops=None):
    stops = pd.DataFrame(
        {"pid": ["p1", "p1"], "rtdir": ["Northbound"] * 2, "seq": [1, 2], "stpid": ["s1", "s2"],
         "stpnm": ["A", "B"], "lat": [41.8, 41.81], "lon": [-87.6] * 2, "pdist_ft": [0.0, 500.0]}
    )
    trips = pd.DataFrame(
        {
            "run_id": ["no-date-here"] * 2,
            "route": ["3"] * 2,
            "pid": ["p1"] * 2,
            "vehicle_id": ["v"] * 2,
            "stpid": ["s1", "s2"],
            "stop_sequence": [1, 2],
            "bus_stop_time": pd.to_datetime(["2026-07-27 23:50:00", "2026-07-28 00:10:00"]),
        }
    )
    view, qa = views.mansueto_view_from_trips(trips, stops)
    assert list(view.columns) == views.RUN_LEVEL_COLUMNS
    assert (view["service_date"] == "2026-07-27").all()
    assert view["stop_sequence_index"].tolist() == [0, 1]
    assert set(qa["pid"]) == {"p1"}


@needs_fixtures
def test_qa_table_per_pid_stage_sums_and_chains(one_day):
    _, qa = one_day
    assert list(qa.columns) == ["pid", "stage", "rows_in", "rows_out", "reason", "count"]
    assert set(qa["pid"]) == set(ONE_DAY_PIDS)
    for pid, part in qa.groupby("pid"):
        stages = list(dict.fromkeys(part["stage"]))
        assert stages == list(mansueto.STAGES), pid
        for stage, rows in part.groupby("stage", sort=False):
            assert rows["count"].sum() == rows["rows_in"].iloc[0] - rows["rows_out"].iloc[0], (pid, stage)
        outs = part.groupby("stage", sort=False)["rows_out"].first()
        ins = part.groupby("stage", sort=False)["rows_in"].first()
        for a, b in zip(stages, stages[1:]):
            assert outs[a] == ins[b], (pid, a, b)
    # the first stage sees every parquet row of the pid; the last stage's rows_out is the view's row count
    manifest = json.loads(MANIFEST.read_text())
    first = qa[qa["stage"] == mansueto.STAGES[0]].groupby("pid")["rows_in"].first()
    assert int(first.sum()) == manifest["files"][ONE_DAY.name]["rows"]


@needs_fixtures
def test_self_consistency_6410_against_legacy_median():
    from cta.michigan_ave_segment import trip_segment_minutes

    rec = next(r for r in json.loads(KEPT_PIDS.read_text())["pids"] if str(r["pid"]) == "6410")
    stops = bustracker.pattern_stops_table(["6410"], GETPATTERNS_DIR)
    view = views.run_level_from_mansueto(["6410"], parquet_dir=FIXTURES, pattern_stops=stops)
    assert (view["direction"] == rec["rtdir"]).all()
    legacy = views.legacy_trip_columns(view)
    minutes = trip_segment_minutes(legacy, rec["entry_stpid"], rec["exit_stpid"])
    assert len(minutes) >= mansueto.MIN_RUNS_FOR_RATIO
    ratio = float(np.median(minutes)) / float(rec["median_minutes"])
    assert abs(ratio - 1.0) <= mansueto.MAX_SELF_CONSISTENCY_DEVIATION, (ratio, len(minutes))
    assert abs(len(minutes) / rec["n_trips"] - 1.0) <= MAX_RUN_COUNT_DEVIATION, (len(minutes), rec["n_trips"])


@pytest.mark.skipif(
    mansueto.MANSUETO_DATA_EDGE < "2026-09-28",
    reason=f"deferred (ADR-007): Mansueto data edge {mansueto.MANSUETO_DATA_EDGE} precedes the archive start "
    "2026-09-28, so no service day exists in both sources; re-measure with cta.mansueto.data_edge",
)
def test_same_day_archive_comparison():
    # ADR-006: per-pattern corridor medians within MAX_MEDIAN_RATIO_DEVIATION on a day both sources cover.
    raise NotImplementedError("needs an overlapping day: build the fixture, then compare as tests/test_views_archive.py does")


# --- dense stop index on both adapters ------------------------------------------------------------


def test_pattern_stops_table_has_dense_stop_rank():
    pids = ["6410", "18414", "18415"]
    stops = bustracker.pattern_stops_table(pids, GETPATTERNS_DIR)
    assert "stop_rank" in stops.columns
    for pid, part in stops.groupby("pid"):
        part = part.sort_values("seq")
        assert part["stop_rank"].tolist() == list(range(len(part))), pid
        assert part["seq"].max() > len(part), pid  # seq counts waypoints; the rank does not


@needs_fixtures
def test_stop_sequence_index_increases_with_arrival_time_within_runs(one_day):
    view, _ = one_day
    v = view.sort_values(["run_id", "stop_sequence_index"])
    idx_step = v.groupby("run_id")["stop_sequence_index"].diff().dropna()
    assert (idx_step > 0).all()
    t_step = v.groupby("run_id")["arrival_time"].diff().dropna()
    assert (t_step >= pd.Timedelta(0)).all()
    assert view.groupby("pattern_id")["stop_sequence_index"].max().lt(130).all()


@needs_fixtures
def test_views_pass_source_to_calendar_flag(monkeypatch: pytest.MonkeyPatch):
    """specs/calendar-module.md: the Mansueto view flags rows on or after the parquet data edge."""
    from cta import calendar

    monkeypatch.setattr(mansueto, "MANSUETO_DATA_EDGE", "2026-06-01")  # before the 6410 fixture's 30-day window
    stops = bustracker.pattern_stops_table(["6410"], GETPATTERNS_DIR)
    view = views.run_level_from_mansueto(["6410"], parquet_dir=FIXTURES, pattern_stops=stops)
    assert len(view) > 0
    assert view["calendar_flag"].str.endswith(calendar.FLAG_COVERAGE_GAP).all()


# --- stop validity (specs/mansueto-stop-validity.md) ------------------------------------------------

from cta import stop_validity as sv  # noqa: E402

ROUTES_8_65_66_PIDS = Path(__file__).resolve().parent.parent / "notebooks" / "routes_8_65_66_pids.json"
FIXTURE_2025_10_14 = FIXTURES / "mansueto_2025-10-14_routes8_65_66.parquet"
FIXTURE_2025_12_02 = FIXTURES / "mansueto_2025-12-02_routes8_65_66.parquet"
KEY = ["route", "direction", "stop_id"]
# measured on the 2025-10-14 fixture (the spec's estimates were ~4,000 and ~270; both were high)
EXPECTED_BEFORE_VALID_FROM = {"8": 1338, "66": 853, "65": 0}
EXPECTED_NOT_SERVED_15341 = 118

needs_validity_fixtures = pytest.mark.skipif(
    not (FIXTURE_2025_10_14.is_file() and FIXTURE_2025_12_02.is_file()), reason="routes 8/65/66 fixtures missing; see specs/mansueto-stop-validity.md"
)


def _routes_8_65_66() -> tuple[list[str], dict[str, str], pd.DataFrame]:
    pids = json.loads(ROUTES_8_65_66_PIDS.read_text())["pids"]
    ok = [p for p in pids if p.get("getpatterns_ok")]
    ids = [str(p["pid"]) for p in ok]
    return ids, {str(p["pid"]): str(p["route"]) for p in ok}, bustracker.pattern_stops_table(ids, GETPATTERNS_DIR)


def _build(day: str, validity: pd.DataFrame | None):
    pids, route_of, stops = _routes_8_65_66()
    end = str((pd.Timestamp(day) + pd.Timedelta(days=1)).date())
    view, qa = views.run_level_from_mansueto_with_qa(pids, parquet_dir=FIXTURES, pattern_stops=stops, start=day, end=end, stop_validity=validity)
    return view, qa.assign(route=qa["pid"].map(route_of))


def _reason_total(qa: pd.DataFrame, reason: str, route: str | None = None) -> int:
    part = qa[qa["reason"] == reason]
    return int((part if route is None else part[part["route"] == route])["count"].sum())


def test_view_stop_validity_default_and_empty():
    loaded = sv.load_stop_validity()
    first = loaded[loaded["valid_from"].notna()].iloc[0]
    day = str((pd.Timestamp(first["valid_from"]) - pd.Timedelta(days=1)).date())
    stops = pd.DataFrame([{"pid": "p1", "rtdir": first["direction"], "seq": 1, "stpid": first["stop_id"], "stpnm": "S", "lat": 41.8, "lon": -87.6, "pdist_ft": 0.0}])
    trips = pd.DataFrame(
        {"run_id": [f"r-{day}"], "route": [first["route"]], "pid": ["p1"], "vehicle_id": ["v"], "stpid": [first["stop_id"]],
         "stop_sequence": [1], "bus_stop_time": pd.to_datetime([f"{day} 12:00:00"])}
    )
    for given in (None, loaded):
        view, qa = views.mansueto_view_from_trips(trips, stops, stop_validity=given)
        assert len(view) == 0
        assert _reason_total(qa, mansueto.REASON_STOP_BEFORE_VALID_FROM) == 1
    view, qa = views.mansueto_view_from_trips(trips, stops, stop_validity=loaded.iloc[0:0])
    assert len(view) == 1
    assert _reason_total(qa, mansueto.REASON_STOP_BEFORE_VALID_FROM) == 0


@needs_validity_fixtures
def test_mansueto_view_fixture_2025_10_14():
    base, base_qa = _build("2025-10-14", sv.load_stop_validity().iloc[0:0])
    view, qa = _build("2025-10-14", None)
    loaded = sv.load_stop_validity()
    # a key whose applied window opens after the day has no arrival, Wells & Chicago (6665 18803) among them
    after = loaded[loaded["valid_from"].fillna("0") > "2025-10-14"][KEY]
    assert len(after) == 16 and ("66", "Westbound", "18803") in set(map(tuple, after.to_numpy()))
    assert len(view.merge(after, on=KEY)) == 0 and len(base.merge(after, on=KEY)) > 0
    # 15341 on route 8 northbound (9376): not served then, dropped as stop_not_served
    northbound_15341 = lambda v: v[(v["route"] == "8") & (v["direction"] == "Northbound") & (v["stop_id"] == "15341")]  # noqa: E731
    assert len(northbound_15341(view)) == 0 and len(northbound_15341(base)) == EXPECTED_NOT_SERVED_15341
    assert _reason_total(qa, mansueto.REASON_STOP_NOT_SERVED) == EXPECTED_NOT_SERVED_15341
    # every other key keeps every arrival of the build with an empty table
    others = pd.concat([after, northbound_15341(base)[KEY].drop_duplicates()])
    def rest(v):
        merged = v.merge(others, on=KEY, how="left", indicator=True)
        return merged[merged["_merge"] == "left_only"].drop(columns="_merge").reset_index(drop=True)
    pd.testing.assert_frame_equal(rest(view), rest(base))
    for route, expected in EXPECTED_BEFORE_VALID_FROM.items():
        assert _reason_total(qa, mansueto.REASON_STOP_BEFORE_VALID_FROM, route) == expected, route
    assert _reason_total(qa, mansueto.REASON_RUN_UNOBSERVED) == 0
    assert len(base) - len(view) == sum(EXPECTED_BEFORE_VALID_FROM.values()) + EXPECTED_NOT_SERVED_15341
    # the QA table is additive per pid and stage
    for (_, stage), part in qa.groupby(["pid", "stage"], sort=False):
        assert part["count"].sum() == part["rows_in"].iloc[0] - part["rows_out"].iloc[0]


@needs_validity_fixtures
def test_mansueto_view_fixture_2025_12_02():
    base, _ = _build("2025-12-02", sv.load_stop_validity().iloc[0:0])
    view, qa = _build("2025-12-02", None)
    assert qa["pid"].nunique() == 24
    for reason in (mansueto.REASON_STOP_BEFORE_VALID_FROM, mansueto.REASON_RUN_UNOBSERVED, mansueto.REASON_STOP_NOT_SERVED):
        assert _reason_total(qa, reason) == 0, reason
    pd.testing.assert_frame_equal(view, base)
