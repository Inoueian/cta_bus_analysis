"""Acceptance tests for specs/michigan-segment-from-view.md: Michigan Ave corridor stops and segment speeds
from the run-level view (cta.views.legacy_trip_columns, cta.michigan_ave_segment.*_from_view / corridor_segment_speeds).

Fixtures: tests/fixtures/mansueto_6410_last30d.parquet, mansueto_2026-07-27_route3.parquet,
archive_2026-10-29_michigan.*, getpatterns/. No network, no writes to data/.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cta import archive, bustracker, mansueto, views
from cta import michigan_ave_segment as mas

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GETPATTERNS_DIR = FIXTURES / "getpatterns"
LAST30D = FIXTURES / "mansueto_6410_last30d.parquet"
ONE_DAY = FIXTURES / "mansueto_2026-07-27_route3.parquet"
DAY = "2026-10-29"
DAY_FILE = FIXTURES / f"archive_{DAY}_michigan.ndjson.gz"
DAY_INDEX = FIXTURES / f"archive_{DAY}_michigan.index.json"
KEPT_PIDS = Path(__file__).resolve().parent.parent / "notebooks" / "michigan_ave_kept_pids.json"
KEPT = [str(r["pid"]) for r in json.loads(KEPT_PIDS.read_text())["pids"]]

needs_mansueto = pytest.mark.skipif(
    not (LAST30D.is_file() and ONE_DAY.is_file()), reason="Mansueto fixtures missing; run scripts/build_mansueto_fixtures.py"
)
MISSING_PATTERNS = [p for p in KEPT if not (GETPATTERNS_DIR / f"getpatterns_{p}.json").is_file()]
needs_archive = pytest.mark.skipif(
    bool(MISSING_PATTERNS) or not (DAY_FILE.is_file() and DAY_INDEX.is_file()),
    reason="archive fixture day or getpatterns fixtures missing; run scripts/build_archive_fixtures.py --getpatterns",
)

SPEED_TOL_MPH = 0.05  # spec acceptance: 6410 hop median 4.28 +- 0.05
MAX_SPEED_TOL_MPH = 0.1  # spec acceptance: archive fixture day max speed 35.0 +- 0.1
FEET_PER_DEG_LAT = 364_567.0  # one degree of latitude, for hand-built meridian stops


# --- fixtures -------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(*args, **kwargs):
        raise AssertionError(f"network call attempted in tests: {args[:1]}")

    monkeypatch.setattr(archive, "run_curl", _refuse)
    monkeypatch.setattr(mansueto, "http_head", _refuse)
    monkeypatch.setattr(mansueto, "http_range", _refuse)
    monkeypatch.setattr(mansueto, "download", _refuse)


@pytest.fixture(scope="module")
def patterns_6410() -> pd.DataFrame:
    return bustracker.pattern_stops_table(["6410"], GETPATTERNS_DIR)


@pytest.fixture(scope="module")
def view_6410(patterns_6410) -> pd.DataFrame:
    return views.run_level_from_mansueto(["6410"], parquet_dir=FIXTURES, pattern_stops=patterns_6410)


@pytest.fixture(scope="module")
def stops_6410(view_6410):
    return mas.corridor_stops_from_view(view_6410)


@pytest.fixture(scope="module")
def speeds_6410(stops_6410, patterns_6410):
    return mas.corridor_segment_speeds(stops_6410[0], patterns_6410)


@pytest.fixture(scope="module")
def patterns_kept() -> pd.DataFrame:
    return bustracker.pattern_stops_table(KEPT, GETPATTERNS_DIR)


@pytest.fixture(scope="module")
def archive_view(patterns_kept) -> pd.DataFrame:
    index = json.loads(DAY_INDEX.read_text())
    con = archive.open_archive_db()
    try:
        archive.ingest_day(con, archive.day_file_meta(index, DAY), DAY_FILE)
        return views.run_level_from_archive([DAY], KEPT, con=con, index=index, pattern_stops=patterns_kept)
    finally:
        con.close()


@pytest.fixture(scope="module")
def archive_stops(archive_view):
    return mas.corridor_stops_from_view(archive_view)


@pytest.fixture(scope="module")
def archive_speeds(archive_stops, patterns_kept):
    return mas.corridor_segment_speeds(archive_stops[0], patterns_kept)


def _qa_total(qa: pd.DataFrame) -> tuple[int, int, int]:
    """(rows_in, rows_out, reasons) summed over the pids of a one-stage QA table."""
    first = qa.groupby(["pid", "stage"], sort=False)[["rows_in", "rows_out"]].first()
    return int(first["rows_in"].sum()), int(first["rows_out"].sum()), int(qa["count"].sum())


# --- legacy names and corridor minutes ------------------------------------------------------------


@needs_mansueto
def test_legacy_trip_columns_roundtrip():
    stops = bustracker.pattern_stops_table(["18414", "18415"], GETPATTERNS_DIR)
    view = views.run_level_from_mansueto(["18414", "18415"], parquet_dir=FIXTURES, pattern_stops=stops)
    legacy = views.legacy_trip_columns(view)
    renamed = {
        "run_id": "unique_trip_vehicle_day",
        "stop_id": "stpid",
        "arrival_time": "bus_stop_time",
        "pattern_id": "pid",
        "direction": "rtdir",
        "stop_sequence_index": "stop_sequence",
    }
    for old, new in renamed.items():
        assert new in legacy.columns and old not in legacy.columns
        pd.testing.assert_series_equal(legacy[new], view[old], check_names=False)
    for col in set(view.columns) - set(renamed):
        pd.testing.assert_series_equal(legacy[col], view[col])

    rec = next(r for r in json.loads(KEPT_PIDS.read_text())["pids"] if r["pid"] == "18414")
    assert (rec["entry_stpid"], rec["exit_stpid"]) == ("1580", "1126")
    got = mas.segment_minutes_from_view(view, rec)
    expected = mas.trip_segment_minutes(legacy[legacy["pid"] == "18414"], "1580", "1126")
    pd.testing.assert_series_equal(got, expected)
    assert len(got) > 0


# --- corridor stops -------------------------------------------------------------------------------


def _hand_sequences() -> dict[str, pd.DataFrame]:
    def seq(stpids: list[str], lats: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "seq_index": range(len(stpids)),
                "stpid": stpids,
                "lat": lats,
                "lon": [-87.62] * len(stpids),
                "stpnm": [f"stop {s}" for s in stpids],
            }
        )

    return {
        "Northbound": seq(["n1", "n2", "n3"], [41.870, 41.880, 41.890]),
        "Southbound": seq(["s1", "s2", "s3"], [41.890, 41.880, 41.870]),
    }


def _view_rows(run: str, pid: str, direction: str, stpids: list[str], minutes: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "run_id": run,
            "route": "99",
            "direction": direction,
            "pattern_id": pid,
            "stop_id": stpids,
            "stop_sequence_index": range(len(stpids)),
            "arrival_time": [pd.Timestamp("2026-10-29 13:00", tz="UTC") + pd.Timedelta(minutes=m) for m in minutes],
            "bracket_gap_s": [60.0] * len(stpids),
            "vehicle_id": "v1",
            "service_date": "2026-10-29",
            "calendar_flag": "",
            "source": "archive",
        }
    )


def test_corridor_stops_hand_built_qa():
    view = pd.concat(
        [
            _view_rows("r1", "111", "Northbound", ["n1", "n2", "s1"], [0, 5, 6]),  # s1 is outside the NB sequence
            _view_rows("r2", "222", "Westbound", ["s1", "s2"], [0, 5]),  # only SB stops -> Southbound
            _view_rows("r3", "333", "Northbound", ["n1", "n2"], [0, 5]),  # not kept
            _view_rows("r4", "444", "Westbound", ["x9"], [0]),  # kept, no corridor stop
        ],
        ignore_index=True,
    )
    kept = [
        {"pid": 111, "route": "99", "rtdir": "Northbound"},  # integer pid matches the string pattern_id
        {"pid": "222", "route": "99", "rtdir": "Westbound"},
        {"pid": "444", "route": "99", "rtdir": "Westbound"},
    ]
    stops, qa = mas.corridor_stops_from_view(view, sequences=_hand_sequences(), kept=kept)

    assert list(qa.columns) == views.MANSUETO_QA_COLUMNS
    assert set(qa["stage"]) == {"corridor"}
    rows_in, rows_out, reasons = _qa_total(qa)
    assert (rows_in, rows_out) == (8, 4)
    assert reasons == rows_in - rows_out
    assert qa.groupby("reason")["count"].sum().to_dict() == {
        "pattern_not_kept": 2,
        "no_direction_sequence": 1,
        "stop_not_in_sequence": 1,
    }
    for (_, stage), part in qa.groupby(["pid", "stage"]):
        assert part["count"].sum() == part["rows_in"].iloc[0] - part["rows_out"].iloc[0]

    assert len(stops) == 4
    assert set(stops["pid"]) == {"111", "222"}
    assert stops.loc[stops["pid"] == "222", "rtdir"].eq("Southbound").all()
    assert stops.loc[stops["pid"] == "111", "rtdir"].eq("Northbound").all()
    assert set(stops["stpid"]) == {"n1", "n2", "s1", "s2"}
    assert (~stops["interpolated"]).all()
    assert str(stops["bus_stop_time"].dt.tz) == "UTC"
    assert stops["bracket_gap_s"].dtype == "float64"
    assert stops["seq_index"].dtype == "int64"
    assert (stops["source"] == "archive").all()


@needs_mansueto
def test_corridor_stops_6410_matches_legacy(stops_6410, monkeypatch):
    stops, _ = stops_6410
    assert len(stops) == 990
    assert stops["unique_trip_vehicle_day"].nunique() == 110
    assert (stops["rtdir"] == "Northbound").all()
    assert (stops["source"] == "mansueto").all()
    assert mas.backwards_time_trip_keys(stops).empty

    def only_6410(pid, prefer_local=True, cache_variant="last30d"):
        return LAST30D if str(pid) == "6410" else Path("/nonexistent/none.parquet")

    monkeypatch.setattr(mas, "local_parquet_path", only_6410)
    legacy = mas.build_michigan_segment_view()
    legacy = legacy[~legacy["interpolated"]]

    def keyset(df: pd.DataFrame, chicago_naive: bool) -> set:
        t = df["bus_stop_time"]
        if chicago_naive:
            t = t.dt.tz_convert("America/Chicago").dt.tz_localize(None)
        return set(zip(df["unique_trip_vehicle_day"], df["stpid"], t))

    assert keyset(stops, True) == keyset(legacy, False)


@needs_archive
def test_corridor_stops_archive_fixture_day(archive_stops):
    stops, qa = archive_stops
    assert len(stops) == 15_216
    assert stops["unique_trip_vehicle_day"].nunique() == 1_500
    assert stops["pid"].nunique() == 44
    by_pid = stops.groupby("pid").agg(n=("stpid", "size"), d=("rtdir", "first"))
    assert (by_pid.loc["14130"].tolist()) == [352, "Southbound"]
    assert (by_pid.loc["14132"].tolist()) == [290, "Northbound"]
    assert int((stops.groupby("unique_trip_vehicle_day").size() == 1).sum()) == 4
    assert (stops["calendar_flag"] == "").all()
    rows_in, rows_out, reasons = _qa_total(qa)
    assert rows_out == len(stops)
    assert reasons == rows_in - rows_out

    back = mas.backwards_time_trip_keys(stops)
    assert len(back) == 2
    assert set(back["pid"]) == {"25899"}

    cache_status = pd.DataFrame({"pid": KEPT, "route": "x", "rtdir": "x", "cache_exists": True})
    report = mas.segment_view_report(stops, cache_status=cache_status)
    assert report["pids_missing_from_view"] == ["1054"]
    assert not any("null speed_mph" in i for i in report["issues"])


# --- segment speeds -------------------------------------------------------------------------------


def _hand_speed_inputs():
    lat0 = 41.870
    step = 1000.0 / FEET_PER_DEG_LAT  # stops 1000 ft apart along a meridian
    seq = pd.DataFrame(
        {
            "seq_index": range(4),
            "stpid": ["a", "b", "c", "d"],
            "lat": [lat0 + i * step for i in range(4)],
            "lon": [-87.62] * 4,
            "stpnm": ["A", "B", "C", "D"],
        }
    )
    pats = pd.DataFrame(
        {
            "pid": ["PX"] * 4 + ["PC"] * 4 + ["PD"] * 4,
            "stpid": ["a", "b", "c", "d"] * 3,
            "pdist_ft": [0.0, 1000.0, 2000.0, 3000.0] + [0.0, 1000.0, 500.0, 3000.0] + [0.0, 1000.0, 4000.0, 5000.0],
        }
    )

    def run(rid: str, pid: str, seq_idx: list[int], mins: list[float]) -> pd.DataFrame:
        t0 = pd.Timestamp("2026-10-29 13:00", tz="UTC")
        return pd.DataFrame(
            {
                "unique_trip_vehicle_day": rid,
                "stpid": [seq["stpid"][i] for i in seq_idx],
                "pid": pid,
                "route": "99",
                "rtdir": "Northbound",
                "seq_index": seq_idx,
                "lat": [seq["lat"][i] for i in seq_idx],
                "stpnm": [seq["stpnm"][i] for i in seq_idx],
                "bus_stop_time": [t0 + pd.Timedelta(minutes=m) for m in mins],
                "interpolated": False,
                "source": "archive",
                "service_date": "2026-10-29",
                "calendar_flag": "",
                "bracket_gap_s": 60.0,
            }
        )

    stops = pd.concat(
        [
            run("A", "PX", [0, 2, 3], [0, 10, 12]),
            run("B", "PX", [1, 2], [0, 0]),
            run("C", "PC", [1, 2], [0, 3]),
            run("D", "PD", [1, 2], [0, 3]),
        ],
        ignore_index=True,
    )
    return stops, pats, {"Northbound": seq}


def test_corridor_segment_speeds_hand_built():
    stops, pats, seqs = _hand_speed_inputs()
    assert abs(mas.straight_line_feet(41.87, -87.62, 41.87 + 1000.0 / FEET_PER_DEG_LAT, -87.62) - 1000) < 5

    out, qa = mas.corridor_segment_speeds(stops, pats, sequences=seqs)
    assert len(out) == 3
    out = out.sort_values("seg_index").reset_index(drop=True)
    assert out["seg_index"].tolist() == [0, 1, 2]
    fast = 2000 / 5280 / (10 / 60)
    slow = 1000 / 5280 / (2 / 60)
    assert out["speed_mph"].tolist() == pytest.approx([fast, fast, slow])
    assert out["hop_n_segments"].tolist() == [2, 2, 1]
    assert out["hop_from_stpid"].tolist() == ["a", "a", "c"]
    assert out["hop_to_stpid"].tolist() == ["c", "c", "d"]
    assert out["from_stpid"].tolist() == ["a", "b", "c"]
    assert out["to_stpid"].tolist() == ["b", "c", "d"]
    start = pd.Timestamp("2026-10-29 13:00", tz="UTC")
    assert out["bus_stop_time"].tolist() == [start, start, start + pd.Timedelta(minutes=10)]
    assert (out["speed_basis"] == mas.SPEED_BASIS_SEGMENT).all() and mas.SPEED_BASIS_SEGMENT == "segment"
    assert out["speed_mph"].notna().all()
    assert out["hop_n_segments"].dtype == "int64"

    assert list(qa.columns) == views.MANSUETO_QA_COLUMNS
    assert set(qa["stage"]) == {"hops"}
    rows_in, rows_out, reasons = _qa_total(qa)
    assert (rows_in, rows_out) == (5, 2)
    assert reasons == 3
    assert qa.groupby("reason")["count"].sum().to_dict() == {
        "nonpositive_hop_time": 1,
        "nonpositive_hop_distance": 1,
        "detour_hop": 1,
    }


def test_max_hop_detour_ratio_is_named_constant():
    assert mas.MAX_HOP_DETOUR_RATIO == 1.5


@needs_mansueto
def test_corridor_segment_speeds_6410(speeds_6410):
    out, qa = speeds_6410
    rows_in, rows_out, reasons = _qa_total(qa)
    assert (rows_in, rows_out, reasons) == (880, 880, 0)
    assert len(out) == 1_210
    assert out["unique_trip_vehicle_day"].nunique() == 110

    nb = mas.direction_stop_sequences()["Northbound"].set_index("stpid")["seq_index"]
    assert set(out["seg_index"]) == set(range(int(nb["1119"]), int(nb["1128"])))
    assert out.groupby("unique_trip_vehicle_day").size().eq(11).all()
    assert int((out["hop_n_segments"] > 1).sum()) == 550
    # stops skipped inside multi-segment hops are the ones pattern 6410 lacks
    multi = out.loc[out["hop_n_segments"] > 1].drop_duplicates(["hop_from_stpid", "hop_to_stpid"])
    skipped: set[str] = set()
    for h in multi.itertuples(index=False):
        skipped |= set(nb.index[(nb > nb[h.hop_from_stpid]) & (nb < nb[h.hop_to_stpid])])
    assert skipped == {"18791", "1104", "1126"}
    hops = out.drop_duplicates(["unique_trip_vehicle_day", "hop_from_stpid", "hop_to_stpid"])
    assert len(hops) == 880
    assert hops["speed_mph"].median() == pytest.approx(4.28, abs=SPEED_TOL_MPH)
    assert len(mas.filter_dlsd_leak_stops(out)) == len(out) - 220


@needs_archive
def test_corridor_segment_speeds_archive_fixture_day(archive_speeds):
    out, qa = archive_speeds
    rows_in, rows_out, reasons = _qa_total(qa)
    assert (rows_in, rows_out) == (13_716, 13_712)
    by_reason = qa.groupby("reason")["count"].sum().to_dict()
    assert by_reason == {"nonpositive_hop_distance": 2, "detour_hop": 2}
    assert reasons == 4
    assert qa.loc[qa["reason"].notna(), "pid"].eq("25899").all()

    assert len(out) == 15_919
    assert int((out["hop_n_segments"] > 1).sum()) == 3_718
    assert out["speed_mph"].notna().all()
    assert out["speed_mph"].max() == pytest.approx(35.0, abs=MAX_SPEED_TOL_MPH)
    assert len(mas.filter_dlsd_leak_stops(out)) == len(out) - 1_319
    assert {"14130", "14132"} <= set(out["pid"])

    seqs = mas.direction_segment_sequences()
    for direction, seg in seqs.items():
        rows = out[out["rtdir"] == direction]
        assert set(rows["seg_index"]) == set(seg["seg_index"]), direction
    only_multi = 0
    for direction, seg in seqs.items():
        rows = out[out["rtdir"] == direction]
        for s in seg["seg_index"]:
            part = rows[rows["seg_index"] == s]
            only_multi += int((part["hop_n_segments"] > 1).all())
    assert only_multi == 7
    assert (out["bracket_gap_s"] <= archive.MAX_BRACKET_GAP_S).all()


# --- helpers --------------------------------------------------------------------------------------


@needs_mansueto
def test_segment_helpers_on_view_outputs(speeds_6410):
    out, _ = speeds_6410
    stop_seqs = mas.direction_stop_sequences()
    assert "lon" in stop_seqs["Northbound"].columns

    seqs = mas.direction_segment_sequences()
    assert len(seqs["Northbound"]) == 22 and len(seqs["Southbound"]) == 18
    first = seqs["Northbound"].iloc[0]
    assert first["stpnm"] == "Michigan & Roosevelt to Michigan & 11th Street"
    assert first["seg_index"] == 0
    nb = stop_seqs["Northbound"]
    assert first["lat"] == pytest.approx((nb["lat"].iloc[0] + nb["lat"].iloc[1]) / 2)

    obs = mas.observed_speed_rows(out)
    assert len(obs) == 1_210
    chicago = out["bus_stop_time"].dt.tz_convert("America/Chicago")
    assert (obs["hour"].to_numpy() == chicago.dt.hour.to_numpy()).all()
    assert (obs["hour"].to_numpy() != out["bus_stop_time"].dt.hour.to_numpy()).all()
    weekday = mas.michigan_day_slice_mask(out, "weekday")
    assert weekday.equals(chicago.dt.dayofweek <= 3)

    stats = mas.corridor_segment_min_per_mile_stats(obs, seqs["Northbound"])
    assert len(stats) == 22
    assert {"seg_index", "from_stpid", "to_stpid", "lat", "stpnm", "median_mph", "median_min_mi"} <= set(stats.columns)
    have = stats.loc[stats["median_mph"].notna(), "seg_index"]
    nb_idx = nb.set_index("stpid")["seq_index"]
    assert have.tolist() == list(range(int(nb_idx["1119"]), int(nb_idx["1128"])))
    assert stats["lat"].tolist() == pytest.approx(seqs["Northbound"]["lat"].tolist())

    assert isinstance(mas.slowest_hours(obs, "all"), list)
