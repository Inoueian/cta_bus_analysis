"""Acceptance tests for specs/qa-skill.md: fixture QA tables against the committed baseline. Offline.

No count is hard-coded here: the numbers live in tests/fixtures/qa_baseline.csv alone, and
``test_baseline_matches_fixtures`` is the test that fails when a threshold or exclusion moves.
"""

from __future__ import annotations

import pandas as pd
import pytest

from cta import archive, mansueto, qa_baseline
from cta.qa import QA_COLUMNS

COLUMNS = ["case", "key"] + QA_COLUMNS


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(*args, **kwargs):
        raise AssertionError(f"network call attempted in tests: {args[:1]}")

    monkeypatch.setattr(archive, "run_curl", _refuse)
    for name in ("http_head", "http_range", "download", "_request"):
        monkeypatch.setattr(mansueto, name, _refuse)


@pytest.fixture(scope="module")
def baseline() -> pd.DataFrame:
    return qa_baseline.read_baseline(qa_baseline.BASELINE_PATH)


def test_fixture_qa_schema(baseline):
    assert baseline.loc[baseline["case"] == "mansueto_6410", "key"].map(type).eq(str).all()
    assert set(baseline.loc[baseline["case"] == "mansueto_6410", "key"]) == {"6410"}
    assert baseline["reason"].map(type).eq(str).all() and (baseline["reason"] == "").any()
    for case in qa_baseline.FIXTURE_CASES:
        got = qa_baseline.fixture_qa(case)
        assert list(got.columns) == COLUMNS, case
        assert (got["case"] == case).all()
        assert got["key"].map(type).eq(str).all(), case
        assert got["reason"].notna().all() and got["reason"].map(type).eq(str).all(), case
        for col in ("rows_in", "rows_out", "count"):
            assert got[col].dtype == "int64", (case, col)
        assert len(got) == int((baseline["case"] == case).sum()), case


def test_baseline_matches_fixtures(baseline):
    assert list(baseline.columns) == COLUMNS
    assert list(dict.fromkeys(baseline["case"])) == list(qa_baseline.FIXTURE_CASES)
    for case in qa_baseline.FIXTURE_CASES:
        diff = qa_baseline.diff_qa(qa_baseline.fixture_qa(case), baseline[baseline["case"] == case])
        assert diff.empty, f"QA table of case {case} moved; see .claude/skills/qa/SKILL.md\n{diff.to_string(index=False)}"
    for (case, key, stage), g in baseline.groupby(["case", "key", "stage"]):
        assert g["rows_in"].nunique() == 1 and g["rows_out"].nunique() == 1, (case, key, stage)
        assert int(g["count"].sum()) == int(g["rows_in"].iloc[0] - g["rows_out"].iloc[0]), (case, key, stage)


def _table(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=COLUMNS)


def test_diff_qa_reports_each_kind():
    base = _table([
        ("c", "k", "s1", 10, 7, "a", 2),
        ("c", "k", "s1", 10, 7, "b", 1),
        ("c", "k", "s2", 7, 7, "", 0),
    ])
    observed = _table([
        ("c", "k", "s1", 10, 7, "a", 3),  # changed count
        ("c", "k", "s2", 7, 7, "", 0),
        ("c", "k", "s3", 7, 6, "z", 1),  # only observed; s1/b is only in the baseline
    ])
    diff = qa_baseline.diff_qa(observed, base)
    assert list(diff.columns) == qa_baseline.DIFF_COLUMNS
    got = {(r.stage, r.reason, r.field) for r in diff.itertuples()}
    assert got == {("s1", "a", "count"), ("s1", "b", "missing_row"), ("s3", "z", "new_row")}
    changed = diff[diff["field"] == "count"].iloc[0]
    assert (int(changed["baseline"]), int(changed["observed"])) == (2, 3)

    assert qa_baseline.diff_qa(base.iloc[::-1].reset_index(drop=True), base).empty
