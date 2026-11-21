"""Acceptance tests for specs/qa-helper.md: one owner for the QA arithmetic (``cta.qa``), old names as aliases.

Offline. No test hard-codes a QA count from a fixture; those belong to the /qa baseline (specs/qa-skill.md).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from cta import archive, bustracker, mansueto, qa, views
from scripts import route_run_level as rrl

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ONE_DAY = FIXTURES / "mansueto_2026-07-27_route3.parquet"
GETPATTERNS_DIR = FIXTURES / "getpatterns"
ONE_DAY_PIDS = ["18414", "18415"]
DAY = "2026-10-29"


def test_qa_rows_known_case():
    rows = qa.qa_rows("s", 10, 7, {"a": 2, "b": 1, "c": 0})
    assert [(r["reason"], r["count"]) for r in rows] == [("a", 2), ("b", 1)]
    for row in rows:
        assert list(row) == qa.QA_COLUMNS
        assert (row["stage"], row["rows_in"], row["rows_out"]) == ("s", 10, 7)

    assert qa.qa_rows("s", 5, 5, {}) == [{"stage": "s", "rows_in": 5, "rows_out": 5, "reason": None, "count": 0}]

    with pytest.raises(AssertionError):
        qa.qa_rows("s", 10, 7, {"a": 2})


def test_stage_totals_known_case():
    calls = [("2025", qa.qa_rows("s", 10, 7, {"a": 2, "b": 1})), ("2026", qa.qa_rows("s", 5, 5, {}))]
    table = pd.DataFrame([{"pid": "1", "year": year, **row} for year, rows in calls for row in rows])
    totals = qa.stage_totals(table, ["pid"], ["pid", "year"])

    assert len(totals) == 1
    assert totals.index.names == ["pid", "stage"]
    row = totals.loc[("1", "s")]
    assert (row["rows_in"], row["rows_out"], row["a"], row["b"]) == (15, 12, 2, 1)
    assert (totals.dtypes == "int64").all()

    bad = table.copy()
    bad.loc[bad["reason"] == "a", "count"] = 5
    with pytest.raises(AssertionError):
        qa.stage_totals(bad, ["pid"], ["pid", "year"])


def test_helper_has_one_name():
    # the aliases specs/qa-helper.md kept were removed by the TODO.md Foundation item "Re-point the importers of the QA helper"
    for module, name in ((mansueto, "qa_rows"), (mansueto, "QA_COLUMNS"), (archive, "QA_COLUMNS")):
        assert not hasattr(module, name), f"cta.{module.__name__.split('.')[-1]}.{name} is an alias of cta.qa again"
    assert rrl.stage_totals is qa.stage_totals


def test_qa_imports_nothing_from_cta():
    tree = ast.parse(Path(qa.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "cta" and not alias.name.startswith("cta."), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import"
            assert node.module != "cta" and not node.module.startswith("cta."), node.module


def test_record_qa_failed_check_leaves_table_untouched():
    con = archive.open_archive_db()
    try:
        archive._record_qa(con, DAY, "stage_x", 10, 7, {"a": 3})
        before = archive.qa(con, DAY)
        with pytest.raises(AssertionError) as err:
            archive._record_qa(con, DAY, "stage_x", 10, 7, {"a": 2})
        assert "stage_x" in str(err.value) and DAY in str(err.value)
        after = archive.qa(con, DAY)
    finally:
        con.close()
    assert len(before) == 1
    assert before.iloc[0].to_dict() == {"stage": "stage_x", "rows_in": 10, "rows_out": 7, "reason": "a", "count": 3}
    pd.testing.assert_frame_equal(after, before)


def test_stage_totals_on_route3_fixture():
    stops = bustracker.pattern_stops_table(ONE_DAY_PIDS, GETPATTERNS_DIR)
    view, qa_table = views.run_level_from_mansueto_with_qa(ONE_DAY_PIDS, parquet_dir=FIXTURES, pattern_stops=stops)
    totals = qa.stage_totals(qa_table, ["pid"], ["pid"])

    assert sorted(totals.index) == sorted((pid, stage) for pid in ONE_DAY_PIDS for stage in mansueto.STAGES)
    reason_cols = [c for c in totals.columns if c not in ("rows_in", "rows_out")]
    assert ((totals["rows_in"] - totals["rows_out"]) == totals[reason_cols].sum(axis=1)).all()
    rows_by_pid = view["pattern_id"].value_counts()
    for pid in ONE_DAY_PIDS:
        assert int(totals.loc[(pid, "order"), "rows_out"]) == int(rows_by_pid[pid])
