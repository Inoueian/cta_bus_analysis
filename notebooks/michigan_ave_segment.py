"""Michigan Ave corridor segment geometry (getpatterns) and trip timing (Mansueto)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from cta_api import RT_TO_PID_URL, batch_pattern_stops
from dlsd_run_quality import DEFAULT_PLOT_HOURS, PARQUET_COLS, local_parquet_path

DEFAULT_MIN_MEDIAN_MINUTES = 5.0
DEFAULT_MIN_ENTRY_EXIT_SHARE = 0.5
SHARED_OBSERVATION_WINDOW_HOURS = 720
TRIM_6402_STPIDS: frozenset[str] = frozenset({"1104", "1105", "1106", "18396"})

# Ping-interval speed on DLSD-adjacent stops; excluded from corridor speed charts.
NORTHBOUND_DLSD_LEAK_STPIDS: frozenset[str] = frozenset({"1128", "1127"})
SOUTHBOUND_DLSD_LEAK_STPIDS: frozenset[str] = frozenset({"1097", "1098"})

CORRIDOR_STREET_TICK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Roosevelt", "Roosevelt"),
    ("Ida B", "Ida B. Wells"),
    ("Madison", "Madison"),
    ("Wacker", "Wacker"),
    ("Chicago", "Chicago"),
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def stops_snapshot_path() -> Path:
    return Path(__file__).resolve().parent / "michigan_ave_stops_snapshot.json"


def kept_pids_path() -> Path:
    return Path(__file__).resolve().parent / "michigan_ave_kept_pids.json"


def load_kept_pids_meta(path: Path | None = None) -> dict:
    path = path or kept_pids_path()
    return json.loads(path.read_text())


def load_kept_pid_records(path: Path | None = None) -> list[dict]:
    return list(load_kept_pids_meta(path)["pids"])


def load_corridor_stpids(path: Path | None = None) -> set[str]:
    path = path or stops_snapshot_path()
    data = json.loads(path.read_text())
    return {str(s["stpid"]) for s in data["stops"]}


def load_corridor_stpnm_map(path: Path | None = None) -> dict[str, str]:
    path = path or stops_snapshot_path()
    data = json.loads(path.read_text())
    return {str(s["stpid"]): str(s["stpnm"]) for s in data["stops"]}


def load_candidate_routes(path: Path | None = None) -> list[str]:
    path = path or stops_snapshot_path()
    data = json.loads(path.read_text())
    return [str(r) for r in data["candidate_routes"]]


def pid_to_route_map() -> dict[str, str]:
    rt_df = pd.read_csv(RT_TO_PID_URL)
    rt_df["rt"] = rt_df["rt"].astype(str)
    rt_df["pid"] = rt_df["pid"].astype(str)
    routes = set(load_candidate_routes())
    sub = rt_df.loc[rt_df["rt"].isin(routes)]
    return dict(zip(sub["pid"], sub["rt"]))


def candidate_pids() -> list[str]:
    return sorted(pid_to_route_map().keys(), key=lambda x: int(x))


@dataclass(frozen=True)
class CorridorSegment:
    pid: str
    route: str
    rtdir: str
    entry_stpid: str
    exit_stpid: str
    entry_stpnm: str
    exit_stpnm: str
    n_stops: int
    stop_stpids: tuple[str, ...]


def longest_corridor_run(
    stops: pd.DataFrame,
    corridor_stpids: set[str],
) -> tuple[str, str, int, tuple[str, ...]] | None:
    """Return (entry_stpid, exit_stpid, n_stops, stop_stpids) or None if no span."""
    if stops.empty:
        return None
    corridor = {str(s) for s in corridor_stpids}
    stpids = stops["stpid"].astype(str).tolist()
    lats = stops["lat"].astype(float).tolist()

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, stpid in enumerate(stpids):
        if stpid in corridor:
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(stpids) - 1))

    if not runs:
        return None

    def run_key(run: tuple[int, int]) -> tuple[int, float]:
        a, b = run
        length = b - a + 1
        lat_span = max(lats[a : b + 1]) - min(lats[a : b + 1])
        return (length, lat_span)

    a, b = max(runs, key=run_key)
    if b - a + 1 < 2:
        return None
    return stpids[a], stpids[b], b - a + 1, tuple(stpids[a : b + 1])


def segment_from_pattern_stops(
    pid: str,
    route: str,
    rtdir: str,
    stops: pd.DataFrame,
    corridor_stpids: set[str],
) -> CorridorSegment | None:
    run = longest_corridor_run(stops, corridor_stpids)
    if run is None:
        return None
    entry_stpid, exit_stpid, n_stops, stop_stpids = run
    name_by_stpid = dict(zip(stops["stpid"].astype(str), stops["stpnm"]))
    return CorridorSegment(
        pid=str(pid),
        route=str(route),
        rtdir=str(rtdir),
        entry_stpid=entry_stpid,
        exit_stpid=exit_stpid,
        entry_stpnm=str(name_by_stpid.get(entry_stpid, "")),
        exit_stpnm=str(name_by_stpid.get(exit_stpid, "")),
        n_stops=n_stops,
        stop_stpids=stop_stpids,
    )


def build_corridor_segments(
    pids: list[str] | None = None,
    *,
    corridor_stpids: set[str] | None = None,
    use_cache: bool = True,
) -> dict[str, CorridorSegment]:
    corridor_stpids = corridor_stpids or load_corridor_stpids()
    pid_route = pid_to_route_map()
    pids = pids or candidate_pids()
    pattern_stops = batch_pattern_stops(pids, use_cache=use_cache)

    segments: dict[str, CorridorSegment] = {}
    for pid in pids:
        if pid not in pattern_stops:
            continue
        rtdir, stops = pattern_stops[pid]
        route = pid_route.get(pid, "")
        seg = segment_from_pattern_stops(pid, route, rtdir, stops, corridor_stpids)
        if seg is not None:
            segments[pid] = seg
    return segments


def mode_last_corridor_stop_on_trip(
    df: pd.DataFrame,
    corridor_stpids: set[str],
) -> tuple[str | None, int]:
    """Most common last in-corridor stop (by stop_sequence) among trips that touch the corridor."""
    corridor = {str(s) for s in corridor_stpids}
    sub = df.loc[df["stpid"].astype(str).isin(corridor)].copy()
    if sub.empty:
        return None, 0
    last_stpids: list[str] = []
    for _, trip_df in sub.groupby("unique_trip_vehicle_day"):
        trip_df = trip_df.sort_values("stop_sequence")
        last_stpids.append(str(trip_df.iloc[-1]["stpid"]))
    if not last_stpids:
        return None, 0
    counts = pd.Series(last_stpids).value_counts()
    mode_stpid = str(counts.index[0])
    return mode_stpid, int(counts.iloc[0])


def endpoint_coverage(
    df: pd.DataFrame,
    entry_stpid: str,
    exit_stpid: str,
    corridor_stpids: set[str],
    *,
    stpnm_by_stpid: dict[str, str] | None = None,
) -> dict[str, float | int | str | bool | None]:
    """Trip counts for pattern entry/exit and observed last corridor stop."""
    df = df.copy()
    df["stpid"] = df["stpid"].astype(str)
    entry_stpid = str(entry_stpid)
    exit_stpid = str(exit_stpid)
    names = stpnm_by_stpid or {}

    entry_trips = set(df.loc[df["stpid"] == entry_stpid, "unique_trip_vehicle_day"])
    exit_trips = set(df.loc[df["stpid"] == exit_stpid, "unique_trip_vehicle_day"])
    both_trips = entry_trips & exit_trips
    corridor_trips = set(
        df.loc[df["stpid"].isin({str(s) for s in corridor_stpids}), "unique_trip_vehicle_day"]
    )

    n_entry = len(entry_trips)
    n_exit = len(exit_trips)
    n_both = len(both_trips)
    n_corridor = len(corridor_trips)

    share_entry_with_exit = (n_both / n_entry) if n_entry else np.nan
    share_exit_with_entry = (n_both / n_exit) if n_exit else np.nan

    mode_last, mode_n = mode_last_corridor_stop_on_trip(df, corridor_stpids)

    return {
        "n_trips_total": int(df["unique_trip_vehicle_day"].nunique()),
        "n_trips_corridor": n_corridor,
        "n_trips_entry": n_entry,
        "n_trips_exit": n_exit,
        "n_trips_both": n_both,
        "share_entry_with_exit": float(share_entry_with_exit)
        if not np.isnan(share_entry_with_exit)
        else np.nan,
        "share_entry_without_exit": float(1.0 - share_entry_with_exit)
        if n_entry
        else np.nan,
        "share_exit_with_entry": float(share_exit_with_entry)
        if not np.isnan(share_exit_with_entry)
        else np.nan,
        "mode_last_corridor_stpid": mode_last,
        "mode_last_corridor_stpnm": names.get(mode_last, "") if mode_last else "",
        "mode_last_corridor_n_trips": mode_n,
        "low_entry_exit_coverage": bool(
            n_entry > 0 and share_entry_with_exit < DEFAULT_MIN_ENTRY_EXIT_SHARE
        ),
    }


def endpoint_coverage_row(
    segment: CorridorSegment,
    df: pd.DataFrame,
    *,
    corridor_stpids: set[str] | None = None,
    stpnm_by_stpid: dict[str, str] | None = None,
) -> dict:
    corridor_stpids = corridor_stpids or load_corridor_stpids()
    stpnm_by_stpid = stpnm_by_stpid or load_corridor_stpnm_map()
    row = endpoint_coverage(
        df,
        segment.entry_stpid,
        segment.exit_stpid,
        corridor_stpids,
        stpnm_by_stpid=stpnm_by_stpid,
    )
    row.update(
        {
            "pid": segment.pid,
            "route": segment.route,
            "rtdir": segment.rtdir,
            "entry_stpid": segment.entry_stpid,
            "exit_stpid": segment.exit_stpid,
            "entry_stpnm": segment.entry_stpnm,
            "exit_stpnm": segment.exit_stpnm,
        }
    )
    return row


def build_endpoint_coverage_summary(
    segments: dict[str, CorridorSegment],
    *,
    prefer_local: bool = True,
    cache_variant: str = "last30d",
    min_entry_exit_share: float = DEFAULT_MIN_ENTRY_EXIT_SHARE,
) -> pd.DataFrame:
    corridor_stpids = load_corridor_stpids()
    stpnm_by_stpid = load_corridor_stpnm_map()
    rows = []
    for pid, segment in sorted(segments.items(), key=lambda x: int(x[0])):
        path = local_parquet_path(
            pid, prefer_local=prefer_local, cache_variant=cache_variant
        )
        if prefer_local and not Path(path).is_file():
            continue
        try:
            df = pd.read_parquet(path, columns=PARQUET_COLS)
        except Exception:
            continue
        rows.append(
            endpoint_coverage_row(
                segment,
                df,
                corridor_stpids=corridor_stpids,
                stpnm_by_stpid=stpnm_by_stpid,
            )
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(
        ["share_entry_with_exit", "n_trips_entry"],
        ascending=[True, False],
        na_position="last",
    )
    out["low_entry_exit_coverage"] = (
        out["n_trips_entry"] > 0
    ) & (out["share_entry_with_exit"] < min_entry_exit_share)
    return out


def trip_segment_minutes(
    df: pd.DataFrame,
    entry_stpid: str,
    exit_stpid: str,
) -> pd.Series:
    """Per-trip minutes from entry to exit; NaN when either stop missing."""
    df = df.copy()
    df["stpid"] = df["stpid"].astype(str)
    entry_stpid = str(entry_stpid)
    exit_stpid = str(exit_stpid)

    entries = (
        df.loc[df["stpid"] == entry_stpid]
        .groupby("unique_trip_vehicle_day", as_index=False)["bus_stop_time"]
        .min()
        .rename(columns={"bus_stop_time": "entry_time"})
    )
    exits = (
        df.loc[df["stpid"] == exit_stpid]
        .groupby("unique_trip_vehicle_day", as_index=False)["bus_stop_time"]
        .max()
        .rename(columns={"bus_stop_time": "exit_time"})
    )
    merged = entries.merge(exits, on="unique_trip_vehicle_day", how="inner")
    minutes = (merged["exit_time"] - merged["entry_time"]).dt.total_seconds() / 60.0
    return minutes.set_axis(merged["unique_trip_vehicle_day"].values)


def median_segment_minutes_for_pid(
    segment: CorridorSegment,
    *,
    prefer_local: bool = True,
    cache_variant: str = "last30d",
) -> pd.Series:
    path = local_parquet_path(
        segment.pid, prefer_local=prefer_local, cache_variant=cache_variant
    )
    df = pd.read_parquet(path, columns=PARQUET_COLS)
    return trip_segment_minutes(df, segment.entry_stpid, segment.exit_stpid)


def pid_timing_summary_row(
    segment: CorridorSegment,
    minutes: pd.Series,
) -> dict:
    valid = minutes.dropna()
    valid = valid[valid > 0]
    n_trips = int(len(valid))
    if n_trips == 0:
        return {
            "pid": segment.pid,
            "route": segment.route,
            "rtdir": segment.rtdir,
            "entry_stpid": segment.entry_stpid,
            "exit_stpid": segment.exit_stpid,
            "entry_stpnm": segment.entry_stpnm,
            "exit_stpnm": segment.exit_stpnm,
            "n_corridor_stops": segment.n_stops,
            "n_trips": 0,
            "median_minutes": np.nan,
            "p25_minutes": np.nan,
            "p75_minutes": np.nan,
            "share_under_5_min": np.nan,
        }
    return {
        "pid": segment.pid,
        "route": segment.route,
        "rtdir": segment.rtdir,
        "entry_stpid": segment.entry_stpid,
        "exit_stpid": segment.exit_stpid,
        "entry_stpnm": segment.entry_stpnm,
        "exit_stpnm": segment.exit_stpnm,
        "n_corridor_stops": segment.n_stops,
        "n_trips": n_trips,
        "median_minutes": float(valid.median()),
        "p25_minutes": float(valid.quantile(0.25)),
        "p75_minutes": float(valid.quantile(0.75)),
        "share_under_5_min": float((valid < 5.0).mean()),
    }


def build_pid_timing_summary(
    segments: dict[str, CorridorSegment],
    *,
    prefer_local: bool = True,
    cache_variant: str = "last30d",
) -> pd.DataFrame:
    rows = []
    for pid, segment in sorted(segments.items(), key=lambda x: int(x[0])):
        path = local_parquet_path(
            pid, prefer_local=prefer_local, cache_variant=cache_variant
        )
        if prefer_local and not Path(path).is_file():
            continue
        try:
            df = pd.read_parquet(path, columns=PARQUET_COLS)
        except Exception:
            continue
        minutes = trip_segment_minutes(df, segment.entry_stpid, segment.exit_stpid)
        rows.append(pid_timing_summary_row(segment, minutes))
    return pd.DataFrame(rows)


def apply_median_threshold(
    summary: pd.DataFrame,
    min_median_minutes: float = DEFAULT_MIN_MEDIAN_MINUTES,
) -> pd.DataFrame:
    return summary.loc[
        summary["median_minutes"].notna()
        & (summary["median_minutes"] >= min_median_minutes)
    ].copy()


def _rtdirs_include(rtdirs: str, direction: str) -> bool:
    parts = [p.strip() for p in str(rtdirs).split(",")]
    return direction in parts


def direction_stop_sequences(path: Path | None = None) -> dict[str, pd.DataFrame]:
    """Northbound: lat ascending; Southbound: lat descending."""
    path = path or stops_snapshot_path()
    data = json.loads(path.read_text())
    out: dict[str, pd.DataFrame] = {}
    for direction, ascending in (("Northbound", True), ("Southbound", False)):
        eligible = [
            s
            for s in data["stops"]
            if _rtdirs_include(s.get("rtdirs", ""), direction)
        ]
        eligible.sort(key=lambda s: float(s["lat"]), reverse=not ascending)
        out[direction] = pd.DataFrame(
            {
                "seq_index": range(len(eligible)),
                "stpid": [str(s["stpid"]) for s in eligible],
                "lat": [float(s["lat"]) for s in eligible],
                "stpnm": [str(s["stpnm"]) for s in eligible],
            }
        )
    return out


def interpolate_trip_corridor(
    trip_id: str,
    trip_obs: pd.DataFrame,
    sequence: pd.DataFrame,
    *,
    pid: str,
    route: str,
    rtdir: str,
) -> pd.DataFrame:
    """One trip: observed corridor stops plus gap-filled speed_mph on the sequence span."""
    stpid_to_idx = dict(zip(sequence["stpid"].astype(str), sequence["seq_index"]))
    seq_by_index = sequence.set_index("seq_index")

    obs = trip_obs.copy()
    obs["stpid"] = obs["stpid"].astype(str)
    obs = obs.loc[obs["stpid"].isin(stpid_to_idx)]
    if obs.empty:
        return pd.DataFrame()

    obs = obs.sort_values("bus_stop_time").groupby("stpid", as_index=False).first()
    obs["seq_index"] = obs["stpid"].map(stpid_to_idx).astype(int)

    observed: dict[int, tuple[float, object]] = {}
    for row in obs.itertuples(index=False):
        speed = float(row.speed_mph) if pd.notna(row.speed_mph) else np.nan
        observed[int(row.seq_index)] = (speed, row.bus_stop_time)

    indices = sorted(observed.keys())
    i_min, i_max = indices[0], indices[-1]

    rows: list[dict] = []
    span = range(i_min, i_max + 1) if i_min < i_max else [i_min]

    for i in span:
        meta = seq_by_index.loc[i]
        stpid = str(meta["stpid"])
        lat = float(meta["lat"])
        stpnm = str(meta["stpnm"])
        if i in observed:
            speed, bst = observed[i]
            rows.append(
                {
                    "unique_trip_vehicle_day": trip_id,
                    "stpid": stpid,
                    "pid": str(pid),
                    "route": str(route),
                    "rtdir": str(rtdir),
                    "seq_index": int(i),
                    "lat": lat,
                    "stpnm": stpnm,
                    "bus_stop_time": bst,
                    "speed_mph": speed,
                    "interpolated": False,
                }
            )
        else:
            before = max(j for j in indices if j < i)
            after = min(j for j in indices if j > i)
            speed = float(np.nanmean([observed[before][0], observed[after][0]]))
            rows.append(
                {
                    "unique_trip_vehicle_day": trip_id,
                    "stpid": stpid,
                    "pid": str(pid),
                    "route": str(route),
                    "rtdir": str(rtdir),
                    "seq_index": int(i),
                    "lat": lat,
                    "stpnm": stpnm,
                    "bus_stop_time": pd.NaT,
                    "speed_mph": speed,
                    "interpolated": True,
                }
            )
    return pd.DataFrame(rows)


def build_michigan_segment_view(
    *,
    prefer_local: bool = True,
    cache_variant: str = "last30d",
    kept_path: Path | None = None,
) -> pd.DataFrame:
    """Segment view for all kept PIDs: (trip, stpid) rows with optional speed interpolation."""
    sequences = direction_stop_sequences()
    records = load_kept_pid_records(kept_path)
    frames: list[pd.DataFrame] = []

    for rec in records:
        pid = str(rec["pid"])
        route = str(rec["route"])
        rtdir = str(rec["rtdir"])
        if rtdir not in sequences:
            continue
        sequence = sequences[rtdir]
        seq_stpids = set(sequence["stpid"].astype(str))

        path = local_parquet_path(
            pid, prefer_local=prefer_local, cache_variant=cache_variant
        )
        if prefer_local and not Path(path).is_file():
            continue
        try:
            df = pd.read_parquet(path, columns=PARQUET_COLS)
        except Exception:
            continue

        df["stpid"] = df["stpid"].astype(str)
        sub = df.loc[df["stpid"].isin(seq_stpids)]
        if sub.empty:
            continue

        for trip_id, trip_df in sub.groupby("unique_trip_vehicle_day", sort=False):
            part = interpolate_trip_corridor(
                str(trip_id),
                trip_df,
                sequence,
                pid=pid,
                route=route,
                rtdir=rtdir,
            )
            if not part.empty:
                frames.append(part)

    if not frames:
        return pd.DataFrame(
            columns=[
                "unique_trip_vehicle_day",
                "stpid",
                "pid",
                "route",
                "rtdir",
                "seq_index",
                "lat",
                "stpnm",
                "bus_stop_time",
                "speed_mph",
                "interpolated",
            ]
        )
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(
        ["pid", "unique_trip_vehicle_day", "seq_index"],
        kind="mergesort",
    ).reset_index(drop=True)


def kept_pid_cache_path(
    pid: str,
    *,
    cache_variant: str = "last30d",
) -> Path:
    return repo_root() / "data" / "mansueto" / f"trips_{pid}_{cache_variant}.parquet"


def kept_pid_cache_status(
    *,
    cache_variant: str = "last30d",
    kept_path: Path | None = None,
) -> pd.DataFrame:
    """Per kept PID: whether the local lastNd Mansueto cache file exists."""
    rows = []
    for rec in load_kept_pid_records(kept_path):
        pid = str(rec["pid"])
        path = kept_pid_cache_path(pid, cache_variant=cache_variant)
        rows.append(
            {
                "pid": pid,
                "route": str(rec["route"]),
                "rtdir": str(rec["rtdir"]),
                "n_trips_kept": int(rec.get("n_trips", 0)),
                "cache_exists": path.is_file(),
                "cache_path": str(path),
            }
        )
    return pd.DataFrame(rows)


def backwards_time_trip_keys(view: pd.DataFrame) -> pd.DataFrame:
    """Trips where observed bus_stop_time decreases as seq_index increases."""
    if view.empty:
        return pd.DataFrame(
            columns=["pid", "unique_trip_vehicle_day", "detail"]
        )
    obs = view.loc[~view["interpolated"] & view["bus_stop_time"].notna()].copy()
    if obs.empty:
        return pd.DataFrame(
            columns=["pid", "unique_trip_vehicle_day", "detail"]
        )
    rows: list[dict] = []
    grouped = obs.groupby(["pid", "unique_trip_vehicle_day"], sort=False)
    for (pid, trip_id), grp in grouped:
        g = grp.sort_values("seq_index")
        times = g["bus_stop_time"].tolist()
        if len(times) < 2:
            continue
        for i in range(1, len(times)):
            if times[i] < times[i - 1]:
                detail = "; ".join(
                    f"{r.stpid}@{r.bus_stop_time} (seq {int(r.seq_index)})"
                    for r in g.itertuples(index=False)
                )
                rows.append(
                    {
                        "pid": str(pid),
                        "unique_trip_vehicle_day": str(trip_id),
                        "detail": detail,
                    }
                )
                break
    return pd.DataFrame(rows)


def segment_view_report(
    view: pd.DataFrame,
    *,
    kept_path: Path | None = None,
    cache_status: pd.DataFrame | None = None,
) -> dict:
    """Summary metrics for a built segment view (and optional cache preflight)."""
    kept = load_kept_pid_records(kept_path)
    kept_pids = {str(r["pid"]) for r in kept}
    n_kept = len(kept_pids)

    if cache_status is None:
        variant = load_kept_pids_meta(kept_path).get("cache_variant", "last30d")
        cache_status = kept_pid_cache_status(
            cache_variant=str(variant), kept_path=kept_path
        )

    missing_cache = cache_status.loc[~cache_status["cache_exists"], "pid"].astype(str)
    missing_cache_list = sorted(missing_cache.tolist(), key=lambda x: int(x))

    if view.empty:
        pids_in_view: set[str] = set()
        by_route = pd.DataFrame()
        by_pid = pd.DataFrame(
            [
                {
                    "pid": str(r["pid"]),
                    "route": str(r["route"]),
                    "rtdir": str(r["rtdir"]),
                    "rows": 0,
                    "n_trips_view": 0,
                    "interpolated_share": np.nan,
                    "n_trips_kept": int(r.get("n_trips", 0)),
                }
                for r in kept
            ]
        )
        interp_share = np.nan
        null_obs = null_interp = 0
        backwards = pd.DataFrame(columns=["pid", "unique_trip_vehicle_day", "detail"])
        trim_6402 = {s: 0 for s in TRIM_6402_STPIDS}
    else:
        pids_in_view = set(view["pid"].astype(str))
        by_route = (
            view.groupby("route", as_index=False)
            .agg(
                rows=("stpid", "size"),
                n_trips=("unique_trip_vehicle_day", "nunique"),
                interpolated_share=("interpolated", "mean"),
            )
            .sort_values("route")
        )
        by_pid = (
            view.groupby("pid", as_index=False)
            .agg(
                route=("route", "first"),
                rtdir=("rtdir", "first"),
                rows=("stpid", "size"),
                n_trips_view=("unique_trip_vehicle_day", "nunique"),
                interpolated_share=("interpolated", "mean"),
            )
        )
        kept_trips = {str(r["pid"]): int(r.get("n_trips", 0)) for r in kept}
        by_pid["n_trips_kept"] = by_pid["pid"].map(kept_trips)
        for pid in sorted(kept_pids - pids_in_view, key=lambda x: int(x)):
            rec = next(r for r in kept if str(r["pid"]) == pid)
            by_pid = pd.concat(
                [
                    by_pid,
                    pd.DataFrame(
                        [
                            {
                                "pid": pid,
                                "route": str(rec["route"]),
                                "rtdir": str(rec["rtdir"]),
                                "rows": 0,
                                "n_trips_view": 0,
                                "interpolated_share": np.nan,
                                "n_trips_kept": int(rec.get("n_trips", 0)),
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        by_pid = by_pid.sort_values("pid", key=lambda s: s.astype(int))

        interp_share = float(view["interpolated"].mean())
        null_obs = int(
            view.loc[~view["interpolated"], "speed_mph"].isna().sum()
        )
        null_interp = int(
            view.loc[view["interpolated"], "speed_mph"].isna().sum()
        )
        backwards = backwards_time_trip_keys(view)
        sub_6402 = view.loc[
            (view["pid"].astype(str) == "6402")
            & (view["stpid"].astype(str).isin(TRIM_6402_STPIDS))
        ]
        trim_6402 = {
            stpid: int((sub_6402["stpid"].astype(str) == stpid).sum())
            for stpid in sorted(TRIM_6402_STPIDS)
        }

    missing_from_view = sorted(kept_pids - pids_in_view, key=lambda x: int(x))
    issues: list[str] = []
    if (
        len(cache_status) > 0
        and cache_status["cache_exists"].all()
        and view.empty
    ):
        issues.append(
            "All kept cache files exist but segment view is empty — "
            "check parquet engine (pyarrow) or per-PID read failures in "
            "build_michigan_segment_view"
        )
    if missing_cache_list:
        issues.append(
            f"{len(missing_cache_list)} kept PID(s) missing local cache: "
            + ", ".join(missing_cache_list[:10])
            + ("..." if len(missing_cache_list) > 10 else "")
        )
    if missing_from_view and not view.empty:
        issues.append(
            f"{len(missing_from_view)} kept PID(s) absent from view: "
            + ", ".join(missing_from_view[:10])
            + ("..." if len(missing_from_view) > 10 else "")
        )
    if not view.empty and len(backwards):
        issues.append(
            f"{len(backwards)} trip(s) with backwards observed bus_stop_time vs seq_index"
        )
    if any(trim_6402.values()):
        issues.append(
            f"PID 6402 has rows at trimmed stops: {trim_6402}"
        )
    if not view.empty and null_obs:
        issues.append(f"{null_obs} observed row(s) with null speed_mph")

    return {
        "n_kept_pids": n_kept,
        "n_pids_in_view": len(pids_in_view),
        "pids_missing_cache": missing_cache_list,
        "pids_missing_from_view": missing_from_view,
        "n_rows": int(len(view)),
        "n_trips": int(view["unique_trip_vehicle_day"].nunique()) if not view.empty else 0,
        "interpolated_share_overall": interp_share,
        "null_speed_mph_observed": null_obs,
        "null_speed_mph_interpolated": null_interp,
        "backwards_time_n_trips": int(len(backwards)),
        "backwards_time_sample": backwards.head(10),
        "pid_6402_trim_stpid_counts": trim_6402,
        "by_route": by_route,
        "by_pid": by_pid,
        "cache_status": cache_status,
        "issues": issues,
    }


def format_segment_view_report(report: dict) -> str:
    """Plain-text summary for notebooks or logs."""
    lines = [
        f"Kept PIDs: {report['n_kept_pids']}; in view: {report['n_pids_in_view']}",
        f"Rows: {report['n_rows']:,}; distinct trips: {report['n_trips']:,}",
    ]
    if report["pids_missing_cache"]:
        lines.append(
            f"Missing cache ({len(report['pids_missing_cache'])}): "
            + ", ".join(report["pids_missing_cache"])
        )
    share = report["interpolated_share_overall"]
    if not np.isnan(share):
        lines.append(f"Interpolated row share: {100 * share:.2f}%")
    lines.append(
        f"Null speed_mph — observed: {report['null_speed_mph_observed']}, "
        f"interpolated: {report['null_speed_mph_interpolated']}"
    )
    lines.append(
        f"Backwards-time trips: {report['backwards_time_n_trips']}"
    )
    lines.append(f"PID 6402 trimmed-stop row counts: {report['pid_6402_trim_stpid_counts']}")
    if report["issues"]:
        lines.append("Issues:")
        lines.extend(f"  - {i}" for i in report["issues"])
    return "\n".join(lines)


def michigan_day_slice_mask(df: pd.DataFrame, slice_name: str) -> pd.Series:
    """all | weekday (Mon–Thu) | friday | weekend (Sat–Sun)."""
    if slice_name == "all":
        return pd.Series(True, index=df.index)
    if "day_of_week" in df.columns:
        dow = df["day_of_week"]
    else:
        dow = pd.to_datetime(df["bus_stop_time"]).dt.dayofweek
    if slice_name == "weekday":
        return dow <= 3
    if slice_name == "friday":
        return dow == 4
    if slice_name == "weekend":
        return dow >= 5
    raise ValueError(
        f"Unknown day_slice {slice_name!r}; use all, weekday, friday, weekend"
    )


def observed_speed_rows(view: pd.DataFrame) -> pd.DataFrame:
    """Observed corridor rows with hour and day_of_week from bus_stop_time."""
    obs = view.loc[~view["interpolated"] & view["bus_stop_time"].notna()].copy()
    if obs.empty:
        return obs
    bst = pd.to_datetime(obs["bus_stop_time"])
    obs["hour"] = bst.dt.hour
    obs["day_of_week"] = bst.dt.dayofweek
    return obs


def shared_observation_window(
    obs: pd.DataFrame,
    hours: int = SHARED_OBSERVATION_WINDOW_HOURS,
) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """
    Keep rows with bus_stop_time in [end - hours, end], where end is max bus_stop_time in obs.
    """
    if obs.empty:
        return obs.copy(), pd.NaT, pd.NaT
    bst = pd.to_datetime(obs["bus_stop_time"])
    end = pd.Timestamp(bst.max())
    start = end - pd.Timedelta(hours=hours)
    mask = (bst >= start) & (bst <= end)
    return obs.loc[mask].copy(), start, end


def hour_stop_speed_stats(
    sub: pd.DataFrame,
    hours: list[int] | None = None,
    *,
    min_obs: int = 10,
) -> pd.DataFrame:
    """
    Hourly stop-level speed_mph stats on a fixed hour index.
    Hours with n < min_obs get NaN stat columns (plot gaps).
    """
    hours = list(hours) if hours is not None else list(DEFAULT_PLOT_HOURS)
    if sub.empty:
        return pd.DataFrame(
            {
                "hour": hours,
                "n": np.nan,
                "median_mph": np.nan,
                "q25_mph": np.nan,
                "q75_mph": np.nan,
                "q05_mph": np.nan,
            }
        )
    grouped = (
        sub.groupby("hour", as_index=False)
        .agg(
            n=("speed_mph", "count"),
            median_mph=("speed_mph", "median"),
            q25_mph=("speed_mph", lambda s: s.quantile(0.25)),
            q75_mph=("speed_mph", lambda s: s.quantile(0.75)),
            q05_mph=("speed_mph", lambda s: s.quantile(0.05)),
        )
    )
    out = grouped.set_index("hour").reindex(hours).reset_index()
    stat_cols = [c for c in out.columns if c not in ("hour", "n")]
    low = out["n"].fillna(0) < min_obs
    out.loc[low, stat_cols] = np.nan
    return out


def filter_dlsd_leak_stops(df: pd.DataFrame) -> pd.DataFrame:
    """Drop Delaware / Chestnut / Pearson rows that leak DLSD speeds into Michigan."""
    if df.empty:
        return df
    stpid = df["stpid"].astype(str)
    rtdir = df["rtdir"].astype(str)
    drop = (
        ((rtdir == "Northbound") & stpid.isin(NORTHBOUND_DLSD_LEAK_STPIDS))
        | ((rtdir == "Southbound") & stpid.isin(SOUTHBOUND_DLSD_LEAK_STPIDS))
    )
    return df.loc[~drop].copy()


def corridor_hourly_median_speed(
    obs: pd.DataFrame,
    day_slice: str,
    hours: list[int] | None = None,
    *,
    exclude_dlsd_leak: bool = True,
) -> pd.DataFrame:
    """Pooled median speed_mph by hour (all routes, directions, stops)."""
    hours = list(hours) if hours is not None else list(DEFAULT_PLOT_HOURS)
    sub = obs.loc[michigan_day_slice_mask(obs, day_slice)]
    if exclude_dlsd_leak:
        sub = filter_dlsd_leak_stops(sub)
    sub = sub.loc[sub["hour"].isin(hours)]
    if sub.empty:
        return pd.DataFrame({"hour": hours, "median_mph": np.nan, "n": 0})
    grouped = (
        sub.groupby("hour", as_index=False)
        .agg(
            median_mph=("speed_mph", "median"),
            n=("speed_mph", "count"),
        )
    )
    out = grouped.set_index("hour").reindex(hours).reset_index()
    out["n"] = out["n"].fillna(0).astype(int)
    return out


def slowest_hours(
    obs: pd.DataFrame,
    day_slice: str,
    n: int = 3,
    hours: list[int] | None = None,
    *,
    exclude_dlsd_leak: bool = True,
) -> list[int]:
    """Hours with the lowest corridor-wide median speed_mph (ties broken by hour)."""
    hourly = corridor_hourly_median_speed(
        obs,
        day_slice,
        hours=hours,
        exclude_dlsd_leak=exclude_dlsd_leak,
    )
    valid = hourly.loc[hourly["median_mph"].notna()].copy()
    if valid.empty:
        return []
    valid = valid.sort_values(["median_mph", "hour"], kind="mergesort")
    chosen = valid.head(n)["hour"].astype(int).tolist()
    return sorted(chosen)


def pooled_stop_speed_quantiles(
    sub: pd.DataFrame,
    *,
    min_obs: int = 10,
) -> dict[str, float]:
    """Single distribution of speed_mph in sub; NaN stats when n < min_obs."""
    nan = {
        "n": 0,
        "median_mph": np.nan,
        "q25_mph": np.nan,
        "q75_mph": np.nan,
        "q05_mph": np.nan,
    }
    if sub.empty:
        return nan
    speeds = sub["speed_mph"].dropna()
    n = int(len(speeds))
    if n < min_obs:
        return {**nan, "n": n}
    return {
        "n": n,
        "median_mph": float(speeds.median()),
        "q25_mph": float(speeds.quantile(0.25)),
        "q75_mph": float(speeds.quantile(0.75)),
        "q05_mph": float(speeds.quantile(0.05)),
    }


def speed_quantiles_to_min_per_mile(stats: dict[str, float]) -> dict[str, float]:
    """
    Map speed quantiles to minutes/mile for plotting (slow = high min/mi).
    IQR band uses 60/q75_mph .. 60/q25_mph; slow tail is 60/q05_mph (p95 time).
    """
    out: dict[str, float] = {
        "n": stats.get("n", 0),
        "median_min_mi": np.nan,
        "q25_min_mi": np.nan,
        "q75_min_mi": np.nan,
        "q95_min_mi": np.nan,
    }
    med = stats.get("median_mph", np.nan)
    q25 = stats.get("q25_mph", np.nan)
    q75 = stats.get("q75_mph", np.nan)
    q05 = stats.get("q05_mph", np.nan)
    if np.isfinite(med) and med > 0:
        out["median_min_mi"] = 60.0 / med
    if np.isfinite(q25) and q25 > 0:
        out["q75_min_mi"] = 60.0 / q25
    if np.isfinite(q75) and q75 > 0:
        out["q25_min_mi"] = 60.0 / q75
    if np.isfinite(q05) and q05 > 0:
        out["q95_min_mi"] = 60.0 / q05
    return out


def corridor_stop_min_per_mile_stats(
    sub: pd.DataFrame,
    sequence: pd.DataFrame,
    *,
    min_obs: int = 10,
) -> pd.DataFrame:
    """Per-stop pooled quantiles on sequence order; lat from sequence."""
    rows: list[dict] = []
    for row in sequence.sort_values("seq_index").itertuples(index=False):
        stpid = str(row.stpid)
        stop_sub = sub.loc[sub["stpid"].astype(str) == stpid]
        mph = pooled_stop_speed_quantiles(stop_sub, min_obs=min_obs)
        mpi = speed_quantiles_to_min_per_mile(mph)
        rows.append(
            {
                "stpid": stpid,
                "lat": float(row.lat),
                "stpnm": str(row.stpnm),
                **mph,
                **mpi,
            }
        )
    return pd.DataFrame(rows)


def corridor_street_tick_positions(
    sequences: dict[str, pd.DataFrame] | None = None,
    *,
    path: Path | None = None,
) -> pd.DataFrame:
    """
    X-axis tick latitudes from corridor stop names (NB + SB sequences).
    Per direction: mean lat of matching stops; if both directions match, average those means.
    """
    sequences = sequences or direction_stop_sequences(path)
    nb = sequences["Northbound"]
    sb = sequences["Southbound"]
    rows: list[dict] = []
    for needle, label in CORRIDOR_STREET_TICK_PATTERNS:
        parts: list[float] = []
        for seq in (nb, sb):
            hits = seq.loc[
                seq["stpnm"].astype(str).str.contains(needle, case=False, regex=False)
            ]
            if not hits.empty:
                parts.append(float(hits["lat"].mean()))
        if not parts:
            continue
        rows.append({"label": label, "lat": float(np.mean(parts))})
    return pd.DataFrame(rows)
