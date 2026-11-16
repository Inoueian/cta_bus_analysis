"""Shared QA arithmetic: the five QA columns, the per-stage row builder and the sum over calls (specs/qa-helper.md).

Every pipeline stage reports rows in, rows out and one reason per dropped row, so reason counts sum to
rows_in - rows_out. ``qa_rows`` builds and checks the rows of one stage; ``stage_totals`` sums a per-call
QA table (one call per pid and year, or per day) and checks the same identity on the sums.

This module imports nothing from ``cta``: every source module imports it.
"""

from __future__ import annotations

import pandas as pd

QA_COLUMNS = ["stage", "rows_in", "rows_out", "reason", "count"]


def qa_rows(stage: str, rows_in: int, rows_out: int, reasons: dict[str, int]) -> list[dict]:
    """QA rows for one stage, one per non-zero reason (one ``None`` row when nothing was dropped). Asserts additivity."""
    items = [(r, int(c)) for r, c in reasons.items() if int(c) != 0] or [(None, 0)]
    total = sum(c for _, c in items)
    if total != rows_in - rows_out:
        raise AssertionError(f"QA stage {stage}: reasons sum to {total}, expected {rows_in - rows_out}")
    return [{"stage": stage, "rows_in": int(rows_in), "rows_out": int(rows_out), "reason": r, "count": c} for r, c in items]


def stage_totals(qa: pd.DataFrame, by: list[str], call_keys: list[str]) -> pd.DataFrame:
    """Sum a per-call QA table over calls: rows in/out per stage and one column per reason; asserts additivity.

    ``call_keys`` identify one adapter call (pid and year, or day); ``by`` is the grouping to report.
    """
    stage = qa.drop_duplicates(call_keys + ["stage"]).groupby(by + ["stage"], sort=False)[["rows_in", "rows_out"]].sum()
    reasons = qa.dropna(subset=["reason"]).pivot_table(index=by + ["stage"], columns="reason", values="count", aggfunc="sum", fill_value=0)
    out = stage.join(reasons).fillna(0).astype("int64")
    reason_cols = [c for c in out.columns if c not in ("rows_in", "rows_out")]
    if not ((out["rows_in"] - out["rows_out"]) == out[reason_cols].sum(axis=1)).all():
        raise AssertionError("QA reasons do not sum to rows dropped")
    return out
