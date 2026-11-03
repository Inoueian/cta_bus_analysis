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
