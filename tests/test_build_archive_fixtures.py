"""Tests for scripts.build_archive_fixtures (no network; the builder itself is run by hand)."""

from __future__ import annotations

from pathlib import Path

from scripts.build_archive_fixtures import getpatterns_to_write


def test_getpatterns_keeps_committed_files(tmp_path: Path):
    (tmp_path / "getpatterns_1.json").write_text("{}")
    assert getpatterns_to_write(["1", "2", "3"], tmp_path, refresh=False) == ["2", "3"]


def test_getpatterns_refresh_rewrites_every_pid(tmp_path: Path):
    (tmp_path / "getpatterns_1.json").write_text("{}")
    assert getpatterns_to_write(["1", "2"], tmp_path, refresh=True) == ["1", "2"]


def test_getpatterns_nothing_to_write_when_all_committed(tmp_path: Path):
    for p in ("1", "2"):
        (tmp_path / f"getpatterns_{p}.json").write_text("{}")
    assert getpatterns_to_write(["1", "2"], tmp_path, refresh=False) == []
