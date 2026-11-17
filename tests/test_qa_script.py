"""Acceptance tests for specs/qa-skill.md: scripts/qa.py exit codes and --record. Offline; writes only under tmp_path."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cta import archive, mansueto, qa_baseline
from scripts import qa as qa_script

COMMITTED = qa_baseline.BASELINE_PATH


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch):
    def _refuse(*args, **kwargs):
        raise AssertionError(f"network call attempted in tests: {args[:1]}")

    monkeypatch.setattr(archive, "run_curl", _refuse)
    for name in ("http_head", "http_range", "download", "_request"):
        monkeypatch.setattr(mansueto, name, _refuse)


def test_script_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture):
    assert qa_script.main(["mansueto_6410"]) == 0
    out = capsys.readouterr().out
    assert "missing_row" not in out

    base = qa_baseline.read_baseline(COMMITTED)
    row = base.index[(base["case"] == "mansueto_6410") & (base["stage"] == "order")][0]
    base.loc[row, "count"] += 1
    edited = tmp_path / "edited.csv"
    qa_baseline.write_baseline(base, edited)

    assert qa_script.main(["mansueto_6410", "--baseline", str(edited)]) == 1
    out = capsys.readouterr().out
    diff_text = out[out.index("differs from"):]
    assert "mansueto_6410" in diff_text and "order" in diff_text and "count" in diff_text
    assert "missing_row" not in diff_text and "new_row" not in diff_text


def test_record_reproduces_baseline(tmp_path: Path):
    committed_bytes = COMMITTED.read_bytes()
    mtime = COMMITTED.stat().st_mtime_ns

    whole = tmp_path / "whole.csv"
    shutil.copy(COMMITTED, whole)
    assert qa_script.main(["--record", "--baseline", str(whole)]) == 0
    assert whole.read_bytes() == committed_bytes
    assert COMMITTED.stat().st_mtime_ns == mtime

    one = tmp_path / "one.csv"
    shutil.copy(COMMITTED, one)
    assert qa_script.main(["mansueto_6410", "--record", "--baseline", str(one)]) == 0
    assert one.read_bytes() == committed_bytes

    fresh = tmp_path / "new" / "fresh.csv"
    fresh.parent.mkdir()
    assert qa_script.main(["--record", "--baseline", str(fresh)]) == 0
    assert fresh.read_bytes() == committed_bytes
