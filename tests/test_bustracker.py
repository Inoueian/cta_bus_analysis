"""Tests for cta/bustracker.py: the six tests from the former tests/test_cta_api.py (module reference
changed only) plus the acceptance tests of specs/split-cta-api.md."""

from __future__ import annotations

import importlib
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from cta import bustracker

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
GETPATTERNS_DIR = FIXTURES / "getpatterns"
KEPT = [str(r["pid"]) for r in json.loads((REPO_ROOT / "notebooks" / "michigan_ave_kept_pids.json").read_text())["pids"]]

# ---------------------------------------------------------------------------------------------
# The six tests from tests/test_cta_api.py (acceptance 6), `cta_api` -> `bustracker` only.
# test_parquet_url_basic moved to tests/test_mansueto.py.
# ---------------------------------------------------------------------------------------------


def test_module_imports():
    from cta import bustracker as _m  # noqa: F401


def test_ptr_to_stops_df_filters_waypoints_and_sorts():
    ptr = {
        "rtdir": "Northbound",
        "pt": [
            {"typ": "W", "seq": 1, "stpid": "1", "stpnm": "wp", "lat": 0, "lon": 0},
            {"typ": "S", "seq": 2, "stpid": "99", "stpnm": "Michigan & Roosevelt", "lat": 41.87, "lon": -87.62, "pdist": 100},
            {"typ": "S", "seq": 3, "stpid": "100", "stpnm": "Michigan & Ida B Wells", "lat": 41.88, "lon": -87.62, "pdist": 500},
        ],
    }
    df = bustracker.ptr_to_stops_df(ptr)
    assert len(df) == 2
    assert list(df["seq"]) == [2, 3]
    assert df.iloc[0]["stpid"] == "99"


def test_daily_counter_increments_and_resets_by_date(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    today = bustracker._chicago_today()
    bustracker._save_request_log(cache_dir, {"date": today, "count": 0})

    assert bustracker.daily_api_request_count(cache_dir) == 0
    bustracker._increment_daily_counter(cache_dir)
    assert bustracker.daily_api_request_count(cache_dir) == 1

    yesterday = "2000-01-01"
    bustracker._save_request_log(cache_dir, {"date": yesterday, "count": 999})
    assert bustracker.daily_api_request_count(cache_dir) == 0


def test_cta_api_get_throttles_between_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("CTA_API_KEY", "test-key")
    monkeypatch.setattr(bustracker, "_last_api_call_monotonic", 1000.0)

    times = iter([1000.0, 1000.0, 1000.1, 1000.1, 1000.1, 1000.1])
    monkeypatch.setattr(bustracker.time, "monotonic", lambda: next(times, 1000.1))
    sleeps: list[float] = []
    monkeypatch.setattr(bustracker.time, "sleep", lambda s: sleeps.append(s))

    payload = json.dumps({"bustime-response": {"ptr": []}}).encode()

    def fake_urlopen(req, timeout=60):
        class Resp:
            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return Resp()

    monkeypatch.setattr(bustracker.urllib.request, "urlopen", fake_urlopen)

    bustracker.cta_api_get("getpatterns", pid="1", cache_dir=cache_dir)
    bustracker.cta_api_get("getpatterns", pid="2", cache_dir=cache_dir)

    assert sleeps, "expected throttle sleep before second live API call"
    assert sleeps[0] >= bustracker.CTA_API_MIN_INTERVAL_SEC - 0.1


def test_batch_pattern_stops_uses_cache_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cache_dir = tmp_path / "cache"
    pid = "4509"
    root = {"ptr": [{"pid": pid, "rtdir": "Northbound", "pt": [{"typ": "S", "seq": 1, "stpid": "1", "stpnm": "A", "lat": 0, "lon": 0, "pdist": 0}]}]}
    bustracker._save_getpatterns_cache(pid, cache_dir, root)

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("urlopen should not run on cache hit")

    monkeypatch.setattr(bustracker.urllib.request, "urlopen", fail_urlopen)

    result = bustracker.batch_pattern_stops([pid], use_cache=True, cache_dir=cache_dir, progress_every=0)
    assert pid in result
    assert result[pid][0] == "Northbound"
    assert len(result[pid][1]) == 1


# ---------------------------------------------------------------------------------------------
# Acceptance tests, specs/split-cta-api.md.
# ---------------------------------------------------------------------------------------------

# Pre-split signatures, hand-copied from cta/cta_api.py and cta/patterns.py at HEAD 12f0aeb
# (`inspect.signature` strings; annotations are strings because both modules use
# `from __future__ import annotations`).
BUSTRACKER_CONSTANTS = [
    "CHICAGO",
    "CTA_API_BASE",
    "CTA_API_MIN_INTERVAL_SEC",
    "CTA_API_DAILY_WARN",
    "CTA_API_DAILY_MAX",
    "CTA_API_MAX_RETRIES",
    "CTA_API_RETRY_BASE_SEC",
    "LAST_CTA_REQUEST_URL",
    "PATTERN_STOP_COLUMNS",
]
BUSTRACKER_SIGNATURES = {
    "repo_root": "() -> 'Path'",
    "api_cache_dir": "() -> 'Path'",
    "load_dotenv": "(env_path: 'Path | None' = None) -> 'None'",
    "daily_api_request_count": "(cache_dir: 'Path | None' = None) -> 'int'",
    "cta_api_get": "(endpoint: 'str', *, allow_over_budget: 'bool' = False, cache_dir: 'Path | None' = None, **params: 'str') -> 'dict'",
    "ptr_to_stops_df": "(ptr: 'dict') -> 'pd.DataFrame'",
    "pattern_stops_from_ptr": "(ptr: 'dict') -> 'tuple[str, pd.DataFrame]'",
    "pattern_records": "(pid: 'str', **cta_kwargs) -> 'list[dict]'",
    "batch_pattern_stops": "(pids: 'list[str]', *, use_cache: 'bool' = True, cache_dir: 'Path | None' = None, max_requests: 'int | None' = None, allow_over_budget: 'bool' = False, progress_every: 'int' = 10) -> 'dict[str, tuple[str, pd.DataFrame]]'",
    "default_cache_dir": "() -> 'Path'",
    "cache_path": "(pid: 'str', cache_dir: 'Path') -> 'Path'",
    "load_getpatterns": "(pid: 'str', cache_dir: 'Path | None' = None) -> 'dict | None'",
    "stops_from_getpatterns": "(root: 'dict') -> 'pd.DataFrame'",
    "pattern_stops_table": "(pids: 'list[str]', cache_dir: 'Path | None' = None) -> 'pd.DataFrame'",
}
MANSUETO_CONSTANTS = ["BASE", "RT_TO_PID_URL", "CLOUDFRONT_MIN_INTERVAL_SEC"]
MANSUETO_SIGNATURES = {
    "parquet_url": "(pid: 'str') -> 'str'",
    "parquet_http_status": "(pid: 'str') -> 'int'",
}
BUSTRACKER_PRIVATE = ["_chicago_today", "_save_request_log", "_increment_daily_counter", "_save_getpatterns_cache", "_last_api_call_monotonic"]

# Constants moved verbatim (spec: Thresholds and exclusions).
EXPECTED_CONSTANTS = {
    "CTA_API_BASE": "https://www.ctabustracker.com/bustime/api/v3",
    "CTA_API_MIN_INTERVAL_SEC": 0.25,
    "CTA_API_DAILY_WARN": 9_500,
    "CTA_API_DAILY_MAX": 10_000,
    "CTA_API_MAX_RETRIES": 3,
    "CTA_API_RETRY_BASE_SEC": 2.0,
    "PATTERN_STOP_COLUMNS": ["pid", "rtdir", "seq", "stpid", "stpnm", "lat", "lon", "pdist_ft", "stop_rank"],  # stop_rank added by specs/mansueto-adapter.md
}

# Row count of pattern_stops_table(KEPT, GETPATTERNS_DIR) obtained by tests/test_views_archive.py
# with cta.patterns at HEAD 12f0aeb (45 pids, 2026-11-03 fixture).
FIXTURE_STOP_ROWS = 2469

_NOTEBOOK_LEGACY_IMPORT = re.compile(r"^\s*(?:from|import)\s+cta\.(?:cta_api|patterns)\b", re.MULTILINE)


def _isolated_import_check(module: str, other: str) -> None:
    code = f"import sys, {module}; assert {other!r} not in sys.modules, sorted(sys.modules)"
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_name_inventory():
    """Acceptance 1: every public name is importable with its pre-split signature; no cross-import."""
    from cta import mansueto

    assert len(BUSTRACKER_CONSTANTS) + len(BUSTRACKER_SIGNATURES) == 23
    assert len(MANSUETO_CONSTANTS) + len(MANSUETO_SIGNATURES) == 5
    for name in BUSTRACKER_CONSTANTS + BUSTRACKER_PRIVATE:
        assert hasattr(bustracker, name), name
    for name, sig in BUSTRACKER_SIGNATURES.items():
        assert str(inspect.signature(getattr(bustracker, name))) == sig, name
    for name in MANSUETO_CONSTANTS:
        assert hasattr(mansueto, name), name
    for name, sig in MANSUETO_SIGNATURES.items():
        assert str(inspect.signature(getattr(mansueto, name))) == sig, name
    for name, value in EXPECTED_CONSTANTS.items():
        assert getattr(bustracker, name) == value, name
    assert mansueto.BASE == "https://d2v7z51jmtm0iq.cloudfront.net/cta-stop-watch"
    assert mansueto.RT_TO_PID_URL == f"{mansueto.BASE}/rt_to_pid.csv"
    assert mansueto.CLOUDFRONT_MIN_INTERVAL_SEC == 0.1
    assert bustracker.default_cache_dir is bustracker.api_cache_dir

    _isolated_import_check("cta.bustracker", "cta.mansueto")
    _isolated_import_check("cta.mansueto", "cta.bustracker")


def test_legacy_modules_gone():
    """Acceptance 2: cta.cta_api and cta.patterns no longer exist and no notebook imports them."""
    for legacy in ("cta.cta_api", "cta.patterns"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(legacy)
    assert not (REPO_ROOT / "cta" / "cta_api.py").exists()
    assert not (REPO_ROOT / "cta" / "patterns.py").exists()
    offenders = []
    for nb_path in sorted((REPO_ROOT / "notebooks").glob("*.ipynb")):
        nb = json.loads(nb_path.read_text())
        for cell in nb["cells"]:
            if cell["cell_type"] != "code":
                continue
            for m in _NOTEBOOK_LEGACY_IMPORT.finditer("".join(cell["source"])):
                offenders.append((nb_path.name, m.group(0).strip()))
    assert offenders == []


def _two_pattern_root() -> dict:
    return {
        "ptr": [
            {
                "pid": "20",
                "rtdir": "Southbound",
                "pt": [
                    {"typ": "S", "seq": 4, "stpid": "2004", "stpnm": "D", "lat": 41.80, "lon": -87.60, "pdist": 3000},
                    {"typ": "W", "seq": 2, "lat": 41.85, "lon": -87.61},
                    {"typ": "S", "seq": 1, "stpid": "2001", "stpnm": "A", "lat": 41.90, "lon": -87.62, "pdist": 0},
                ],
            },
            {
                "pid": "10",
                "rtdir": "Northbound",
                "pt": [
                    {"typ": "W", "seq": 1, "lat": 41.80, "lon": -87.60},
                    {"typ": "S", "seq": 3, "stpid": "1003", "stpnm": "C", "lat": 41.90, "lon": -87.62, "pdist": 2500},
                    {"typ": "S", "seq": 2, "stpid": "1002", "stpnm": "B", "lat": 41.85, "lon": -87.61, "pdist": 1200.5},
                ],
            },
        ]
    }


def test_parser_equivalence():
    """Acceptance 3: stops_from_getpatterns == ptr_to_stops_df per pattern, and the fixture table is unchanged."""
    root = _two_pattern_root()
    df = bustracker.stops_from_getpatterns(root)
    assert list(df.columns) == bustracker.PATTERN_STOP_COLUMNS
    assert len(df) == 4
    assert list(zip(df["pid"], df["seq"])) == [("10", 2), ("10", 3), ("20", 1), ("20", 4)]
    assert df["pdist_ft"].dtype == "float64"
    assert all(isinstance(s, str) for s in df["stpid"])
    assert list(df["pdist_ft"]) == [1200.5, 2500.0, 0.0, 3000.0]
    assert list(df["rtdir"]) == ["Northbound", "Northbound", "Southbound", "Southbound"]
    for ptr in root["ptr"]:
        pid = str(ptr["pid"])
        part = df[df["pid"] == pid].drop(columns=["pid", "rtdir"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(part, bustracker.ptr_to_stops_df(ptr))

    # A pattern with no stop points contributes no rows (as before the split) and does not raise.
    df_empty = bustracker.stops_from_getpatterns({"ptr": {"pid": "1", "rtdir": "X", "pt": [{"typ": "W", "seq": 1, "lat": 0, "lon": 0}]}})
    assert len(df_empty) == 0 and list(df_empty.columns) == bustracker.PATTERN_STOP_COLUMNS

    missing = [p for p in KEPT if not (GETPATTERNS_DIR / f"getpatterns_{p}.json").is_file()]
    if missing:
        pytest.skip(f"getpatterns fixture missing for {len(missing)} kept pids")
    stops = bustracker.pattern_stops_table(KEPT, GETPATTERNS_DIR)
    assert len(stops) == FIXTURE_STOP_ROWS
    assert list(stops.columns) == bustracker.PATTERN_STOP_COLUMNS
    assert stops["pid"].nunique() == len(KEPT)


def test_one_cache_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Acceptance 4: cache_path names the file batch_pattern_stops writes; load_getpatterns reads it back."""
    cache_dir = tmp_path / "cache"
    pid = "7107"
    root = {
        "ptr": [
            {
                "pid": pid,
                "rtdir": "Southbound",
                "pt": [{"typ": "S", "seq": 1, "stpid": "1", "stpnm": "A", "lat": 41.9, "lon": -87.6, "pdist": 0}],
            }
        ]
    }
    monkeypatch.setenv("CTA_API_KEY", "test-key")
    monkeypatch.setattr(bustracker.time, "sleep", lambda s: None)
    payload = json.dumps({"bustime-response": root}).encode()

    def fake_urlopen(req, timeout=60):
        class Resp:
            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return Resp()

    monkeypatch.setattr(bustracker.urllib.request, "urlopen", fake_urlopen)

    result = bustracker.batch_pattern_stops([pid], use_cache=True, cache_dir=cache_dir, progress_every=0)
    assert pid in result
    written = sorted(p for p in cache_dir.iterdir() if p.name.startswith("getpatterns_"))
    assert written == [bustracker.cache_path(pid, cache_dir)]
    assert bustracker.load_getpatterns(pid, cache_dir) == root
    assert bustracker.load_getpatterns("0", cache_dir) is None


# Implementation-report QA table (acceptance 5): one row per name, reason in {moved, merged_duplicate, alias}.
QA_TABLE = [
    # old_module, name, new_module, reason
    ("cta_api", "CHICAGO", "bustracker", "moved"),
    ("cta_api", "BASE", "mansueto", "moved"),
    ("cta_api", "RT_TO_PID_URL", "mansueto", "moved"),
    ("cta_api", "CTA_API_BASE", "bustracker", "moved"),
    ("cta_api", "CTA_API_MIN_INTERVAL_SEC", "bustracker", "moved"),
    ("cta_api", "CTA_API_DAILY_WARN", "bustracker", "moved"),
    ("cta_api", "CTA_API_DAILY_MAX", "bustracker", "moved"),
    ("cta_api", "CLOUDFRONT_MIN_INTERVAL_SEC", "mansueto", "moved"),
    ("cta_api", "CTA_API_MAX_RETRIES", "bustracker", "moved"),
    ("cta_api", "CTA_API_RETRY_BASE_SEC", "bustracker", "moved"),
    ("cta_api", "LAST_CTA_REQUEST_URL", "bustracker", "moved"),
    ("cta_api", "repo_root", "bustracker", "moved"),
    ("cta_api", "api_cache_dir", "bustracker", "moved"),
    ("cta_api", "load_dotenv", "bustracker", "moved"),
    ("cta_api", "daily_api_request_count", "bustracker", "moved"),
    ("cta_api", "parquet_url", "mansueto", "moved"),
    ("cta_api", "parquet_http_status", "mansueto", "moved"),
    ("cta_api", "cta_api_get", "bustracker", "moved"),
    ("cta_api", "ptr_to_stops_df", "bustracker", "moved"),
    ("cta_api", "pattern_stops_from_ptr", "bustracker", "moved"),
    ("cta_api", "pattern_records", "bustracker", "moved"),
    ("cta_api", "batch_pattern_stops", "bustracker", "moved"),
    ("patterns", "PATTERN_STOP_COLUMNS", "bustracker", "moved"),
    ("patterns", "repo_root", "bustracker", "merged_duplicate"),
    ("patterns", "default_cache_dir", "bustracker", "alias"),
    ("patterns", "cache_path", "bustracker", "moved"),
    ("patterns", "load_getpatterns", "bustracker", "moved"),
    ("patterns", "stops_from_getpatterns", "bustracker", "moved"),
    ("patterns", "pattern_stops_table", "bustracker", "moved"),
    # private names folded into one implementation
    ("cta_api", "_getpatterns_cache_path", "bustracker", "merged_duplicate"),
    ("cta_api", "_load_getpatterns_cache", "bustracker", "merged_duplicate"),
]


def test_qa_table_sums():
    """Acceptance 5: moved + merged_duplicate + alias == names_in and names_out == moved + alias."""
    from cta import mansueto

    public = [row for row in QA_TABLE if not row[1].startswith("_")]
    assert len(public) == 29
    assert sum(1 for r in public if r[0] == "cta_api") == 22
    assert sum(1 for r in public if r[0] == "patterns") == 7
    assert sum(1 for r in QA_TABLE if r[1].startswith("_")) == 2

    reasons = {r[3] for r in QA_TABLE}
    assert reasons <= {"moved", "merged_duplicate", "alias"}
    counts = {reason: sum(1 for r in QA_TABLE if r[3] == reason) for reason in sorted(reasons)}
    assert counts["moved"] + counts["merged_duplicate"] + counts["alias"] == len(QA_TABLE)

    names_out = {(r[2], r[1]) for r in QA_TABLE if r[3] in ("moved", "alias")}
    assert len(names_out) == counts["moved"] + counts["alias"]
    assert len({n for m, n in names_out if m == "bustracker"}) == 23
    assert len({n for m, n in names_out if m == "mansueto"}) == 5
    modules = {"bustracker": bustracker, "mansueto": mansueto}
    for new_module, name in names_out:
        assert hasattr(modules[new_module], name), (new_module, name)
    for _, name, new_module, reason in QA_TABLE:
        if reason == "merged_duplicate" and name.startswith("_"):
            assert not hasattr(modules[new_module], name), name


def test_existing_tests_unchanged():
    """Acceptance 6: the six former test_cta_api tests exist here, one moved to test_mansueto; total >= 73."""
    kept_here = {
        "test_module_imports",
        "test_ptr_to_stops_df_filters_waypoints_and_sorts",
        "test_daily_counter_increments_and_resets_by_date",
        "test_cta_api_get_throttles_between_calls",
        "test_batch_pattern_stops_uses_cache_without_network",
    }
    assert kept_here <= set(globals())
    assert "test_parquet_url_basic" in (REPO_ROOT / "tests" / "test_mansueto.py").read_text()
    assert not (REPO_ROOT / "tests" / "test_cta_api.py").exists()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    collected = [line for line in proc.stdout.splitlines() if "::" in line]
    assert len(collected) >= 68 + 5, len(collected)


@pytest.mark.parametrize("script", ["archive_run_level.py", "build_archive_fixtures.py"])
def test_scripts_smoke(script: str):
    """Acceptance 7: both scripts import the new modules at top level and answer -h."""
    proc = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / script), "-h"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "usage:" in proc.stdout
