"""Calendar facts in one place: CTA holidays, archive ``known_gaps`` windows, declared source coverage
and Mansueto freshness (specs/archive-adapter.md, specs/calendar-module.md, ADR-007, ADR-009).

Rows are flagged, never dropped, by the views (ADR-004 consequences; specs/archive-adapter.md
Method 7). The one exception is a consecutive-fix pair that spans a known gap, which
``cta.archive.fix_pairs`` drops and counts, because no arrival can be interpolated across it.

Holiday list: CTA runs a Sunday schedule on the six holidays below (knowledge-vault note
``cta-holiday-schedule-filtering``; migration to docs/ pending).

Source coverage: ``source_coverage`` declares which service dates each source covers, from the constants
below (the archive's upper edge and whole-day gaps from a passed ``index``); ``calendar_flag(..., source=)``
adds ``coverage_gap`` to rows outside it and ``coverage_days`` builds a (service date, source) spine with a
QA table, so a chart can tell "no buses" from "no data". ``_coverage_reason`` alone decides coverage.

Freshness: ``source_freshness`` reads the download metadata that ``cta.mansueto.fetch_parquet`` and
``cta.mansueto_raw.fetch_day`` write (JSON only: no network, no parquet, no write) and says whether a frozen
Mansueto source has moved past its declared edge. ``moved`` means "re-measure and reopen ADR-007 / ADR-009";
the constants change only through CLAUDE.md Rule 2.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from cta import mansueto, mansueto_raw

CHICAGO = ZoneInfo("America/Chicago")

FLAG_KNOWN_GAP_DAY = "known_gap_day"  # service date overlaps an archive known_gaps window for the bus feed
FLAG_HOLIDAY_PREFIX = "holiday:"
FLAG_COVERAGE_GAP = "coverage_gap"  # service date outside the row's source coverage (specs/calendar-module.md)
FLAG_SEPARATOR = ";"

SOURCE_MANSUETO = mansueto.SOURCE_MANSUETO
SOURCE_MANSUETO_RAW = mansueto_raw.SOURCE_MANSUETO_RAW
SOURCE_ARCHIVE = "archive"  # same as cta.views.SOURCE_ARCHIVE (views imports this module)
SOURCES = (SOURCE_MANSUETO, SOURCE_MANSUETO_RAW, SOURCE_ARCHIVE)

# The parquet edge itself is cta.mansueto.MANSUETO_DATA_EDGE (ADR-007), read at call time; the edge day is a gap.
MANSUETO_FIRST_DAY = None  # open: parquets start per pid (2022-05-31 for 6414, 2022-08-21 for 18414); owner, 2026-11-12
MANSUETO_RAW_FIRST_DAY = "2026-08-13"  # HEAD sweep 2026-11-06, ADR-009 bound; earlier files exist but are outside the declared window
MANSUETO_RAW_EDGE = "2026-10-27"  # same sweep: nothing since 2026-10-28 (ADR-009, docs/2026-11-06-mansueto-raw-positions.md)
MANSUETO_RAW_MISSING_DAYS = ("2026-09-30", "2026-10-02", "2026-10-03", "2026-10-16", "2026-10-17")  # same sweep: 25 of 30 present
ARCHIVE_FIRST_DAY = "2026-09-28"  # archive index.json first day (ADR-004, ADR-007); last day and whole-day gaps come from the index

REASON_BEFORE_FIRST_DAY = "before_first_day"
REASON_AFTER_EDGE = "after_edge"
REASON_MISSING_DAY_FILE = "missing_day_file"
COVERAGE_REASONS = (REASON_BEFORE_FIRST_DAY, REASON_AFTER_EDGE, REASON_MISSING_DAY_FILE)  # priority order
COVERAGE_STAGE = "coverage"
COVERAGE_COLUMNS = ["source", "first_day", "last_day", "missing_days", "evidence"]
COVERAGE_DAY_COLUMNS = ["service_date", "source", "covered", "reason", "calendar_flag"]
COVERAGE_QA_COLUMNS = ["source"] + mansueto.QA_COLUMNS  # shape of cta.views.MANSUETO_QA_COLUMNS

STATUS_NOT_MOVED = "not_moved"
STATUS_MOVED = "moved"
STATUS_NO_METADATA = "no_metadata"
FRESHNESS_COLUMNS = ["source", "declared_edge", "observed_edge", "newest_last_modified", "oldest_fetched_at", "files", "status"]
_RAW_META_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.meta\.json$")

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


def calendar_flag(service_date: pd.Series, *, index: dict | None = None, source: str | None = None) -> pd.Series:
    """Flag per service date: '' (nothing), 'holiday:<name>', 'known_gap_day', 'coverage_gap', joined by ';'.

    ``coverage_gap`` is added only when ``source`` is given and the date is outside that source's declared
    coverage (``source_coverage``); ``source=None`` gives the holiday and known-gap flags alone.
    """
    if source is not None:
        _window(source, index)  # unknown source raises even on an empty series
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
        if source is not None and _coverage_reason(source, key[:10], index):
            parts.append(FLAG_COVERAGE_GAP)
        cache[key] = FLAG_SEPARATOR.join(parts)
        return cache[key]

    return service_date.map(flag_for).astype(str)


# --- declared source coverage ----------------------------------------------------------------------


def _day_before(day: str) -> str:
    return (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()


def _archive_listed_days(index: dict | None) -> list[str]:
    """Index days that have a bus day file, sorted."""
    return sorted(
        str(d["date"]) for d in (index or {}).get("days", []) or [] if (d.get("files") or {}).get("bus")
    )


def _window(source: str, index: dict | None = None) -> tuple[str | None, str | None, tuple[str, ...]]:
    """(first_day, last_day, missing_days) of ``source``; inclusive ISO dates, None = open. Built at call time."""
    if source == SOURCE_MANSUETO:
        return MANSUETO_FIRST_DAY, _day_before(mansueto.MANSUETO_DATA_EDGE), ()
    if source == SOURCE_MANSUETO_RAW:
        return MANSUETO_RAW_FIRST_DAY, MANSUETO_RAW_EDGE, tuple(MANSUETO_RAW_MISSING_DAYS)
    if source == SOURCE_ARCHIVE:
        listed = _archive_listed_days(index)
        if not listed:
            return ARCHIVE_FIRST_DAY, None, ()
        # The index speaks only for its first..last listed day (Method 3): earlier days are not claimed missing.
        listed_set = set(listed)
        span = pd.date_range(max(listed[0], ARCHIVE_FIRST_DAY), listed[-1]) if listed[-1] >= ARCHIVE_FIRST_DAY else []
        missing = tuple(str(d.date()) for d in span if str(d.date()) not in listed_set)
        return ARCHIVE_FIRST_DAY, listed[-1], missing
    raise ValueError(f"unknown source {source!r}; expected one of {SOURCES}")


def _coverage_reason(source: str, day: str, index: dict | None = None) -> str:
    """'' when ``source`` covers service date ``day``, else the first of ``COVERAGE_REASONS`` that applies."""
    first, last, missing = _window(source, index)
    day = str(day)[:10]
    if first is not None and day < first:
        return REASON_BEFORE_FIRST_DAY
    if last is not None and day > last:
        return REASON_AFTER_EDGE
    if day in missing:
        return REASON_MISSING_DAY_FILE
    return ""


_EVIDENCE = {
    SOURCE_MANSUETO: "ADR-007: parquet footers frozen at MANSUETO_DATA_EDGE (probe 2026-11-04); the edge day is a gap",
    SOURCE_MANSUETO_RAW: "ADR-009: HEAD sweep 2026-11-06, docs/2026-11-06-mansueto-raw-positions.md",
    SOURCE_ARCHIVE: "ADR-004, ADR-007: index.json first day; last day and whole-day gaps from the passed index",
}


def source_coverage(index: dict | None = None) -> pd.DataFrame:
    """Declared coverage, one row per source: first_day, last_day (inclusive, None = open), missing_days, evidence.

    ``index`` (``cta.archive.fetch_index``) sets the archive's last day and whole-day gaps; it never affects
    the two Mansueto sources.
    """
    rows = []
    for source in SOURCES:
        first, last, missing = _window(source, index)
        rows.append({"source": source, "first_day": first, "last_day": last, "missing_days": missing, "evidence": _EVIDENCE[source]})
    return pd.DataFrame({c: pd.Series([r[c] for r in rows], dtype=object) for c in COVERAGE_COLUMNS})  # None stays None


def coverage_days(start, end, *, sources=None, index: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per (service date, source) from ``start`` to ``end`` inclusive, and its QA table.

    Columns ``service_date``, ``source``, ``covered``, ``reason`` ('' when covered), ``calendar_flag``. The
    QA table has one stage, ``coverage``: rows are days, ``rows_out`` the covered days, one row per reason.
    """
    sources = list(sources) if sources is not None else list(SOURCES)
    days = [str(d.date()) for d in pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="D")]
    frames, qa = [], []
    for source in sources:
        reasons = [_coverage_reason(source, d, index) for d in days]
        source_index = index if source == SOURCE_ARCHIVE else None  # archive known_gaps are not Mansueto outages
        frame = pd.DataFrame({"service_date": days, "source": source, "reason": reasons})
        frame["covered"] = frame["reason"] == ""
        frame["calendar_flag"] = calendar_flag(frame["service_date"], index=source_index, source=source)
        frames.append(frame)
        counts = Counter(r for r in reasons if r)
        covered = len(days) - sum(counts.values())
        for row in mansueto.qa_rows(COVERAGE_STAGE, len(days), covered, {r: counts.get(r, 0) for r in COVERAGE_REASONS}):
            qa.append({"source": source, **row})
    if frames:
        out = pd.concat(frames, ignore_index=True)
        out = out.sort_values(["service_date"], kind="stable").reset_index(drop=True)
    else:
        out = pd.DataFrame({c: pd.Series(dtype="object") for c in COVERAGE_DAY_COLUMNS})
    qa_table = pd.DataFrame(qa, columns=COVERAGE_QA_COLUMNS)
    for c in ("rows_in", "rows_out", "count"):
        qa_table[c] = qa_table[c].astype("int64")
    return out[COVERAGE_DAY_COLUMNS], qa_table


# --- Mansueto freshness ----------------------------------------------------------------------------


def _utc(value) -> pd.Timestamp:
    if value is None or value == "":
        return pd.NaT
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def freshness_status(source: str, records: list[dict]) -> dict:
    """Freshness of one frozen Mansueto source from its download or probe records (one Freshness row).

    ``mansueto`` records are ``cta.mansueto.data_edge`` dicts (``max_bus_stop_time`` is naive Chicago wall
    time, read as a date, never localized as UTC); ``mansueto_raw`` records have ``day`` and ``last_modified``.
    ``fetched_at`` is optional. No records gives ``no_metadata``.
    """
    records = list(records)
    if source == SOURCE_MANSUETO:
        declared = mansueto.MANSUETO_DATA_EDGE
        edges = [str(r["max_bus_stop_time"])[:10] for r in records if r.get("max_bus_stop_time")]
        observed = max(edges) if edges else None
        modified_days = [str(r["last_modified"])[:10] for r in records if r.get("last_modified")]
        moved = (observed is not None and observed > declared) or any(d > declared for d in modified_days)
    elif source == SOURCE_MANSUETO_RAW:
        declared = MANSUETO_RAW_EDGE
        days = [str(r["day"])[:10] for r in records]
        observed = max(days) if days else None
        # fetch_day writes metadata only after a download, so a declared-missing day here came back.
        moved = (observed is not None and observed > declared) or any(d in MANSUETO_RAW_MISSING_DAYS for d in days)
    else:
        raise ValueError(f"no freshness rule for source {source!r}; expected {SOURCE_MANSUETO!r} or {SOURCE_MANSUETO_RAW!r}")
    modified = [t for t in (_utc(r.get("last_modified")) for r in records) if not pd.isna(t)]
    fetched = [t for t in (_utc(r.get("fetched_at")) for r in records) if not pd.isna(t)]
    if not records:
        status = STATUS_NO_METADATA
    else:
        status = STATUS_MOVED if moved else STATUS_NOT_MOVED
    return {
        "source": source,
        "declared_edge": declared,
        "observed_edge": observed if records else None,
        "newest_last_modified": max(modified) if modified else pd.NaT,
        "oldest_fetched_at": min(fetched) if fetched else pd.NaT,
        "files": len(records),
        "status": status,
    }


def _parquet_records(parquet_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(Path(parquet_dir).glob("trips_*_full.meta.json"))]


def _raw_records(raw_dir: Path) -> list[dict]:
    out = []
    for p in sorted(Path(raw_dir).glob("*.meta.json")):
        m = _RAW_META_NAME.match(p.name)
        if m:
            out.append({**json.loads(p.read_text()), "day": m.group(1)})
    return out


def source_freshness(*, parquet_dir: Path | None = None, raw_dir: Path | None = None) -> pd.DataFrame:
    """One Freshness row per directory passed: ``mansueto`` from ``trips_<pid>_full.meta.json`` under
    ``parquet_dir``, ``mansueto_raw`` from ``YYYY-MM-DD.meta.json`` under ``raw_dir``. Reads JSON only."""
    rows = []
    if parquet_dir is not None:
        rows.append(freshness_status(SOURCE_MANSUETO, _parquet_records(parquet_dir)))
    if raw_dir is not None:
        rows.append(freshness_status(SOURCE_MANSUETO_RAW, _raw_records(raw_dir)))
    out = pd.DataFrame(rows, columns=FRESHNESS_COLUMNS)
    for c in ("newest_last_modified", "oldest_fetched_at"):
        out[c] = pd.to_datetime(out[c], utc=True)
    out["files"] = out["files"].astype("int64")
    out["observed_edge"] = pd.Series([r["observed_edge"] for r in rows], dtype=object)  # None stays None
    return out
