"""Tests for cta.calendar: CTA holidays and archive known_gaps windows."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from cta import calendar as cal

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DAY_INDEX = FIXTURES / "archive_2026-10-29_michigan.index.json"


def test_cta_holidays_2026():
    hol = cal.cta_holidays(2026)
    assert hol[dt.date(2026, 1, 1)] == "New Year's Day"
    assert hol[dt.date(2026, 5, 25)] == "Memorial Day"
    assert hol[dt.date(2026, 7, 4)] == "Independence Day"
    assert hol[dt.date(2026, 9, 7)] == "Labor Day"
    assert hol[dt.date(2026, 11, 26)] == "Thanksgiving Day"
    assert hol[dt.date(2026, 12, 25)] == "Christmas Day"
    assert len(hol) == 6


def test_known_gaps_are_tz_aware_utc_and_filtered_by_feed():
    index = json.loads(DAY_INDEX.read_text())
    gaps = cal.known_gaps(index)
    assert list(gaps.columns) == ["start", "end", "feeds", "note"]
    assert str(gaps["start"].dt.tz) == "UTC" and str(gaps["end"].dt.tz) == "UTC"
    assert (gaps["end"] > gaps["start"]).all()
    assert len(gaps) == len(index["known_gaps"])
    # 2026-10-22 15:37-05:00 == 20:37 UTC
    g = gaps[gaps["note"] == "No polls recorded"].iloc[0]
    assert g["start"] == pd.Timestamp("2026-10-22T20:37:00Z")
    train_only = cal.known_gaps({"known_gaps": [{"start": "2026-10-22T15:37-05:00", "end": "2026-10-22T15:48-05:00", "feeds": ["train"]}]})
    assert train_only.empty


def test_calendar_flag_marks_holidays_and_gap_days():
    index = json.loads(DAY_INDEX.read_text())
    dates = pd.Series(["2026-10-29", "2026-10-30", "2026-11-26", "2026-10-13"])
    flags = cal.calendar_flag(dates, index=index)
    assert flags.tolist() == ["", cal.FLAG_KNOWN_GAP_DAY, "holiday:Thanksgiving Day", cal.FLAG_KNOWN_GAP_DAY]


# --- specs/calendar-module.md: source coverage and Mansueto freshness ------------------------------

MANSUETO_MANIFEST = FIXTURES / "mansueto.manifest.json"
MANSUETO_RAW_MANIFEST = FIXTURES / "mansueto_raw.manifest.json"
RAW_MISSING = ("2026-09-30", "2026-10-02", "2026-10-03", "2026-10-16", "2026-10-17")
SPINE_START, SPINE_END = "2026-07-25", "2026-10-31"


def test_source_coverage_windows():
    cov = cal.source_coverage()
    assert list(cov.columns) == ["source", "first_day", "last_day", "missing_days", "evidence"]
    rows = {r.source: (r.first_day, r.last_day, r.missing_days) for r in cov.itertuples()}
    assert rows == {
        "mansueto": (None, "2026-07-27", ()),
        "mansueto_raw": ("2026-08-13", "2026-10-27", RAW_MISSING),
        "archive": ("2026-09-28", None, ()),
    }
    assert cov["evidence"].map(bool).all()


def test_coverage_days_known_case():
    days, _ = cal.coverage_days(SPINE_START, SPINE_END)
    assert list(days.columns) == ["service_date", "source", "covered", "reason", "calendar_flag"]
    assert len(days) == 297
    assert days.groupby("source")["covered"].sum().to_dict() == {"archive": 34, "mansueto": 3, "mansueto_raw": 71}
    by_day = days.groupby("service_date")["covered"]
    uncovered = sorted(d for d, any_cov in by_day.any().items() if not any_cov)
    assert len(uncovered) == 16
    assert uncovered == [str(d.date()) for d in pd.date_range("2026-07-28", "2026-08-12")]
    wide = days.pivot(index="service_date", columns="source", values="covered")
    assert int((wide["archive"] & wide["mansueto_raw"]).sum()) == 25
    labor = days[days["service_date"] == "2026-09-07"].set_index("source")["calendar_flag"].to_dict()
    assert labor == {
        "mansueto": "holiday:Labor Day;coverage_gap",
        "archive": "holiday:Labor Day;coverage_gap",
        "mansueto_raw": "holiday:Labor Day",
    }


def test_coverage_days_qa():
    days, qa = cal.coverage_days(SPINE_START, SPINE_END)
    assert list(qa.columns) == cal.COVERAGE_QA_COLUMNS
    assert (qa["stage"] == "coverage").all()
    expected = {
        "mansueto": {"after_edge": 96},
        "archive": {"before_first_day": 65},
        "mansueto_raw": {"before_first_day": 19, "missing_day_file": 5, "after_edge": 4},
    }
    for source, reasons in expected.items():
        q = qa[qa["source"] == source]
        assert (q["rows_in"] == 99).all(), source
        rows_out = int(days[(days["source"] == source)]["covered"].sum())
        assert (q["rows_out"] == rows_out).all(), source
        got = dict(zip(q["reason"], q["count"]))
        assert got == reasons, source
        assert sum(got.values()) == 99 - rows_out


def test_calendar_flag_coverage_gap():
    index = json.loads(DAY_INDEX.read_text())
    flag = cal.calendar_flag
    assert flag(pd.Series(["2026-07-27", "2026-07-28", "2026-07-04"]), source="mansueto").tolist() == [
        "", cal.FLAG_COVERAGE_GAP, "holiday:Independence Day"
    ]
    assert flag(pd.Series(["2026-10-16"]), source="mansueto_raw").tolist() == ["coverage_gap"]
    assert flag(pd.Series(["2026-09-27", "2026-10-16"]), source="archive").tolist() == ["coverage_gap", ""]
    assert flag(pd.Series(["2026-10-29"]), index=index, source="archive").tolist() == [""]
    assert flag(pd.Series(["2026-11-26"]), source="mansueto_raw").tolist() == ["holiday:Thanksgiving Day;coverage_gap"]
    try:
        flag(pd.Series(["2026-10-29"]), source="gtfs")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown source must raise ValueError")
    dates = pd.Series(["2026-10-29", "2026-10-30", "2026-11-26", "2026-10-13"])
    assert flag(dates, index=index, source=None).tolist() == flag(dates, index=index).tolist() == [
        "", cal.FLAG_KNOWN_GAP_DAY, "holiday:Thanksgiving Day", cal.FLAG_KNOWN_GAP_DAY
    ]


def _hand_index() -> dict:
    listed = [str(d.date()) for d in pd.date_range("2026-09-28", "2026-10-05") if str(d.date()) != "2026-10-02"]
    return {
        "known_gaps": [{"start": "2026-10-03T10:00-05:00", "end": "2026-10-03T10:30-05:00", "feeds": ["bus"], "note": "test"}],
        "days": [{"date": d, "files": {"bus": {"path": f"{d}.ndjson.gz"}}} for d in listed],
    }


def test_archive_coverage_from_index():
    index = _hand_index()
    days, qa = cal.coverage_days("2026-09-27", "2026-10-07", sources=["archive"], index=index)
    assert len(days) == 11
    assert int(days["covered"].sum()) == 7
    got = dict(zip(qa["reason"], qa["count"]))
    assert got == {"before_first_day": 1, "missing_day_file": 1, "after_edge": 2}
    assert sum(got.values()) == int(qa["rows_in"].iloc[0] - qa["rows_out"].iloc[0])
    assert days.loc[days["reason"] == "missing_day_file", "service_date"].tolist() == ["2026-10-02"]
    oct3 = days[days["service_date"] == "2026-10-03"].iloc[0]
    assert bool(oct3["covered"]) and oct3["calendar_flag"] == cal.FLAG_KNOWN_GAP_DAY
    arch = cal.source_coverage(index).set_index("source").loc["archive"]
    assert arch["last_day"] == "2026-10-05"
    assert arch["missing_days"] == ("2026-10-02",)
    with_index, qa_with = cal.coverage_days("2026-09-27", "2026-10-07", sources=["mansueto_raw"], index=index)
    without, qa_without = cal.coverage_days("2026-09-27", "2026-10-07", sources=["mansueto_raw"])
    pd.testing.assert_frame_equal(with_index, without)
    pd.testing.assert_frame_equal(qa_with, qa_without)


def _write_parquet_meta(directory: Path, pid: str, edge: dict, fetched_at: str | None = None) -> None:
    meta = {"pid": pid, **edge}
    if fetched_at:
        meta["fetched_at"] = fetched_at
    (directory / f"trips_{pid}_full.meta.json").write_text(json.dumps(meta))


def _write_raw_meta(directory: Path, day: str, last_modified: str, fetched_at: str | None = None) -> None:
    meta = {"url": f"https://example.invalid/{day}.csv", "last_modified": last_modified}
    if fetched_at:
        meta["fetched_at"] = fetched_at
    (directory / f"{day}.meta.json").write_text(json.dumps(meta))


def test_source_freshness_not_moved(tmp_path: Path):
    parquet_dir, raw_dir = tmp_path / "parquet", tmp_path / "raw"
    parquet_dir.mkdir()
    raw_dir.mkdir()
    man = json.loads(MANSUETO_MANIFEST.read_text())
    for pid, src in man["sources"].items():
        _write_parquet_meta(parquet_dir, pid, src["data_edge"], src["fetched_at"])
    raw = json.loads(MANSUETO_RAW_MANIFEST.read_text())
    for day, src in raw["sources"].items():
        _write_raw_meta(raw_dir, day, src["last_modified"], src["fetched_at"])

    fresh = cal.source_freshness(parquet_dir=parquet_dir, raw_dir=raw_dir).set_index("source")
    assert list(fresh.index) == ["mansueto", "mansueto_raw"]
    assert (fresh["status"] == "not_moved").all()
    assert fresh.loc["mansueto", "observed_edge"] == "2026-07-28"
    assert fresh.loc["mansueto", "files"] == 3
    assert fresh.loc["mansueto", "declared_edge"] == "2026-07-28"
    assert fresh.loc["mansueto_raw", "observed_edge"] == "2026-10-22"
    assert fresh.loc["mansueto_raw", "files"] == 1
    assert fresh.loc["mansueto_raw", "declared_edge"] == "2026-10-27"
    assert fresh["files"].dtype == "int64"
    for col in ("newest_last_modified", "oldest_fetched_at"):
        assert str(fresh[col].dt.tz) == "UTC", col
        assert fresh[col].notna().all(), col

    status = cal.freshness_status("mansueto", [src["data_edge"] for src in man["sources"].values()])
    assert status["status"] == "not_moved"
    assert status["observed_edge"] == "2026-07-28"
    assert pd.isna(status["oldest_fetched_at"])


def test_source_freshness_moved_and_empty(tmp_path: Path):
    old_edge = {"last_modified": "2026-07-28T10:11:52+00:00", "max_bus_stop_time": "2026-07-28T00:04:59"}

    def status_of(name: str, *, parquet: list | None = None, raw: list | None = None) -> pd.Series:
        d = tmp_path / name
        d.mkdir()
        if parquet is not None:
            for i, edge in enumerate(parquet):
                _write_parquet_meta(d, str(i), edge)
            return cal.source_freshness(parquet_dir=d).iloc[0]
        for day in raw:
            _write_raw_meta(d, day, "2026-10-23T10:00:00+00:00")
        return cal.source_freshness(raw_dir=d).iloc[0]

    assert status_of("p_edge", parquet=[old_edge, {**old_edge, "max_bus_stop_time": "2026-11-01T08:00:00"}])["status"] == "moved"
    assert status_of("p_lm", parquet=[{**old_edge, "last_modified": "2026-11-02T10:00:00+00:00"}])["status"] == "moved"
    assert status_of("r_edge", raw=["2026-10-22", "2026-10-28"])["status"] == "moved"
    assert status_of("r_missing", raw=["2026-10-02"])["status"] == "moved"

    empty = tmp_path / "empty"
    empty.mkdir()
    for kwargs in ({"parquet_dir": empty}, {"raw_dir": empty}):
        row = cal.source_freshness(**kwargs).iloc[0]
        assert row["status"] == "no_metadata"
        assert row["files"] == 0
        assert row["observed_edge"] is None
        assert pd.isna(row["newest_last_modified"]) and pd.isna(row["oldest_fetched_at"])
