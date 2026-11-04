"""Acceptance tests for specs/archive-adapter.md: cta.views.run_level_from_archive on the fixture day.

The getpatterns fixture (tests/fixtures/getpatterns/getpatterns_<pid>.json for the 45 kept pids,
fetched 2026-11-03) is built by scripts/build_archive_fixtures.py --getpatterns. Tests that need it
skip, with the reason, if it is ever missing.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cta import archive, patterns, views

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DAY = "2026-10-29"
DAY_FILE = FIXTURES / f"archive_{DAY}_michigan.ndjson.gz"
DAY_INDEX = FIXTURES / f"archive_{DAY}_michigan.index.json"
GETPATTERNS_DIR = FIXTURES / "getpatterns"
REPO = Path(__file__).resolve().parent.parent
KEPT_PIDS = REPO / "notebooks" / "michigan_ave_kept_pids.json"

KEPT = [str(r["pid"]) for r in json.loads(KEPT_PIDS.read_text())["pids"]]
MISSING_PATTERNS = [p for p in KEPT if not (GETPATTERNS_DIR / f"getpatterns_{p}.json").is_file()]
needs_getpatterns = pytest.mark.skipif(
    bool(MISSING_PATTERNS),
    reason=f"getpatterns fixture missing for {len(MISSING_PATTERNS)} kept pids; "
    "run scripts/build_archive_fixtures.py --getpatterns (needs CTA_API_KEY and www.ctabustracker.com)",
)

MIN_RUN_STOP_ROWS = 16_000  # spec acceptance: prototype produced 16,740
MAX_MEDIAN_RATIO_DEVIATION = 0.20  # ADR-006: one-day medians vs a 30-day Mansueto median; 10% failed 3 of 17 pids
MIN_RUNS_FOR_RATIO = 30


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(url, out, **kwargs):
        raise AssertionError(f"network call attempted in tests: {url}")

    monkeypatch.setattr(archive, "run_curl", _refuse)


@pytest.fixture(scope="module")
def fixture_index() -> dict:
    return json.loads(DAY_INDEX.read_text())


@pytest.fixture(scope="module")
def ingested_con(fixture_index):
    con = archive.open_archive_db()
    archive.ingest_day(con, archive.day_file_meta(fixture_index, DAY), DAY_FILE)
    yield con
    con.close()


@pytest.fixture(scope="module")
def run_level(ingested_con, fixture_index) -> pd.DataFrame:
    stops = patterns.pattern_stops_table(KEPT, GETPATTERNS_DIR)
    return views.run_level_from_archive([DAY], KEPT, con=ingested_con, index=fixture_index, pattern_stops=stops)


def test_run_level_from_synthetic_pattern_cache(ingested_con, fixture_index, tmp_path: Path):
    """The view builds end to end from a getpatterns cache file, with ADR-003 columns and types."""
    pid = "6414"
    # Stop pdists taken from the fixes themselves: a stop at the median pdist of the pattern is crossed
    # by nearly every run, so the view is non-trivial without the real getpatterns fixture.
    fixes = archive.clean_fixes(ingested_con, DAY, [pid])
    mid = float(fixes["pdist"].median())
    root = {
        "ptr": [
            {
                "pid": pid,
                "ln": 99999,
                "rtdir": "Northbound",
                "pt": [
                    {"seq": 1, "lat": 41.87, "lon": -87.62, "typ": "S", "stpid": "1580", "stpnm": "Michigan & Roosevelt", "pdist": 0},
                    {"seq": 2, "lat": 41.88, "lon": -87.62, "typ": "W", "pdist": 10},
                    {"seq": 3, "lat": 41.89, "lon": -87.62, "typ": "S", "stpid": "1126", "stpnm": "Michigan & Chicago", "pdist": mid},
                ],
            }
        ]
    }
    (tmp_path / f"getpatterns_{pid}.json").write_text(json.dumps(root))
    stops = patterns.pattern_stops_table([pid], tmp_path)
    assert stops["stpid"].tolist() == ["1580", "1126"]  # waypoints dropped
    view = views.run_level_from_archive([DAY], [pid], con=ingested_con, index=fixture_index, pattern_stops=stops)
    assert list(view.columns) == views.RUN_LEVEL_COLUMNS
    assert (view["source"] == "archive").all()
    assert (view["direction"] == "Northbound").all()
    assert (view["pattern_id"] == pid).all()
    assert set(view["stop_id"]) <= {"1580", "1126"}
    assert not view.duplicated(["run_id", "stop_id"]).any()
    assert str(view["arrival_time"].dt.tz) == "UTC"
    assert view["stop_sequence_index"].dtype.kind == "i"
    assert (view["calendar_flag"] == "").all()  # 2026-10-29: no holiday, no known gap
    n_runs = fixes["run_id"].nunique()
    assert (view["stop_id"] == "1126").sum() >= 0.8 * n_runs
    assert (view["bracket_gap_s"] <= archive.MAX_BRACKET_GAP_S).all()


@needs_getpatterns
def test_run_level_row_count_and_no_duplicates(run_level):
    assert len(run_level) >= MIN_RUN_STOP_ROWS
    assert not run_level.duplicated(["run_id", "stop_id"]).any()
    assert list(run_level.columns) == views.RUN_LEVEL_COLUMNS


@needs_getpatterns
def test_corridor_minutes_match_mansueto_medians(run_level):
    from cta.michigan_ave_segment import trip_segment_minutes

    kept = pd.DataFrame(json.loads(KEPT_PIDS.read_text())["pids"])
    kept["pid"] = kept["pid"].astype(str)
    legacy = run_level.rename(
        columns={"run_id": "unique_trip_vehicle_day", "stop_id": "stpid", "arrival_time": "bus_stop_time"}
    )
    checked = 0
    for rec in kept.itertuples(index=False):
        sub = legacy[legacy["pattern_id"] == rec.pid]
        minutes = trip_segment_minutes(sub, rec.entry_stpid, rec.exit_stpid)
        if len(minutes) < MIN_RUNS_FOR_RATIO:
            continue
        ratio = float(np.median(minutes)) / float(rec.median_minutes)
        assert abs(ratio - 1.0) <= MAX_MEDIAN_RATIO_DEVIATION, (rec.pid, rec.route, rec.rtdir, ratio, len(minutes))
        checked += 1
    assert checked >= 10
