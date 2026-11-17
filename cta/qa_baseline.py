"""Fixture QA tables against a committed baseline: the cases, the diff and the baseline file (specs/qa-skill.md).

A development tool tied to the repo checkout: every case reads ``tests/fixtures/`` and
``notebooks/michigan_ave_kept_pids.json``, so it works from a clone, not from an installed package.
``FIXTURE_CASES`` maps a case name to a callable returning the QA table its adapter produces on a
committed fixture; ``fixture_qa`` runs one and normalises it; ``diff_qa`` compares it with the rows of
``tests/fixtures/qa_baseline.csv``. ``scripts/qa.py`` is the CLI and the only writer of that file
(``--record``); ``tests/test_qa_baseline.py`` fails on any difference, which is how a threshold or
exclusion change becomes visible (CLAUDE.md Rule 2). A new adapter adds a case.

Nothing here touches the network or ``data/``: patterns come from ``tests/fixtures/getpatterns/`` by
explicit directory, never the local getpatterns cache, and the archive case reads the committed fixture index.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import pandas as pd

from cta import archive, bustracker, mansueto_raw, views
from cta.qa import QA_COLUMNS

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
GETPATTERNS_DIR = FIXTURES / "getpatterns"
KEPT_PIDS_FILE = REPO_ROOT / "notebooks" / "michigan_ave_kept_pids.json"
BASELINE_PATH = FIXTURES / "qa_baseline.csv"

ARCHIVE_DAY = "2026-10-29"
ARCHIVE_DAY_FILE = FIXTURES / f"archive_{ARCHIVE_DAY}_michigan.ndjson.gz"
ARCHIVE_DAY_INDEX = FIXTURES / f"archive_{ARCHIVE_DAY}_michigan.index.json"
ROUTE3_PIDS = ["18414", "18415"]  # on mansueto_2026-07-27_route3.parquet
PID_6410 = ["6410"]  # on mansueto_6410_last30d.parquet
RAW_DAY = "2026-10-22"  # mansueto_raw_2026-10-22_michigan.csv.gz

BASELINE_COLUMNS = ["case", "key"] + QA_COLUMNS
ROW_KEY = ["case", "key", "stage", "reason"]
COUNT_COLUMNS = ["rows_in", "rows_out", "count"]
DIFF_COLUMNS = ROW_KEY + ["field", "baseline", "observed"]
FIELD_MISSING_ROW = "missing_row"  # in the baseline, not observed; ``baseline`` holds its count
FIELD_NEW_ROW = "new_row"  # observed, not in the baseline; ``observed`` holds its count


def kept_pids() -> list[str]:
    """The 45 Michigan Ave kept pids, as strings."""
    return [str(r["pid"]) for r in json.loads(KEPT_PIDS_FILE.read_text())["pids"]]


# --- cases: each returns (QA table, name of its key column or None, key value when there is no column) ---


def _archive_case() -> pd.DataFrame:
    pids = kept_pids()
    index = json.loads(ARCHIVE_DAY_INDEX.read_text())
    con = archive.open_archive_db()
    try:
        archive.ingest_day(con, archive.day_file_meta(index, ARCHIVE_DAY), ARCHIVE_DAY_FILE)
        stops = bustracker.pattern_stops_table(pids, GETPATTERNS_DIR)
        views.run_level_from_archive([ARCHIVE_DAY], pids, con=con, index=index, pattern_stops=stops)
        return archive.qa(con, ARCHIVE_DAY).assign(key=ARCHIVE_DAY)
    finally:
        con.close()


def _mansueto_case(pids: list[str]) -> pd.DataFrame:
    stops = bustracker.pattern_stops_table(pids, GETPATTERNS_DIR)
    _, qa = views.run_level_from_mansueto_with_qa(pids, parquet_dir=FIXTURES, pattern_stops=stops)
    return qa.rename(columns={"pid": "key"})


def _mansueto_raw_case() -> pd.DataFrame:
    pids = kept_pids()
    stops = bustracker.pattern_stops_table(pids, GETPATTERNS_DIR)
    con = mansueto_raw.open_db()  # its own connection: check_db refuses one shared with archive days
    try:
        _, qa = views.run_level_from_mansueto_raw_with_qa([RAW_DAY], pids, csv_dir=FIXTURES, pattern_stops=stops, con=con)
    finally:
        con.close()
    return qa.rename(columns={"day": "key"})


FIXTURE_CASES = {
    "archive": _archive_case,
    "mansueto_route3": functools.partial(_mansueto_case, ROUTE3_PIDS),
    "mansueto_6410": functools.partial(_mansueto_case, PID_6410),
    "mansueto_raw": _mansueto_raw_case,
}


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """``BASELINE_COLUMNS`` with string keys, ``reason`` None as ``""`` and int64 counts; row order kept."""
    out = df.reset_index(drop=True).copy()
    for col in ("case", "key", "stage"):
        out[col] = out[col].astype(str)
    out["reason"] = out["reason"].astype(object).where(out["reason"].notna(), "").astype(str)
    for col in COUNT_COLUMNS:
        out[col] = out[col].astype("int64")
    return out[BASELINE_COLUMNS]


@functools.lru_cache(maxsize=None)
def _fixture_qa(name: str) -> pd.DataFrame:
    return _normalise(FIXTURE_CASES[name]().assign(case=name))


def fixture_qa(name: str) -> pd.DataFrame:
    """QA table of one case on its committed fixture, one row per (case, key, stage, reason), in the adapter's order.

    Each case runs once per session; a copy is returned.
    """
    if name not in FIXTURE_CASES:
        raise KeyError(f"unknown QA case {name!r}; cases: {list(FIXTURE_CASES)}")
    return _fixture_qa(name).copy()


def empty_baseline() -> pd.DataFrame:
    return _normalise(pd.DataFrame({c: pd.Series(dtype="object") for c in BASELINE_COLUMNS}))


def read_baseline(path: Path = BASELINE_PATH) -> pd.DataFrame:
    """The baseline CSV with keys and reasons as strings (``6410`` stays ``"6410"``, ``""`` stays ``""``)."""
    df = pd.read_csv(path, dtype={c: str for c in ROW_KEY}, keep_default_na=False)
    if list(df.columns) != BASELINE_COLUMNS:
        raise ValueError(f"{path}: columns {list(df.columns)}, expected {BASELINE_COLUMNS}")
    return _normalise(df)


def write_baseline(df: pd.DataFrame, path: Path = BASELINE_PATH) -> None:
    """Write ``df`` as the baseline CSV (``\\n`` line ends). Only ``scripts/qa.py --record`` writes the committed file."""
    _normalise(df).to_csv(path, index=False, lineterminator="\n")


def diff_qa(observed: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """One row per differing cell between two QA tables, matched on (case, key, stage, reason); empty when equal.

    ``field`` is ``rows_in``, ``rows_out`` or ``count`` for a changed number, ``missing_row`` for a row only
    in ``baseline`` and ``new_row`` for a row only in ``observed`` (the count on the side that has it).
    It compares exactly the rows it is given: callers filter the baseline by case. Row order is ignored.
    """
    obs, base = _normalise(observed), _normalise(baseline)
    for name, table in (("observed", obs), ("baseline", base)):
        if table.duplicated(ROW_KEY).any():
            raise ValueError(f"{name} QA table repeats a (case, key, stage, reason) row")
    both = base.merge(obs, on=ROW_KEY, how="outer", suffixes=("_base", "_obs"), indicator=True, sort=False)
    rows = []
    for r in both.to_dict("records"):
        key = [r[c] for c in ROW_KEY]
        if r["_merge"] == "left_only":
            rows.append(key + [FIELD_MISSING_ROW, int(r["count_base"]), pd.NA])
        elif r["_merge"] == "right_only":
            rows.append(key + [FIELD_NEW_ROW, pd.NA, int(r["count_obs"])])
        else:
            rows += [key + [c, int(r[f"{c}_base"]), int(r[f"{c}_obs"])] for c in COUNT_COLUMNS if r[f"{c}_base"] != r[f"{c}_obs"]]
    out = pd.DataFrame(rows, columns=DIFF_COLUMNS)
    for col in ("baseline", "observed"):
        out[col] = out[col].astype("Int64")
    return out
