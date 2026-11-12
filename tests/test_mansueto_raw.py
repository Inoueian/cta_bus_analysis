"""Acceptance tests for specs/mansueto-raw-adapter.md: cta.mansueto_raw (fetch, read, clean, pairs, guards).

No network: ``cta.mansueto._request`` is disabled for every test; fetch tests replace ``http_head`` and
``download`` with fakes.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import urllib.error
from pathlib import Path

import pandas as pd
import pytest

from cta import archive, mansueto, mansueto_raw

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DAY = "2026-10-22"
DAY_FILE = FIXTURES / f"mansueto_raw_{DAY}_michigan.csv.gz"
MANIFEST = FIXTURES / "mansueto_raw.manifest.json"
KEPT_PIDS = Path(__file__).resolve().parent.parent / "notebooks" / "michigan_ave_kept_pids.json"

# Measured on the committed fixture (spec estimates ~23,453 rows, ~44 pids, ~23,393 fixes, ~1,559 runs, ~60 duplicates).
EXPECTED_ROWS = 23_453
EXPECTED_PIDS = 44
EXPECTED_FIXES = 23_393
EXPECTED_RUNS = 1_559
EXPECTED_DUPLICATES = 60

CSV_COLUMNS = [
    "vid", "tmstmp", "lat", "lon", "hdg", "pid", "rt", "des", "pdist", "dly", "tatripid", "origtatripno",
    "tablockid", "zone", "scrape_file", "data_time", "data_hour", "data_date",
]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(url, *args, **kwargs):
        raise AssertionError(f"network call attempted in tests: {url}")

    monkeypatch.setattr(mansueto, "_request", _refuse)


def _lat(pdist_ft: float) -> float:
    """Latitude that puts a straight northbound pattern's GPS distance equal to its pdist."""
    return 41.9 + pdist_ft / archive.FT_PER_M / archive.M_PER_DEG_LAT


def csv_row(vid: str, tmstmp: str, pdist: float | None, data_date: str, *, pid: str = "9001", trip: str | None = "77") -> dict:
    lat = _lat(pdist or 0.0)
    return {
        "vid": vid, "tmstmp": tmstmp, "lat": lat, "lon": -87.62, "hdg": 0, "pid": pid, "rt": "146", "des": "X",
        "pdist": "" if pdist is None else int(pdist), "dly": "False", "tatripid": "1", "origtatripno": trip or "",
        "tablockid": "B", "zone": "", "scrape_file": "f.json", "data_time": "", "data_hour": "", "data_date": data_date,
    }


def write_csv(path: Path, rows: list[dict]) -> Path:
    pd.DataFrame(rows, columns=CSV_COLUMNS).to_csv(path, index=False)
    return path


def stops_table(pid: str = "9001", pdists=(1500.0, 4500.0)) -> pd.DataFrame:
    return pd.DataFrame(
        {"pid": pid, "rtdir": "Northbound", "seq": range(1, len(pdists) + 1),
         "stpid": [f"S{i}" for i in range(len(pdists))], "pdist_ft": list(pdists)}
    )


def test_read_and_clean_fixture():
    manifest = json.loads(MANIFEST.read_text())["files"][DAY_FILE.name]
    assert hashlib.sha256(DAY_FILE.read_bytes()).hexdigest() == manifest["sha256"]
    with gzip.open(DAY_FILE, "rt") as f:
        raw = pd.read_csv(f, dtype=str, keep_default_na=False)
    pos = mansueto_raw.read_day(DAY_FILE)
    assert len(pos) == manifest["rows"] == EXPECTED_ROWS
    assert pos["pid"].nunique() == EXPECTED_PIDS
    for c in ("route", "pid", "vehicle_id", "origtatripno", "data_date", "tmstmp"):
        assert pos[c].dropna().map(type).eq(str).all(), c
    assert str(pos["vehicle_ts"].dt.tz) == "UTC"
    assert (pos["vehicle_ts"].dt.second == 0).all()
    for raw_col, col in [("vid", "vehicle_id"), ("pid", "pid"), ("origtatripno", "origtatripno"), ("tmstmp", "tmstmp"), ("pdist", "pdist")]:
        assert pos[col].isna().sum() == (raw[raw_col] == "").sum(), col
    assert pos["vehicle_ts"].isna().sum() == 0

    con = mansueto_raw.open_db()
    fixes = mansueto_raw.clean_fixes(con, DAY, pos)
    assert list(fixes.columns) == archive.CLEAN_FIX_COLUMNS
    assert len(fixes) == EXPECTED_FIXES
    assert fixes["run_id"].nunique() == EXPECTED_RUNS
    assert not fixes.duplicated(["run_id", "vehicle_ts"]).any()
    q = mansueto_raw.qa(con, DAY)
    clean = q[q["stage"] == "clean"]
    assert dict(zip(clean["reason"], clean["count"])) == {archive.REASON_DUPLICATE_FIX: EXPECTED_DUPLICATES}


def test_known_case_arrivals(tmp_path: Path):
    day = "2026-09-15"
    rows = [
        csv_row("1", "20260915 08:00", 0, day),
        csv_row("1", "20260915 08:05", 3000, day),
        csv_row("1", "20260915 08:05", 3100, day),  # repeated tmstmp: the lower pdist is kept
        csv_row("1", "20260915 08:10", 6000, day),
        csv_row("2", "20260915 08:00", 100, day, trip=None),  # null origtatripno
        csv_row("3", "20251102 01:30", 100, day),  # fall-back hour, ambiguous in Chicago
    ]
    pos = mansueto_raw.read_day(write_csv(tmp_path / f"{day}.csv", rows))
    con = mansueto_raw.open_db()
    fixes = mansueto_raw.clean_fixes(con, day, pos)
    assert fixes["pdist"].tolist() == [0.0, 3000.0, 6000.0]
    assert (fixes["service_date"] == day).all()
    assert fixes["run_id"].iloc[0] == f"1-9001-77-{day}"
    pairs = mansueto_raw.fix_pairs(con, day, fixes)
    arr = archive.impute_arrivals(con, day, pairs, stops_table())
    assert arr["arrival_time"].tolist() == [
        pd.Timestamp("2026-09-15 13:02:30", tz="UTC"), pd.Timestamp("2026-09-15 13:07:30", tz="UTC"),
    ]
    assert (arr["bracket_gap_s"] == 300).all()
    q = mansueto_raw.qa(con, day)
    clean = q[q["stage"] == "clean"]
    assert dict(zip(clean["reason"], clean["count"])) == {
        archive.REASON_NULL_KEY: 1, mansueto_raw.REASON_DST_AMBIGUOUS: 1, archive.REASON_DUPLICATE_FIX: 1,
    }


def test_gap_threshold_is_per_source():
    t0 = pd.Timestamp("2026-09-15 13:00", tz="UTC")
    fixes = pd.DataFrame(
        {
            "route": "146", "pid": "9001", "vehicle_id": "1", "run_id": "1-9001-77-2026-09-15", "service_date": "2026-09-15",
            "vehicle_ts": [t0 + pd.Timedelta(seconds=s) for s in (0, 300, 900, 1800)],
            "pdist": [0.0, 2000.0, 4000.0, 6000.0],
        }
    )
    fixes["lat"] = fixes["pdist"].map(_lat)
    fixes["lon"] = -87.62
    con = mansueto_raw.open_db()
    raw = archive.fix_pairs(con, "2026-09-15", fixes, max_gap_s=mansueto_raw.MAX_RAW_BRACKET_GAP_S)
    assert raw["bracket_gap_s"].tolist() == [300.0, 600.0]
    q = mansueto_raw.qa(con, "2026-09-15")
    assert dict(zip(q["reason"], q["count"])) == {archive.REASON_GAP: 1}
    default = archive.fix_pairs(con, "2026-09-15", fixes)
    assert default.empty
    assert archive.MAX_BRACKET_GAP_S == 180
    assert mansueto_raw.MAX_RAW_BRACKET_GAP_S == 660


class _Head:
    def __init__(self, bytes_: int, last_modified: str, status: int = 200):
        self.value = {"bytes": bytes_, "last_modified": last_modified}
        self.status = status

    def __call__(self, url):
        if self.status == 404:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return dict(self.value)


def test_fetch_day_records_and_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    body = b"vid,tmstmp\n1,20260915 08:00\n2,20260915 08:05\n"
    head = _Head(len(body), "2026-09-16T10:00:00+00:00")
    calls = []

    def fake_download(url, out, payload=None):
        calls.append(url)
        Path(out).write_bytes(fake_download.payload)

    fake_download.payload = body
    monkeypatch.setattr(mansueto, "http_head", head)
    monkeypatch.setattr(mansueto, "download", fake_download)

    dest = tmp_path / "raw"
    path = mansueto_raw.fetch_day("2026-09-15", dest)
    meta = json.loads(mansueto_raw.meta_path(path).read_text())
    assert meta["bytes"] == len(body) and meta["rows"] == 2 and meta["last_modified"] == head.value["last_modified"]
    assert meta["url"].endswith("/full_day_data/2026-09-15.csv") and meta["fetched_at"]
    assert mansueto_raw.fetch_day("2026-09-15", dest) == path
    assert len(calls) == 1

    head.value["last_modified"] = "2026-11-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="changed"):
        mansueto_raw.fetch_day("2026-09-15", dest)
    assert json.loads(mansueto_raw.meta_path(path).read_text()) == meta  # never overwritten

    fake_download.payload = body[:-5]
    with pytest.raises(ValueError, match="bytes"):
        mansueto_raw.fetch_day("2026-09-16", dest)
    assert not (dest / "2026-09-16.csv").exists()
    assert not mansueto_raw.meta_path(dest / "2026-09-16.csv").exists()
    assert not list(dest.glob("*.part"))

    head.status = 404
    with pytest.raises(FileNotFoundError, match="2026-09-17"):
        mansueto_raw.fetch_day("2026-09-17", dest)


def test_refuses_foreign_connection_and_files(tmp_path: Path):
    pos = mansueto_raw.read_day(write_csv(tmp_path / "2026-09-15.csv", [csv_row("1", "20260915 08:00", 0, "2026-09-15")]))
    with pytest.raises(ValueError, match="open_db"):
        mansueto_raw.clean_fixes(archive.open_archive_db(), "2026-09-15", pos)
    con = mansueto_raw.open_db()
    con.execute(
        "INSERT INTO archive_ingest(archive_date, sha256, source_path, local_path, rows, bytes) VALUES ('2026-10-22','x','p','l',1,1)"
    )
    with pytest.raises(ValueError, match="archive_ingest"):
        mansueto_raw.clean_fixes(con, "2026-09-15", pos)

    both = tmp_path / "both"
    both.mkdir()
    (both / "2026-10-22.csv").write_text("x")
    (both / "mansueto_raw_2026-10-22_x.csv.gz").write_bytes(b"x")
    with pytest.raises(ValueError, match="several"):
        mansueto_raw.day_file(both, "2026-10-22")
    one = tmp_path / "one"
    one.mkdir()
    (one / "mansueto_raw_2026-10-22_x.csv.gz").write_bytes(b"x")
    (one / "archive_2026-10-22_x.ndjson.gz").write_bytes(b"x")
    assert mansueto_raw.day_file(one, "2026-10-22") == one / "mansueto_raw_2026-10-22_x.csv.gz"
    with pytest.raises(FileNotFoundError):
        mansueto_raw.day_file(one, "2026-10-23")
