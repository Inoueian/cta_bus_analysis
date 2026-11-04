"""Calendar exclusions in one place: CTA holidays and archive ``known_gaps`` windows.

Rows are flagged, never dropped, by the views (ADR-004 consequences; specs/archive-adapter.md
Method 7). The one exception is a consecutive-fix pair that spans a known gap, which
``cta.archive.fix_pairs`` drops and counts, because no arrival can be interpolated across it.

Holiday list: CTA runs a Sunday schedule on the six holidays below (knowledge-vault note
``cta-holiday-schedule-filtering``; migration to docs/ pending). Mansueto freshness is out of scope.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

CHICAGO = ZoneInfo("America/Chicago")

FLAG_KNOWN_GAP_DAY = "known_gap_day"  # service date overlaps an archive known_gaps window for the bus feed
FLAG_HOLIDAY_PREFIX = "holiday:"
FLAG_SEPARATOR = ";"

KNOWN_GAP_COLUMNS = ["start", "end", "feeds", "note"]


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-th (1-based) given weekday (Mon=0) of a month; n=-1 for the last one."""
    if n > 0:
        first = dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + dt.timedelta(days=offset + 7 * (n - 1))
    last = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1))
    offset = (last.weekday() - weekday) % 7
    return last - dt.timedelta(days=offset)


def cta_holidays(year: int) -> dict[dt.date, str]:
    """CTA Sunday-schedule holidays for a calendar year (observed on the day itself)."""
    return {
        dt.date(year, 1, 1): "New Year's Day",
        _nth_weekday(year, 5, 0, -1): "Memorial Day",
        dt.date(year, 7, 4): "Independence Day",
        _nth_weekday(year, 9, 0, 1): "Labor Day",
        _nth_weekday(year, 11, 3, 4): "Thanksgiving Day",
        dt.date(year, 12, 25): "Christmas Day",
    }


def known_gaps(index: dict | None, feed: str = "bus") -> pd.DataFrame:
    """Archive ``known_gaps`` windows that affect ``feed``, as tz-aware UTC start/end."""
    rows = []
    for g in (index or {}).get("known_gaps", []) or []:
        feeds = list(g.get("feeds") or [])
        if feed not in feeds:
            continue
        rows.append(
            {
                "start": pd.Timestamp(g["start"]).tz_convert("UTC"),
                "end": pd.Timestamp(g["end"]).tz_convert("UTC"),
                "feeds": feeds,
                "note": g.get("note", ""),
            }
        )
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in KNOWN_GAP_COLUMNS})
    return pd.DataFrame(rows, columns=KNOWN_GAP_COLUMNS)


def _service_day_bounds_utc(day: dt.date) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(dt.datetime.combine(day, dt.time(), CHICAGO)).tz_convert("UTC")
    end = pd.Timestamp(dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), CHICAGO)).tz_convert("UTC")
    return start, end


def calendar_flag(service_date: pd.Series, *, index: dict | None = None) -> pd.Series:
    """Flag per service date: '' (nothing), 'holiday:<name>', 'known_gap_day', joined by ';'."""
    gaps = known_gaps(index)
    years = {int(str(d)[:4]) for d in service_date.dropna().unique()}
    holidays: dict[dt.date, str] = {}
    for y in years:
        holidays.update(cta_holidays(y))

    cache: dict[str, str] = {}

    def flag_for(value) -> str:
        key = str(value)
        if key in cache:
            return cache[key]
        day = dt.date.fromisoformat(key[:10])
        parts: list[str] = []
        if day in holidays:
            parts.append(FLAG_HOLIDAY_PREFIX + holidays[day])
        if not gaps.empty:
            start, end = _service_day_bounds_utc(day)
            if bool(((gaps["start"] < end) & (gaps["end"] > start)).any()):
                parts.append(FLAG_KNOWN_GAP_DAY)
        cache[key] = FLAG_SEPARATOR.join(parts)
        return cache[key]

    return service_date.map(flag_for).astype(str)
