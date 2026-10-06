"""Shared DLSD run construction and Mansueto-aligned quality flags."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from cta_api import BASE, parquet_url

PARQUET_COLS = [
    "bus_stop_time",
    "unique_trip_vehicle_day",
    "stpid",
    "pid",
    "stop_sequence",
    "speed_mph",
    "seg_combined",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def local_parquet_path(
    pid: str,
    *,
    prefer_local: bool = True,
    cache_variant: str = "last30d",
) -> str | Path:
    """Prefer cached file under data/mansueto/ when prefer_local (e.g. last30d, last365d)."""
    if prefer_local:
        cached = (
            repo_root() / "data" / "mansueto" / f"trips_{pid}_{cache_variant}.parquet"
        )
        if cached.is_file():
            return cached
    return parquet_url(pid)


def load_dlsd_boundaries(path: Path | None = None) -> dict[str, dict]:
    path = path or Path(__file__).resolve().parent / "dlsd_boundaries_snapshot.json"
    return json.loads(path.read_text())


def _entry_exit_runs(
    df: pd.DataFrame, entry_stpid: str, exit_stpid: str
) -> pd.DataFrame:
    """One row per trip that visits both the entry and exit stop."""
    entries = (
        df[df["stpid"] == entry_stpid]
        .groupby("unique_trip_vehicle_day", as_index=False)
        .agg(
            entry_time=("bus_stop_time", "min"),
            entry_sequence=("stop_sequence", "min"),
            entry_speed_mph=("speed_mph", "first"),
            entry_seg=("seg_combined", "first"),
        )
    )
    exits = (
        df[df["stpid"] == exit_stpid]
        .groupby("unique_trip_vehicle_day", as_index=False)
        .agg(
            exit_time=("bus_stop_time", "max"),
            exit_sequence=("stop_sequence", "max"),
            exit_speed_mph=("speed_mph", "first"),
            exit_seg=("seg_combined", "first"),
        )
    )
    return entries.merge(exits, on="unique_trip_vehicle_day", how="inner")


def _bracket_times(df: pd.DataFrame, runs: pd.DataFrame) -> pd.DataFrame:
    """Per run: time at the stop just before entry and just after exit (NaT if absent)."""
    trip_bounds = runs[["unique_trip_vehicle_day", "entry_sequence", "exit_sequence"]]
    visits = df[["unique_trip_vehicle_day", "stop_sequence", "bus_stop_time"]].merge(
        trip_bounds, on="unique_trip_vehicle_day", how="inner"
    )
    pre = (
        visits[visits["stop_sequence"] == visits["entry_sequence"] - 1]
        .groupby("unique_trip_vehicle_day")["bus_stop_time"]
        .min()
        .rename("pre_dlsd_time")
    )
    post = (
        visits[visits["stop_sequence"] == visits["exit_sequence"] + 1]
        .groupby("unique_trip_vehicle_day")["bus_stop_time"]
        .max()
        .rename("post_dlsd_time")
    )
    return (
        trip_bounds[["unique_trip_vehicle_day"]]
        .join(pre, on="unique_trip_vehicle_day")
        .join(post, on="unique_trip_vehicle_day")
    )


def build_dlsd_runs(
    dlsd_boundaries: dict[str, dict],
    *,
    prefer_local: bool = True,
    cache_variant: str = "last30d",
) -> pd.DataFrame:
    """One row per trip with entry/exit times, sequences, and bracket stops."""
    frames = []

    for pid, info in dlsd_boundaries.items():
        pid = str(pid)
        entry_stpid = str(info["entry_stpid"])
        exit_stpid = str(info["exit_stpid"])
        hop_feet = float(info["hop_feet"])
        df = pd.read_parquet(
            local_parquet_path(
                pid, prefer_local=prefer_local, cache_variant=cache_variant
            ),
            columns=PARQUET_COLS,
        )
        df["stpid"] = df["stpid"].astype(str)
        df["pid"] = df["pid"].astype(float).astype(int).astype(str)
        df = df.sort_values(["unique_trip_vehicle_day", "stop_sequence"])

        runs = _entry_exit_runs(df, entry_stpid, exit_stpid)
        if runs.empty:
            continue

        runs["pid"] = pid
        runs["route"] = info["route"]
        runs["rtdir"] = info["rtdir"]
        runs["hop_feet"] = hop_feet
        runs["dlsd_miles"] = hop_feet / 5280.0
        runs["dlsd_minutes"] = (
            runs["exit_time"] - runs["entry_time"]
        ).dt.total_seconds() / 60.0
        runs["implied_dlsd_mph"] = runs["dlsd_miles"] / (runs["dlsd_minutes"] / 60.0)
        runs["dlsd_minutes_bin"] = np.floor(runs["dlsd_minutes"] / 5.0) * 5.0
        runs["same_ping_interval_proxy"] = (
            runs["entry_speed_mph"] == runs["exit_speed_mph"]
        ) & runs["entry_speed_mph"].notna()
        frames.append(
            runs.merge(_bracket_times(df, runs), on="unique_trip_vehicle_day", how="left")
        )

    dlsd_runs = pd.concat(frames, ignore_index=True)
    dlsd_runs["bracket_minutes"] = (
        dlsd_runs["post_dlsd_time"] - dlsd_runs["pre_dlsd_time"]
    ).dt.total_seconds() / 60.0

    dlsd_runs["hour"] = dlsd_runs["entry_time"].dt.hour
    dlsd_runs["day_of_week"] = dlsd_runs["entry_time"].dt.dayofweek
    dlsd_runs["is_weekday"] = dlsd_runs["day_of_week"] < 5

    dlsd_runs = add_quality_flags(dlsd_runs)
    return dlsd_runs


RUSH_ROUTES: frozenset[str] = frozenset({"134", "135", "136", "143", "148"})
ALL_DAY_DLSD_ROUTES: frozenset[str] = frozenset({"146", "147"})
DEFAULT_PLOT_HOURS: list[int] = list(range(6, 23))

# Weekday (Mon–Thu) run counts >= this define rush (route, rtdir, hour) plot targets.
# Friday charts reuse the same target set; see valid_rush_plot_cells().
MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY: int = 30

# Deprecated: use MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY + valid_rush_plot_cells().
MIN_RUNS_RUSH_HOUR: int | None = None


def day_slice_mask(dlsd_runs: pd.DataFrame, slice_name: str) -> pd.Series:
    """weekday = Mon–Thu; mon_fri = Mon–Fri; friday; weekend = Sat–Sun."""
    if "day_of_week" not in dlsd_runs.columns:
        dow = dlsd_runs["entry_time"].dt.dayofweek
    else:
        dow = dlsd_runs["day_of_week"]
    if slice_name == "weekday":
        return dow <= 3
    if slice_name == "mon_fri":
        return dow <= 4
    if slice_name == "friday":
        return dow == 4
    if slice_name == "weekend":
        return dow >= 5
    raise ValueError(
        f"Unknown day_slice {slice_name!r}; use weekday, mon_fri, friday, weekend"
    )


def hour_run_counts(
    dlsd_runs: pd.DataFrame,
    *,
    routes: set[str] | frozenset[str] | None = None,
    day_slice: str,
) -> pd.DataFrame:
    """Count analysis_ok runs per (route, rtdir, hour) within a day slice."""
    df = dlsd_runs.loc[dlsd_runs["analysis_ok"] & day_slice_mask(dlsd_runs, day_slice)]
    if routes is not None:
        df = df.loc[df["route"].astype(str).isin(routes)]
    counts = (
        df.groupby(["route", "rtdir", "hour"], as_index=False)
        .size()
        .rename(columns={"size": "n_runs"})
    )
    counts["day_slice"] = day_slice
    return counts


def routes_for_day_slice(day_slice: str) -> frozenset[str]:
    """Weekend comparison views: 146/147 only; otherwise rush + all-day."""
    if day_slice == "weekend":
        return ALL_DAY_DLSD_ROUTES
    return RUSH_ROUTES | ALL_DAY_DLSD_ROUTES


def valid_rush_plot_cells(
    dlsd_runs: pd.DataFrame,
    min_runs: int | None = None,
) -> pd.DataFrame:
    """
    Rush plot targets from weekday (Mon–Thu) analysis_ok counts only.
    Friday plots reuse this set; they do not apply a separate Friday min_runs gate.
    """
    threshold = (
        min_runs
        if min_runs is not None
        else MIN_RUNS_RUSH_WEEKDAY_ELIGIBILITY
    )
    counts = hour_run_counts(dlsd_runs, routes=RUSH_ROUTES, day_slice="weekday")
    valid = counts.loc[counts["n_runs"] >= threshold].copy()
    return valid[["route", "rtdir", "hour", "n_runs"]].reset_index(drop=True)


def _mask_stats_to_valid_cells(
    out: pd.DataFrame,
    route: str,
    rtdir: str,
    valid_cells: pd.DataFrame | None,
) -> pd.DataFrame:
    if valid_cells is None or str(route) not in RUSH_ROUTES:
        return out
    allowed = valid_cells.loc[
        (valid_cells["route"].astype(str) == str(route))
        & (valid_cells["rtdir"] == rtdir),
        "hour",
    ].astype(int)
    allowed_hours = set(allowed.tolist())
    stat_cols = [c for c in out.columns if c not in ("hour", "n_runs")]
    for hour in out["hour"].dropna().astype(int):
        if hour not in allowed_hours:
            out.loc[out["hour"] == hour, stat_cols] = np.nan
    return out


def hour_dlsd_stats(
    sub: pd.DataFrame,
    hours: list[int],
    *,
    route: str,
    rtdir: str | None = None,
    min_runs: int | None = None,
    apply_min_to_routes: set[str] | frozenset[str] | None = None,
    valid_cells: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Hourly DLSD duration and implied speed stats on a fixed hour index.
    For rush routes, pass valid_cells from valid_rush_plot_cells() to leave gaps
    outside weekday-eligible (route, rtdir, hour) targets.
    min_runs on the current sub is legacy; prefer valid_cells for rush gating.
    """
    if rtdir is None and not sub.empty and "rtdir" in sub.columns:
        rtdir = str(sub["rtdir"].iloc[0])
    apply_min_to_routes = apply_min_to_routes or frozenset()
    grouped = (
        sub.groupby("hour", as_index=False)
        .agg(
            n_runs=("dlsd_minutes", "count"),
            median_min=("dlsd_minutes", "median"),
            q25_min=("dlsd_minutes", lambda s: s.quantile(0.25)),
            q75_min=("dlsd_minutes", lambda s: s.quantile(0.75)),
            q95_min=("dlsd_minutes", lambda s: s.quantile(0.95)),
            median_mph=("implied_dlsd_mph", "median"),
            q25_mph=("implied_dlsd_mph", lambda s: s.quantile(0.25)),
            q75_mph=("implied_dlsd_mph", lambda s: s.quantile(0.75)),
            q95_mph=("implied_dlsd_mph", lambda s: s.quantile(0.95)),
        )
    )
    out = grouped.set_index("hour").reindex(hours).reset_index()
    if min_runs is not None and str(route) in {str(r) for r in apply_min_to_routes}:
        stat_cols = [
            c
            for c in out.columns
            if c not in ("hour", "n_runs") and not c.endswith("_runs")
        ]
        low = out["n_runs"].fillna(0) < min_runs
        out.loc[low, stat_cols] = np.nan
    if valid_cells is not None and rtdir is not None:
        out = _mask_stats_to_valid_cells(out, route, rtdir, valid_cells)
    return out


def add_quality_flags(dlsd_runs: pd.DataFrame) -> pd.DataFrame:
    out = dlsd_runs.copy()
    out["ok_times_present"] = (
        out["entry_time"].notna() & out["exit_time"].notna()
    )
    out["ok_time_order"] = out["exit_time"] > out["entry_time"]
    out["ok_consecutive"] = (
        out["exit_sequence"] == out["entry_sequence"] + 1
    )
    out["analysis_ok"] = (
        out["ok_times_present"] & out["ok_time_order"] & out["ok_consecutive"]
    )
    out["legacy_drop"] = (out["dlsd_minutes"] < 1) | (out["dlsd_minutes"] > 120)
    return out
