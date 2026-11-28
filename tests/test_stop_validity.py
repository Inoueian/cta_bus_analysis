"""specs/stop-validity-measurement.md: windows measured per stop against raw pings. Hand-built inputs except the snapshot."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cta import geo, stop_validity as sv
from scripts import route_run_level as rrl

LAT0, LON0 = 41.90, -87.65
STOP_GAP_DEG = 0.01  # about 3,648 ft between stops: a stop's only near ping is its own
NEAR_DEG = 0.0005  # a served stop's ping: about 182.4 ft north of it (0.001 degree of latitude is about 364.8 ft)
MAX_FT = 500.0  # threshold passed in; served stops sit at 182 ft, unserved ones beyond 3,400 ft, nothing in the band
CHANGES = [("2025-08-17", "1"), ("2025-11-25", "1")]
SAMPLE_DAYS = ("2025-07-15", "2025-10-14", "2026-09-15")  # one inside each of the three periods


def _pid_file(changes=CHANGES) -> dict:
    return {"geometry_changes": [{"pid": pid, "first_day_new": day} for day, pid in changes]}


def _stop_lat(i: int) -> float:
    return LAT0 + STOP_GAP_DEG * i


def _stops(n: int = 5, pid: str = "1") -> pd.DataFrame:
    return pd.DataFrame(
        [{"pid": pid, "stpid": f"s{i}", "stpnm": f"Stop {i}", "lat": _stop_lat(i), "lon": LON0} for i in range(1, n + 1)]
    )


def _candidates(stop_ids, pid: str = "1") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"route": "r", "direction": "Eastbound", "stop_id": s, "stop_name": f"Stop {s[1:]}", "from_pid": pid,
             "first_arrival_day": "2024-09-03"}
            for s in stop_ids
        ]
    )


def _ping(pid: str, day: str, stop_index: int | None, lat: float | None = None, lon: float | None = LON0) -> dict:
    return {"pid": pid, "data_date": day, "lat": _stop_lat(stop_index) + NEAR_DEG if lat is None else lat, "lon": lon}


def _served_pings() -> pd.DataFrame:
    """s1 served in all three periods, s2 in periods 2 and 3, s3 in period 3, s4 in periods 1 and 3, s5 in none of period 3."""
    rows = [_ping("1", "2025-07-15", 1), _ping("1", "2025-07-15", 4)]
    rows += [_ping("1", "2025-10-14", 1), _ping("1", "2025-10-14", 2)]
    rows += [_ping("1", "2026-09-15", i) for i in (1, 2, 3, 4)]
    # none of these may count: another pid, a stale data_date, a fix without coordinates
    rows += [_ping("2", "2025-10-14", 3), _ping("1", "2025-10-14", 3).copy() | {"data_date": "2025-10-13"}]
    rows += [{"pid": "1", "data_date": "2025-10-14", "lat": np.nan, "lon": np.nan}]
    return pd.DataFrame(rows)


def test_stop_validity_from_pings_hand_built():
    periods = sv.geometry_periods(_pid_file(), "1", sample_days=SAMPLE_DAYS)
    assert periods.to_dict("records") == [
        {"pid": "1", "start": None, "end_exclusive": "2025-08-17", "sample_day": "2025-07-15"},
        {"pid": "1", "start": "2025-08-17", "end_exclusive": "2025-11-25", "sample_day": "2025-10-14"},
        {"pid": "1", "start": "2025-11-25", "end_exclusive": None, "sample_day": "2026-09-15"},
    ]
    # the latest sample day inside a period wins, and a pid with no dated change is one open period
    assert sv.geometry_periods(_pid_file(), "1", sample_days=("2025-07-15", "2025-08-01", "2025-10-14", "2026-09-15"))[
        "sample_day"
    ].tolist() == ["2025-08-01", "2025-10-14", "2026-09-15"]
    assert sv.geometry_periods({"geometry_changes": []}, "9", sample_days=SAMPLE_DAYS).to_dict("records") == [
        {"pid": "9", "start": None, "end_exclusive": None, "sample_day": "2026-09-15"}
    ]
    # a period with no sample day raises, naming the pid and the period
    with pytest.raises(ValueError, match=r"pid 1.*2025-08-17"):
        sv.geometry_periods(_pid_file(), "1", sample_days=("2025-07-15", "2026-09-15"))

    rows = sv.stop_validity_from_pings(_candidates(["s1", "s2", "s3", "s4"]), _stops(), _served_pings(), periods, MAX_FT)
    got = rows.set_index("stop_id")
    assert [None if pd.isna(v) else v for v in got["valid_from"]] == [None, "2025-08-17", "2025-11-25", "2025-11-25"]  # s1..s4
    assert set(rows["source"]) == {"mansueto"}
    assert list(got.loc["s2", "nearest_ping_ft"]) == list(SAMPLE_DAYS)  # one distance per period, keyed by its sample day
    assert got.loc["s1", "nearest_ping_ft"]["2025-07-15"] == pytest.approx(182.4, abs=1.0)  # 0.0005 degree north
    assert got.loc["s2", "nearest_ping_ft"]["2025-07-15"] > 2 * MAX_FT  # not served in period 1
    assert got.loc["s3", "nearest_ping_ft"]["2025-10-14"] > 2 * MAX_FT  # the stale, other-pid and null fixes did not count
    assert got.loc["s4", "first_arrival_day"] == "2024-09-03" and got.loc["s4", "from_pid"] == "1"

    # s5 is not served in the last period: today's stop missed on today's geometry is a threshold or data fault
    with pytest.raises(ValueError, match="s5"):
        sv.stop_validity_from_pings(_candidates(["s5"]), _stops(), _served_pings(), periods, MAX_FT)
    # no pings for the pid on a sample day raises, naming pid and day
    no_day = _served_pings()
    no_day = no_day[no_day["data_date"] != "2025-10-14"]
    with pytest.raises(ValueError, match=r"pid 1.*2025-10-14"):
        sv.stop_validity_from_pings(_candidates(["s1"]), _stops(), no_day, periods, MAX_FT)

    # nearest_feet is the minimum of straight_line_feet over the points
    rng = np.random.default_rng(0)
    lats, lons = 41.9 + rng.random(25) * 0.05, -87.7 + rng.random(25) * 0.05
    expected = min(geo.straight_line_feet(41.92, -87.66, a, b) for a, b in zip(lats, lons))
    assert geo.nearest_feet(41.92, -87.66, lats, lons) == pytest.approx(expected, rel=1e-9)
    with pytest.raises(ValueError):
        geo.nearest_feet(41.92, -87.66, [], [])


def test_ambiguous_distances_hand_built():
    """The margin the spec says to stop and report on: within MARGIN_FACTOR of the threshold either side, bounds included."""
    assert sv.MARGIN_FACTOR == 1.25  # at 500 ft: 400 to 625 ft
    rows = pd.DataFrame(
        [
            {"stop_id": "a", "from_pid": "1", "nearest_ping_ft": {"2025-07-15": 399.0, "2025-10-14": 625.0}},
            {"stop_id": "b", "from_pid": "1", "nearest_ping_ft": {"2025-07-15": 420.0, "2025-10-14": 700.0}},
        ]
    )
    got = sv.ambiguous_distances(rows, 500.0)
    assert got[["stop_id", "sample_day", "nearest_ping_ft"]].to_dict("records") == [
        {"stop_id": "a", "sample_day": "2025-10-14", "nearest_ping_ft": 625.0},
        {"stop_id": "b", "sample_day": "2025-07-15", "nearest_ping_ft": 420.0},
    ]
    clear = pd.DataFrame([{"stop_id": "c", "from_pid": "1", "nearest_ping_ft": {"2025-07-15": 100.0, "2025-10-14": 900.0}}])
    assert sv.ambiguous_distances(clear, 500.0).empty


def test_detour_candidates_hand_built(tmp_path: Path):
    """Two stops from day one, a third first seen on day 100 (after the slack): the third is the candidate."""
    days = pd.date_range("2025-01-01", periods=200).strftime("%Y-%m-%d")
    rows = [{"route": "8", "direction": "Southbound", "stop_id": s, "service_date": d} for d in days for s in ("a", "b")]
    rows += [{"route": "8", "direction": "Southbound", "stop_id": "c", "service_date": d} for d in days[100:]]
    target = tmp_path / "source=mansueto" / "pid=1"
    target.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(target / "year=2025.parquet", index=False)
    got = rrl.detour_candidates(tmp_path, ["1", "2"])  # pid 2 has no files: skipped, as detour_stop_arrivals does
    assert got.to_dict("records") == [
        {"route": "8", "direction": "Southbound", "stop_id": "c", "from_pid": "1", "first_arrival_day": days[100]}
    ]


def test_stop_validity_snapshot():
    data = sv.read_stop_validity_file()
    rows = pd.DataFrame(data["rows"])
    assert len(rows) == 38
    assert rows.groupby("from_pid").size().to_dict() == {"6662": 11, "6665": 13, "9368": 8, "9376": 6}
    assert set(rows["source"]) == {"mansueto"}
    pid_file = rrl.load_pid_file(rrl.DEFAULT_PIDS_FILE)
    assert data["max_stop_ping_distance_ft"] == sv.MAX_STOP_PING_DISTANCE_FT
    for pid, group in rows.groupby("from_pid"):
        periods = sv.geometry_periods(pid_file, pid)
        starts = {p for p in periods["start"] if p is not None}
        assert set(group["valid_from"].dropna()) <= starts  # a window opens on a geometry change
        for dist in group["nearest_ping_ft"]:
            assert list(dist) == periods["sample_day"].tolist()  # one distance per period
        # the last period's stops are all served: a window never starts after today's geometry
        assert (group["valid_from"].dropna() <= periods["start"].iloc[-1]).all()
    # the loader keeps every measured window (it also holds the reviewed keys: test_stop_validity_review_snapshot)
    loaded = sv.load_stop_validity()
    assert loaded["measured_valid_from"].notna().sum() == rows["valid_from"].notna().sum()
    assert {"route", "direction", "stop_id", "valid_from"} <= set(loaded.columns)
    # measured 2026-11-21 at 100 m (the spec's estimates, pinned): 29 stops with a window
    assert int(rows["valid_from"].notna().sum()) == 29
    by_stop = rows[rows["from_pid"] == "6662"].set_index("stop_id")["valid_from"]
    assert pd.isna(by_stop["18720"]) and pd.isna(by_stop["18721"])  # stop-id swaps on Chicago Avenue, served throughout
    wells = rows[rows["from_pid"] == "6665"].set_index("stop_id")["valid_from"]
    assert all(wells[s] == "2025-11-24" for s in ("6613", "6614", "5020"))
    # Wells & Chicago sits 155 and 172 ft from the old route's pings: read as served, the method's known limit
    assert pd.isna(wells["18803"])


def test_write_validity_refuses_windowed_view(tmp_path: Path):
    qa = tmp_path / "qa_mansueto.csv"
    with pytest.raises(ValueError, match="qa_mansueto.csv"):  # no view built yet
        rrl.check_unwindowed_view(tmp_path)
    header = "pid,year,stage,rows_in,rows_out,reason,count\n"
    qa.write_text(header + "9368,2025,pattern_join,10,8,stop_not_in_pattern,2\n")
    rrl.check_unwindowed_view(tmp_path)  # only the pattern-list reason: passes
    qa.write_text(header + "9368,2025,pattern_join,10,7,stop_not_in_pattern,2\n9368,2025,pattern_join,10,7,stop_before_valid_from,1\n")
    with pytest.raises(ValueError, match="qa_mansueto.csv"):
        rrl.check_unwindowed_view(tmp_path)
    assert not list(tmp_path.glob("*.json"))  # nothing written, and nothing under data/ from a test


# --- the owner's review (specs/mansueto-stop-validity.md) -------------------------------------------


def _row(route, direction, stop, pid, valid_from):
    return {"route": route, "direction": direction, "stop_id": stop, "stop_name": stop, "from_pid": pid, "source": "mansueto",
            "first_arrival_day": "2024-09-03", "nearest_ping_ft": {"2025-07-15": 1.0}, "valid_from": valid_from}


def _entry(stop, pid, valid_from, not_served=(), route="r", direction="Eastbound"):
    return {"route": route, "direction": direction, "stop_id": stop, "from_pid": pid, "valid_from": valid_from,
            "not_served": [list(p) for p in not_served], "rule": "ADR-014 point 1", "evidence": "docs/x.md",
            "schedule_sha1": ["a" * 40], "decided": "2026-11-27"}


def _file(tmp_path: Path, review, rows=None, dropped=None) -> Path:
    rows = rows or [_row("r", "Eastbound", "s1", "1", "2025-09-27"), _row("r", "Eastbound", "s2", "1", None),
                    _row("r", "Eastbound", "s3", "1", None), _row("r", "Eastbound", "s4", "1", None)]
    path = tmp_path / "validity.json"
    path.write_text(json.dumps({"title": "t", "max_stop_ping_distance_ft": 328.0, "sample_days": ["2025-07-15"], "rows": rows,
                                "review": review, "dropped_runs": dropped or []}))
    return path


def test_load_stop_validity_applies_review(tmp_path: Path):
    path = _file(tmp_path, [
        _entry("s1", "1", "2025-09-28"),  # replaces the measured date
        _entry("s2", "1", "2025-11-23"),  # gives a window to a row with none
        _entry("s3", "1", None, not_served=[("2025-08-17", "2025-11-22")]),  # an interval, no window
    ])
    loaded = sv.load_stop_validity(path).set_index("stop_id")
    assert list(sv.load_stop_validity(path).columns) == sv.ROW_COLUMNS + ["measured_valid_from", "not_served"]
    assert loaded.loc["s1", "valid_from"] == "2025-09-28" and loaded.loc["s1", "measured_valid_from"] == "2025-09-27"
    assert loaded.loc["s2", "valid_from"] == "2025-11-23" and loaded.loc["s2", "measured_valid_from"] is None
    assert loaded.loc["s3", "valid_from"] is None and loaded.loc["s3", "not_served"] == [("2025-08-17", "2025-11-22")]
    assert loaded.loc["s1", "not_served"] == []
    assert "s4" not in loaded.index  # neither a window nor an interval
    # an entry for a stop that is not among the rows raises
    with pytest.raises(ValueError, match="s9"):
        sv.load_stop_validity(_file(tmp_path, [_entry("s9", "1", "2025-09-28")]))
    # no review: the measured windows, as before
    assert sv.load_stop_validity(_file(tmp_path, []))["stop_id"].tolist() == ["s1"]
    # the writer keeps review and dropped_runs when it rewrites the rows
    dropped = [{"route": "r", "pid": "1", "vehicle_id": "v", "service_date": "2025-11-24", "first_arrival_from": "18:15",
                "first_arrival_to": "19:55", "rule": "ADR-015 point 2", "evidence": "docs/x.md", "decided": "2026-11-28"}]
    path = _file(tmp_path, [_entry("s1", "1", "2025-09-28")], dropped=dropped)
    sv.write_validity_file(pd.DataFrame([_row("r", "Eastbound", "s1", "1", "2025-09-27"), _row("r", "Eastbound", "s2", "1", None)]), path)
    after = json.loads(path.read_text())
    assert after["review"] == [_entry("s1", "1", "2025-09-28")] and after["dropped_runs"] == dropped
    assert len(after["rows"]) == 2
    with pytest.raises(ValueError, match="s1"):  # the rewritten rows no longer hold the reviewed stop
        sv.write_validity_file(pd.DataFrame([_row("r", "Eastbound", "s2", "1", None)]), path)
    assert len(json.loads(path.read_text())["rows"]) == 2  # nothing written on the refusal
    assert sv.load_dropped_runs(path)["vehicle_id"].tolist() == ["v"]


def test_stop_validity_review_snapshot():
    data = sv.read_stop_validity_file()
    review = data["review"]
    assert len(review) == 21
    for e in review:
        assert e["rule"] in ("ADR-014 point 1", "ADR-014 point 3") and e["evidence"].startswith("docs/") and e["decided"]
        assert e["schedule_sha1"] and all(re.fullmatch(r"[0-9a-f]{40}", h) for h in e["schedule_sha1"])
        assert (Path(__file__).resolve().parent.parent / e["evidence"]).is_file()
    loaded = sv.load_stop_validity()
    windows = loaded[loaded["valid_from"].notna()]
    assert len(windows) == 31
    assert int((loaded["not_served"].map(len) > 0).sum()) == 1 and len(loaded) == 32
    by = loaded.set_index(["from_pid", "stop_id"])
    assert by.loc[("9376", "15341"), "not_served"] == [("2025-08-17", "2025-11-22")] and by.loc[("9376", "15341"), "valid_from"] is None
    assert by.loc[("6665", "18803"), "valid_from"] == "2025-11-23" and by.loc[("6665", "18803"), "measured_valid_from"] is None
    assert by.loc[("6662", "6714"), "valid_from"] == "2025-09-28"
    assert by.loc[("6662", "17834"), "valid_from"] == "2025-09-28" and by.loc[("6662", "17834"), "measured_valid_from"] == "2025-09-27"
    assert by.loc[("9368", "5500"), "valid_from"] == "2025-11-23" and by.loc[("9368", "5500"), "measured_valid_from"] == "2025-11-25"
    assert by.loc[("6665", "769"), "valid_from"] == "2025-11-23"
    assert by.loc[("6665", "771"), "valid_from"] == "2025-09-28"  # not reviewed: measured date kept
    assert not loaded.duplicated(["route", "direction", "stop_id"]).any()
    assert len(data["rows"]) == 38 and sum(r["valid_from"] is not None for r in data["rows"]) == 29  # the measured rows are unchanged
    dropped = sv.load_dropped_runs()
    assert dropped.to_dict("records") == [{
        "route": "8", "pid": "9368", "vehicle_id": "1286", "service_date": "2025-11-24", "first_arrival_from": "18:15",
        "first_arrival_to": "19:55", "rule": "ADR-015 point 2", "evidence": "docs/2026-11-23-longest-pdist-dating.md", "decided": "2026-11-28",
    }]
