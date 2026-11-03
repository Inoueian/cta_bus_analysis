"""Acceptance tests for specs/archive-adapter.md: cta.archive (ingest, clean fixes, pairs, imputation, QA).

No network: ``cta.archive.run_curl`` is disabled for every test by the autouse fixture below.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from cta import archive

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DAY = "2026-10-29"
DAY_FILE = FIXTURES / f"archive_{DAY}_michigan.ndjson.gz"
DAY_INDEX = FIXTURES / f"archive_{DAY}_michigan.index.json"
KEPT_PIDS = Path(__file__).resolve().parent.parent / "notebooks" / "michigan_ave_kept_pids.json"

# Prototype numbers from docs/2026-11-03-archive-imputation-prototype.md, re-pinned on the fixture.
EXPECTED_CLEAN_ROWS = 118_014
EXPECTED_RUNS = 1_582


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(url, out, **kwargs):
        raise AssertionError(f"network call attempted in tests: {url}")

    monkeypatch.setattr(archive, "run_curl", _refuse)


@pytest.fixture(scope="module")
def fixture_index() -> dict:
    return json.loads(DAY_INDEX.read_text())


@pytest.fixture(scope="module")
def kept_pids() -> list[str]:
    return [str(r["pid"]) for r in json.loads(KEPT_PIDS.read_text())["pids"]]


@pytest.fixture(scope="module")
def ingested_con(fixture_index):
    con = archive.open_archive_db()
    meta = archive.day_file_meta(fixture_index, DAY)
    archive.ingest_day(con, meta, DAY_FILE)
    yield con
    con.close()


def _synthetic_fixes(run_id: str = "v1-p1-2026-10-29-30000", t0_ms: int = 1_793_300_000_000) -> pd.DataFrame:
    """Three fixes 60 s apart moving 1000 ft each step along pattern p1."""
    rows = []
    for i, (dt_s, pdist) in enumerate([(0, 0.0), (60, 1000.0), (120, 2000.0)]):
        rows.append(
            {
                "route": "151",
                "pid": "p1",
                "vehicle_id": "v1",
                "run_id": run_id,
                "service_date": DAY,
                "vehicle_ts": pd.Timestamp(t0_ms + dt_s * 1000, unit="ms", tz="UTC"),
                "pdist": pdist,
                "lat": 41.88 + i * 0.0025,
                "lon": -87.62,
            }
        )
    return pd.DataFrame(rows)


# --- Fixture ingests with the recorded SHA-256 and row count --------------------------------------


def test_fixture_ingests_with_recorded_checksum_and_rows(fixture_index):
    meta = archive.day_file_meta(fixture_index, DAY)
    assert meta["sha256"] == archive.file_sha256(DAY_FILE)
    con = archive.open_archive_db()
    result = archive.ingest_day(con, meta, DAY_FILE)
    assert result["status"] == "ingested"
    assert result["rows"] == meta["rows"]
    n = con.execute("SELECT count(*) FROM positions_raw WHERE archive_date = ?", [DAY]).fetchone()[0]
    assert n == meta["rows"]
    qa = archive.qa(con, DAY)
    ingest_qa = qa[qa["stage"] == "ingest"]
    assert ingest_qa["rows_in"].iloc[0] == meta["rows"]
    assert ingest_qa["rows_out"].iloc[0] == meta["rows"]
    # A second ingest of the same published file is a no-op, not a duplicate.
    again = archive.ingest_day(con, meta, DAY_FILE)
    assert again["status"] == "skipped"
    assert con.execute("SELECT count(*) FROM positions_raw").fetchone()[0] == meta["rows"]


def test_ingest_refuses_changed_checksum(fixture_index, tmp_path: Path):
    meta = archive.day_file_meta(fixture_index, DAY)
    bad = dict(meta, sha256="0" * 64)
    con = archive.open_archive_db()
    with pytest.raises(ValueError, match="SHA-256"):
        archive.ingest_day(con, bad, DAY_FILE)
    # Published source changed after a successful ingest: refuse rather than silently re-ingest.
    archive.ingest_day(con, meta, DAY_FILE)
    tampered = tmp_path / DAY_FILE.name
    shutil.copy(DAY_FILE, tampered)
    changed = dict(meta, sha256=archive.file_sha256(tampered), rows=meta["rows"])
    changed["sha256"] = "1" * 64
    with pytest.raises(ValueError):
        archive.ingest_day(con, changed, tampered)


def test_fetch_index_uses_curl_not_urllib(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[str] = []

    def fake_curl(url, out, **kwargs):
        calls.append(url)
        shutil.copy(DAY_INDEX, out)

    monkeypatch.setattr(archive, "run_curl", fake_curl)
    index = archive.fetch_index(archive.INDEX_URL, tmp_path)
    assert calls == [archive.INDEX_URL]
    assert index["days"][0]["date"] == DAY
    pinned = archive.pin_index(index, tmp_path)
    assert pinned.is_file()
    assert archive.fetch_index(pinned)["days"][0]["date"] == DAY


# --- clean_fixes on the fixture returns 118,014 rows and 1,582 runs -------------------------------


def test_clean_fixes_row_and_run_counts(ingested_con, kept_pids):
    fixes = archive.clean_fixes(ingested_con, DAY, kept_pids)
    assert len(fixes) == EXPECTED_CLEAN_ROWS
    assert fixes["run_id"].nunique() == EXPECTED_RUNS
    assert list(fixes.columns) == archive.CLEAN_FIX_COLUMNS
    assert fixes["vehicle_ts"].dt.tz is not None and str(fixes["vehicle_ts"].dt.tz) == "UTC"
    for col in ("route", "pid", "vehicle_id", "run_id", "service_date"):
        assert fixes[col].map(type).eq(str).all(), col
    # One row per (run, vehicle_ts).
    assert not fixes.duplicated(["run_id", "vehicle_ts"]).any()
    # Post-midnight trips keep their scheduled service date (Method 6).
    assert set(fixes["service_date"]) == {"2026-10-28", "2026-10-29"}


# --- Synthetic 3-fix trip yields the analytically correct arrival time ----------------------------


def test_synthetic_trip_arrival_time_is_exact():
    con = archive.open_archive_db()
    fixes = _synthetic_fixes()
    pairs = archive.fix_pairs(con, DAY, fixes)
    assert len(pairs) == 2
    stops = pd.DataFrame(
        {
            "pid": ["p1", "p1", "p1"],
            "rtdir": ["Northbound"] * 3,
            "seq": [1, 2, 3],
            "stpid": ["s0", "s1", "s2"],
            "stpnm": ["A", "B", "C"],
            "lat": [41.88, 41.8825, 41.885],
            "lon": [-87.62] * 3,
            "pdist_ft": [0.0, 250.0, 1750.0],
        }
    )
    arrivals = archive.impute_arrivals(con, DAY, pairs, stops)
    arrivals = arrivals.set_index("stpid")
    t0 = fixes["vehicle_ts"].iloc[0]
    # s0 sits exactly on the first fix: p0 <= stop < p1 keeps it, arrival == t0.
    assert arrivals.loc["s0", "arrival_time"] == t0
    # s1 is a quarter of the way through the first 60 s bracket: +15 s.
    assert arrivals.loc["s1", "arrival_time"] == t0 + pd.Timedelta(seconds=15)
    # s2 is three quarters through the second bracket: +60 s +45 s.
    assert arrivals.loc["s2", "arrival_time"] == t0 + pd.Timedelta(seconds=105)
    assert (arrivals["bracket_gap_s"] == 60.0).all()
    assert str(arrivals["arrival_time"].dt.tz) == "UTC"


def test_earliest_crossing_kept_when_run_recrosses_a_stop():
    con = archive.open_archive_db()
    fixes = _synthetic_fixes()
    # Add a backwards snap and a re-crossing: 2000 -> 900 -> 1900 ft.
    extra = fixes.iloc[[1, 2]].copy()
    extra["vehicle_ts"] = extra["vehicle_ts"] + pd.Timedelta(seconds=120)
    extra["pdist"] = [900.0, 1900.0]
    fixes = pd.concat([fixes, extra], ignore_index=True)
    pairs = archive.fix_pairs(con, DAY, fixes)
    stops = pd.DataFrame(
        {"pid": ["p1"], "rtdir": ["Northbound"], "seq": [1], "stpid": ["s1"], "stpnm": ["B"],
         "lat": [41.88], "lon": [-87.62], "pdist_ft": [1500.0]}
    )
    arrivals = archive.impute_arrivals(con, DAY, pairs, stops)
    assert len(arrivals) == 1
    t0 = fixes["vehicle_ts"].iloc[0]
    assert arrivals["arrival_time"].iloc[0] == t0 + pd.Timedelta(seconds=90)
    qa = archive.qa(con, DAY)
    imp = qa[qa["stage"] == "impute"]
    assert imp["rows_in"].iloc[0] == 2 and imp["rows_out"].iloc[0] == 1
    assert imp.set_index("reason").loc[archive.REASON_LATER_CROSSING, "count"] == 1
    # The backward pair was dropped and counted.
    pr = qa[qa["stage"] == "pairs"].set_index("reason")
    assert pr.loc[archive.REASON_BACKWARD, "count"] == 1


# --- A pair spanning a known_gaps window is dropped and counted in the QA table -------------------


def test_pair_spanning_known_gap_is_dropped_and_counted():
    con = archive.open_archive_db()
    fixes = _synthetic_fixes()
    t1 = fixes["vehicle_ts"].iloc[1]
    gaps = pd.DataFrame(
        {
            "start": [t1 + pd.Timedelta(seconds=10)],
            "end": [t1 + pd.Timedelta(seconds=20)],
            "feeds": [["bus"]],
            "note": ["No polls recorded"],
        }
    )
    pairs = archive.fix_pairs(con, DAY, fixes, known_gaps=gaps)
    assert len(pairs) == 1
    assert pairs["p0"].iloc[0] == 0.0  # the first pair (before the gap) survives
    qa = archive.qa(con, DAY)
    pr = qa[qa["stage"] == "pairs"]
    assert pr["rows_in"].iloc[0] == 2 and pr["rows_out"].iloc[0] == 1
    assert pr.set_index("reason").loc[archive.REASON_SPANS_KNOWN_GAP, "count"] == 1


def test_pair_filters_each_reason_once():
    con = archive.open_archive_db()
    fixes = _synthetic_fixes()
    t = fixes["vehicle_ts"].iloc[2]
    more = pd.DataFrame(
        [
            # gap > 180 s
            {"vehicle_ts": t + pd.Timedelta(seconds=181), "pdist": 2100.0, "lat": 41.886, "lon": -87.62},
            # geometry: 10,000 ft of pdist with no GPS movement
            {"vehicle_ts": t + pd.Timedelta(seconds=241), "pdist": 12_100.0, "lat": 41.886, "lon": -87.62},
            # speed: 8,000 ft in 60 s = 91 mph, with matching GPS movement (~0.022 deg lat)
            {"vehicle_ts": t + pd.Timedelta(seconds=301), "pdist": 20_100.0, "lat": 41.908, "lon": -87.62},
        ]
    )
    for col in ("route", "pid", "vehicle_id", "run_id", "service_date"):
        more[col] = fixes[col].iloc[0]
    fixes = pd.concat([fixes, more[fixes.columns]], ignore_index=True)
    pairs = archive.fix_pairs(con, DAY, fixes)
    assert len(pairs) == 2
    qa = archive.qa(con, DAY)
    pr = qa[qa["stage"] == "pairs"].set_index("reason")["count"]
    assert pr[archive.REASON_GAP] == 1
    assert pr[archive.REASON_GEOMETRY] == 1
    assert pr[archive.REASON_SPEED] == 1


# --- QA table reason counts sum to rows_in − rows_out at every stage ------------------------------


def _assert_qa_sums(qa: pd.DataFrame) -> None:
    assert set(qa.columns) >= {"stage", "rows_in", "rows_out", "reason", "count"}
    assert not qa.empty
    for stage, grp in qa.groupby("stage", sort=False):
        assert grp["rows_in"].nunique() == 1 and grp["rows_out"].nunique() == 1, stage
        assert grp["count"].sum() == grp["rows_in"].iloc[0] - grp["rows_out"].iloc[0], stage


def test_qa_reason_counts_sum_on_fixture(ingested_con, kept_pids, fixture_index):
    from cta import calendar as cal

    fixes = archive.clean_fixes(ingested_con, DAY, kept_pids)
    pairs = archive.fix_pairs(ingested_con, DAY, fixes, known_gaps=cal.known_gaps(fixture_index))
    qa = archive.qa(ingested_con, DAY)
    assert set(qa["stage"]) >= {"ingest", "clean", "pairs"}
    _assert_qa_sums(qa)
    clean = qa[qa["stage"] == "clean"]
    assert clean["rows_out"].iloc[0] == EXPECTED_CLEAN_ROWS
    assert clean["rows_in"].iloc[0] == fixture_index["days"][0]["files"]["bus"]["rows"]
    assert clean.set_index("reason").loc[archive.REASON_DUPLICATE_FIX, "count"] == 118_995 - EXPECTED_CLEAN_ROWS
    pr = qa[qa["stage"] == "pairs"]
    assert pr["rows_in"].iloc[0] == EXPECTED_CLEAN_ROWS - EXPECTED_RUNS  # one pair per fix after the first
    assert len(pairs) == pr["rows_out"].iloc[0]


def test_qa_reason_counts_sum_synthetic():
    con = archive.open_archive_db()
    fixes = _synthetic_fixes()
    pairs = archive.fix_pairs(con, DAY, fixes)
    stops = pd.DataFrame(
        {"pid": ["p1"], "rtdir": ["Northbound"], "seq": [1], "stpid": ["s1"], "stpnm": ["B"],
         "lat": [41.88], "lon": [-87.62], "pdist_ft": [500.0]}
    )
    archive.impute_arrivals(con, DAY, pairs, stops)
    _assert_qa_sums(archive.qa(con, DAY))
