"""Tests for cta/mansueto.py: URL helpers (specs/split-cta-api.md) and the adapter (specs/mansueto-adapter.md).

Fixtures (built by scripts/build_mansueto_fixtures.py, manifest tests/fixtures/mansueto.manifest.json):
  mansueto_2026-07-27_route3.parquet   rows of PIDs 18414/18415 on 2026-07-27 Chicago, 11 columns verbatim
  mansueto_6410_last30d.parquet        every row of PID 6410 in the 30 days before its max(bus_stop_time)
  mansueto_rt_to_pid_route3.csv        the route 3 rows of rt_to_pid.csv
  mansueto_18414_footer.bin            the parquet footer (plus 8-byte trailer) cut from the real file
No test touches the network: the HTTP primitives are replaced for every test.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from cta import mansueto

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MANIFEST = FIXTURES / "mansueto.manifest.json"
ONE_DAY = FIXTURES / "mansueto_2026-07-27_route3.parquet"
RT_CSV = FIXTURES / "mansueto_rt_to_pid_route3.csv"
FOOTER = FIXTURES / "mansueto_18414_footer.bin"

needs_fixtures = pytest.mark.skipif(
    not MANIFEST.is_file(), reason="Mansueto fixtures missing; run scripts/build_mansueto_fixtures.py"
)


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


def test_parquet_url_basic():
    url = mansueto.parquet_url("6662")
    assert url.endswith("trips_6662_full.parquet")
    assert "cloudfront.net" in url


def test_rt_to_pid_url_under_base():
    assert mansueto.RT_TO_PID_URL == f"{mansueto.BASE}/rt_to_pid.csv"
    assert mansueto.parquet_url("6662").startswith(mansueto.BASE + "/processed_by_pid/")


def test_constants_match_spec():
    assert mansueto.MANSUETO_DATA_EDGE == "2026-07-28"
    assert mansueto.MANSUETO_TZ == "America/Chicago"
    assert mansueto.SOURCE_MANSUETO == "mansueto"
    assert mansueto.MAX_SELF_CONSISTENCY_DEVIATION == 0.02


# --- read_trips -----------------------------------------------------------------------------------


@needs_fixtures
def test_read_trips_one_day_fixture_returns_manifest_rows_as_utc(manifest):
    expected = manifest["files"][ONE_DAY.name]["rows"]
    frames = [mansueto.read_trips(ONE_DAY, pid=p) for p in ("18414", "18415")]
    trips = pd.concat(frames, ignore_index=True)
    assert len(trips) == expected  # no drops
    assert list(trips.columns) == mansueto.TRIP_COLUMNS
    assert set(trips["pid"]) == {"18414", "18415"}
    assert all(isinstance(v, str) for v in trips["pid"].head(3))
    assert str(trips["bus_stop_time"].dt.tz) == "UTC"
    assert trips["stop_sequence"].dtype == "int64"
    for col in ("run_id", "route", "vehicle_id", "stpid"):
        assert all(isinstance(v, str) for v in trips[col].head(3)), col
    assert (trips["route"] == "3").all()


@needs_fixtures
def test_read_trips_window_filters_on_chicago_wall_time():
    trips = mansueto.read_trips(ONE_DAY, pid="18414", start="2026-07-27 12:00", end="2026-07-27 13:00")
    local = trips["bus_stop_time"].dt.tz_convert(mansueto.MANSUETO_TZ)
    assert len(trips) > 0
    assert (local >= pd.Timestamp("2026-07-27 12:00", tz=mansueto.MANSUETO_TZ)).all()
    assert (local < pd.Timestamp("2026-07-27 13:00", tz=mansueto.MANSUETO_TZ)).all()


# --- clean_trips: analytic case -------------------------------------------------------------------


def _pattern_stops() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pid": ["p1"] * 3,
            "rtdir": ["Northbound"] * 3,
            "seq": [1, 3, 5],
            "stpid": ["s1", "s2", "s3"],
            "stpnm": ["A", "B", "C"],
            "lat": [41.8, 41.81, 41.82],
            "lon": [-87.6] * 3,
            "pdist_ft": [0.0, 1000.0, 2000.0],
        }
    )


def _analytic_trips() -> pd.DataFrame:
    naive = pd.to_datetime
    rows = [
        # trip A: 01:30 on the fall-back night is ambiguous -> dst_ambiguous_time; 03:00 CST is 09:00 UTC
        ("3-p1-A-2026-11-01", "s1", 1, naive("2026-11-01 01:30:00")),
        ("3-p1-A-2026-11-01", "s2", 2, naive("2026-11-01 03:00:00")),
        ("3-p1-A-2026-11-01", "s3", 3, naive("2026-11-01 03:05:00")),
        # trip B: s1 visited twice; the earlier time is kept
        ("3-p1-B-2026-11-02", "s1", 1, naive("2026-11-02 10:05:00")),
        ("3-p1-B-2026-11-02", "s1", 1, naive("2026-11-02 10:00:00")),
        ("3-p1-B-2026-11-02", "s2", 2, naive("2026-11-02 10:10:00")),
        # trip C: time goes backwards at seq 5 (third stop)
        ("3-p1-C-2026-11-02", "s1", 1, naive("2026-11-02 12:00:00")),
        ("3-p1-C-2026-11-02", "s2", 2, naive("2026-11-02 12:05:00")),
        ("3-p1-C-2026-11-02", "s3", 3, naive("2026-11-02 11:50:00")),
        # trip D: a stop the current pattern does not have
        ("3-p1-D-2026-11-02", "s9", 1, naive("2026-11-02 13:00:00")),
        ("3-p1-D-2026-11-02", "s1", 2, naive("2026-11-02 13:05:00")),
    ]
    df = pd.DataFrame(rows, columns=["run_id", "stpid", "stop_sequence", "bus_stop_time"])
    df["route"] = "3"
    df["pid"] = "p1"
    df["vehicle_id"] = "v1"
    return df[mansueto.TRIP_COLUMNS]


def test_clean_trips_analytic_case():
    clean, qa = mansueto.clean_trips(_analytic_trips(), _pattern_stops())
    by = {(r.stage, r.reason): r.count for r in qa.itertuples(index=False)}
    assert by[("read", mansueto.REASON_DST_AMBIGUOUS)] == 1
    assert by[("dedup", mansueto.REASON_DUPLICATE_STOP_VISIT)] == 1
    assert by[("pattern_join", mansueto.REASON_STOP_NOT_IN_PATTERN)] == 1
    assert by[("order", mansueto.REASON_NONMONOTONE_TIME)] == 1
    a = clean[clean["run_id"] == "3-p1-A-2026-11-01"].set_index("stpid")
    assert list(a.index) == ["s2", "s3"]
    assert a.loc["s2", "bus_stop_time"] == pd.Timestamp("2026-11-01 09:00:00", tz="UTC")
    b = clean[clean["run_id"] == "3-p1-B-2026-11-02"].set_index("stpid")
    assert b.loc["s1", "bus_stop_time"] == pd.Timestamp("2026-11-02 10:00:00", tz=mansueto.MANSUETO_TZ)
    c = clean[clean["run_id"] == "3-p1-C-2026-11-02"]
    assert c["stpid"].tolist() == ["s1", "s2"]
    assert not clean.duplicated(["run_id", "stpid"]).any()
    assert str(clean["bus_stop_time"].dt.tz) == "UTC"
    assert clean["seq"].dtype == "int64" and clean["stop_rank"].dtype == "int64"
    assert (clean["rtdir"] == "Northbound").all()
    assert set(clean.loc[clean["run_id"].str.contains("-A-"), "service_date"]) == {"2026-11-01"}
    assert set(clean.loc[clean["run_id"].str.contains("-B-"), "service_date"]) == {"2026-11-02"}


def test_clean_trips_already_utc_input_converts_with_zero_dst_drops():
    trips = _analytic_trips()
    trips = trips[trips["run_id"].str.contains("-B-|-C-")].copy()
    trips["bus_stop_time"] = trips["bus_stop_time"].dt.tz_localize(mansueto.MANSUETO_TZ).dt.tz_convert("UTC")
    clean, qa = mansueto.clean_trips(trips, _pattern_stops())
    read = qa[qa["stage"] == "read"]
    assert read["count"].sum() == 0
    assert len(clean) == 4


def test_clean_trips_null_keys_counted():
    trips = _analytic_trips()
    trips.loc[trips.index[6], "stpid"] = None
    trips.loc[trips.index[7], "bus_stop_time"] = pd.NaT
    clean, qa = mansueto.clean_trips(trips, _pattern_stops())
    read = qa[qa["stage"] == "read"].set_index("reason")["count"]
    assert read[mansueto.REASON_NULL_KEY_OR_TIME] == 2
    assert read[mansueto.REASON_DST_AMBIGUOUS] == 1


def test_clean_trips_service_date_falls_back_to_earliest_arrival():
    trips = _analytic_trips()
    trips = trips[trips["run_id"].str.contains("-B-")].copy()
    trips["run_id"] = "hand-built"
    # 2026-11-02 10:00 Chicago is 16:00 UTC; the fallback is the Chicago date of the run's first arrival
    clean, _ = mansueto.clean_trips(trips, _pattern_stops())
    assert set(clean["service_date"]) == {"2026-11-02"}
    late = trips.copy()
    late["bus_stop_time"] = late["bus_stop_time"] + pd.Timedelta(hours=13)  # 23:00 Chicago = 05:00 UTC next day
    clean, _ = mansueto.clean_trips(late, _pattern_stops())
    assert set(clean["service_date"]) == {"2026-11-02"}


def test_qa_reasons_sum_to_rows_dropped_and_stages_chain():
    _, qa = mansueto.clean_trips(_analytic_trips(), _pattern_stops())
    assert list(qa.columns) == ["stage", "rows_in", "rows_out", "reason", "count"]
    stages = list(dict.fromkeys(qa["stage"]))
    assert stages == list(mansueto.STAGES)
    for stage, part in qa.groupby("stage", sort=False):
        assert part["count"].sum() == part["rows_in"].iloc[0] - part["rows_out"].iloc[0], stage
    outs = qa.groupby("stage", sort=False)["rows_out"].first()
    ins = qa.groupby("stage", sort=False)["rows_in"].first()
    for a, b in zip(stages, stages[1:]):
        assert outs[a] == ins[b], (a, b)


# --- catalog, data edge, download -----------------------------------------------------------------


@needs_fixtures
def test_pids_for_route_from_fixture_csv():
    # The spec expected two route 3 rows; rt_to_pid.csv (2025-01-16) lists nine, in this catalog order.
    pids = mansueto.pids_for_route("3", RT_CSV)
    assert pids == ["18416", "18412", "18414", "18415", "18417", "1054", "7770", "18413", "19388"]
    assert {"18414", "18415"} <= set(pids)
    assert mansueto.pids_for_route("30", RT_CSV) == []


def test_pids_for_route_is_an_exact_string_match():
    cat = pd.DataFrame({"rt": ["3", "30", "3"], "pid": [18414, 30001, 18415]})
    assert mansueto.pids_for_route("3", cat) == ["18414", "18415"]
    assert mansueto.pids_for_route(3, cat) == ["18414", "18415"]
    assert mansueto.pids_for_route("9999", cat) == []


@needs_fixtures
def test_data_edge_from_committed_footer(monkeypatch: pytest.MonkeyPatch, manifest):
    src = manifest["sources"]["18414"]
    size = src["bytes"]
    footer = FOOTER.read_bytes()
    offset = size - len(footer)
    calls: list[tuple[int, int]] = []

    def fake_head(url: str) -> dict:
        assert url == mansueto.parquet_url("18414")
        return {"bytes": size, "last_modified": src["last_modified"]}

    def fake_range(url: str, start: int, end: int) -> bytes:
        assert url == mansueto.parquet_url("18414")
        assert 0 <= start <= end < size
        calls.append((start, end))
        assert start >= offset, "range request reached outside the committed footer sample"
        return footer[start - offset : end - offset + 1]

    monkeypatch.setattr(mansueto, "http_head", fake_head)
    monkeypatch.setattr(mansueto, "http_range", fake_range)
    edge = mansueto.data_edge("18414")
    assert set(edge) == {"url", "bytes", "last_modified", "rows", "min_bus_stop_time", "max_bus_stop_time"}
    assert edge["url"] == mansueto.parquet_url("18414")
    assert edge["bytes"] == size
    assert edge["rows"] == src["data_edge"]["rows"]
    assert edge["max_bus_stop_time"][:10] == mansueto.MANSUETO_DATA_EDGE
    assert edge["min_bus_stop_time"] < edge["max_bus_stop_time"]
    assert sum(e - s + 1 for s, e in calls) < 1_000_000  # footer only, never the file


@needs_fixtures
def test_fetch_parquet_writes_file_and_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, manifest):
    def fake_download(url: str, out: Path) -> None:
        shutil.copy(ONE_DAY, out)

    edge = dict(manifest["sources"]["18414"]["data_edge"])
    monkeypatch.setattr(mansueto, "download", fake_download)
    monkeypatch.setattr(mansueto, "data_edge", lambda pid: edge)
    path = mansueto.fetch_parquet("18414", tmp_path)
    assert path == tmp_path / "trips_18414_full.parquet"
    assert path.stat().st_size == ONE_DAY.stat().st_size
    meta = json.loads((tmp_path / "trips_18414_full.meta.json").read_text())
    assert meta["max_bus_stop_time"][:10] == mansueto.MANSUETO_DATA_EDGE
    assert pd.Timestamp(meta["fetched_at"]).tzinfo is not None
    assert meta["pid"] == "18414"


def test_fetch_parquet_refuses_empty_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(mansueto, "download", lambda url, out: Path(out).write_bytes(b""))
    monkeypatch.setattr(mansueto, "data_edge", lambda pid: {})
    with pytest.raises(ValueError):
        mansueto.fetch_parquet("18414", tmp_path)
    assert not (tmp_path / "trips_18414_full.parquet").exists()
