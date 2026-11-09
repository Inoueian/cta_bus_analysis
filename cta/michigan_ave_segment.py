"""Michigan Ave corridor segment geometry (getpatterns) and trip timing (Mansueto)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from cta.bustracker import batch_pattern_stops
from cta.mansueto import MANSUETO_TZ, RT_TO_PID_URL, qa_rows
from cta.views import MANSUETO_QA_COLUMNS, legacy_trip_columns
from cta.dlsd_run_quality import DEFAULT_PLOT_HOURS, PARQUET_COLS, local_parquet_path

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
    return repo_root() / "notebooks" / "michigan_ave_stops_snapshot.json"


def kept_pids_path() -> Path:
    return repo_root() / "notebooks" / "michigan_ave_kept_pids.json"


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
    """Deprecated: reads a Mansueto parquet directly; use ``segment_minutes_from_view`` on a run-level view."""
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
    """Northbound: lat ascending; Southbound: lat descending. ``lon`` (additive) gives hop distances."""
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
                "lon": [float(s["lon"]) for s in eligible],
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
    """Deprecated (reads Mansueto parquets and ping-interval speed_mph, rule 6): use ``corridor_stops_from_view``.

    Segment view for all kept PIDs: (trip, stpid) rows with optional speed interpolation."""
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
        if "speed_mph" in view.columns:
            null_obs = int(view.loc[~view["interpolated"], "speed_mph"].isna().sum())
            null_interp = int(view.loc[view["interpolated"], "speed_mph"].isna().sum())
        else:  # stop frames from corridor_stops_from_view carry arrivals, not speeds (ADR-010)
            null_obs = null_interp = 0
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


def _chicago_time(times: pd.Series) -> pd.Series:
    """Datetimes for bucketing: tz-aware values (run-level view, UTC) become America/Chicago; naive ones, the legacy
    frames, already are Chicago wall time (playbook gotcha on Mansueto wall-clock times)."""
    t = pd.to_datetime(times)
    return t.dt.tz_convert(MANSUETO_TZ) if t.dt.tz is not None else t


def michigan_day_slice_mask(df: pd.DataFrame, slice_name: str) -> pd.Series:
    """all | weekday (Mon–Thu) | friday | weekend (Sat–Sun)."""
    if slice_name == "all":
        return pd.Series(True, index=df.index)
    if "day_of_week" in df.columns:
        dow = df["day_of_week"]
    else:
        dow = _chicago_time(df["bus_stop_time"]).dt.dayofweek
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
    interpolated = view["interpolated"] if "interpolated" in view.columns else pd.Series(False, index=view.index)
    obs = view.loc[~interpolated & view["bus_stop_time"].notna()].copy()  # a frame without the column is all observed
    if obs.empty:
        return obs
    bst = _chicago_time(obs["bus_stop_time"])
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
    rtdir = df["rtdir"].astype(str)
    if "from_stpid" in df.columns:  # segment frame: drop a segment touching a leak stop of its direction (ADR-010)
        touches = lambda leak: df["from_stpid"].astype(str).isin(leak) | df["to_stpid"].astype(str).isin(leak)
    else:
        touches = lambda leak: df["stpid"].astype(str).isin(leak)
    drop = ((rtdir == "Northbound") & touches(NORTHBOUND_DLSD_LEAK_STPIDS)) | (
        (rtdir == "Southbound") & touches(SOUTHBOUND_DLSD_LEAK_STPIDS)
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


# --- corridor stops and segment speeds from the run-level view (specs/michigan-segment-from-view.md) ---------

SPEED_BASIS_SEGMENT = "segment"  # ADR-010: speed over the road between consecutive corridor stops, not a ping interval
MAX_HOP_DETOUR_RATIO = 1.5  # archive fixture day: 13,712 of 13,714 positive hops within 1.036x straight line; the other 2 (5.32x) leave Michigan on PID 25899's loop
EARTH_RADIUS_FEET = 20_902_260.0  # mean earth radius 6,371,008.8 m; the detour ratio test is far coarser than the sphere error
FEET_PER_MILE = 5280.0

CORRIDOR_STOP_COLUMNS = [
    "unique_trip_vehicle_day",
    "stpid",
    "pid",
    "route",
    "rtdir",
    "seq_index",
    "lat",
    "stpnm",
    "bus_stop_time",
    "interpolated",
    "source",
    "service_date",
    "calendar_flag",
    "bracket_gap_s",
]
SEGMENT_SPEED_COLUMNS = [
    "unique_trip_vehicle_day",
    "pid",
    "route",
    "rtdir",
    "seg_index",
    "from_stpid",
    "to_stpid",
    "lat",
    "stpnm",
    "bus_stop_time",
    "speed_mph",
    "hop_n_segments",
    "hop_from_stpid",
    "hop_to_stpid",
    "source",
    "service_date",
    "calendar_flag",
    "bracket_gap_s",
    "speed_basis",
]


def segment_minutes_from_view(view: pd.DataFrame, segment_or_record) -> pd.Series:
    """Per-run minutes from entry to exit stop of a ``CorridorSegment`` or a kept-pid record, on a run-level view."""
    get = (lambda k: segment_or_record[k]) if isinstance(segment_or_record, dict) else (lambda k: getattr(segment_or_record, k))
    legacy = legacy_trip_columns(view)
    legacy = legacy.loc[legacy["pid"].astype(str) == str(get("pid"))]
    return trip_segment_minutes(legacy, get("entry_stpid"), get("exit_stpid"))


def straight_line_feet(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two points, in feet."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return float(2 * EARTH_RADIUS_FEET * np.arcsin(np.sqrt(a)))


def _empty_qa() -> pd.DataFrame:
    qa = pd.DataFrame({c: pd.Series(dtype="object") for c in MANSUETO_QA_COLUMNS})
    for c in ("rows_in", "rows_out", "count"):
        qa[c] = qa[c].astype("int64")
    return qa


def _qa_table(parts: dict[str, list[dict]]) -> pd.DataFrame:
    rows = [{"pid": pid, **r} for pid, rs in parts.items() for r in rs]
    return pd.DataFrame(rows, columns=MANSUETO_QA_COLUMNS) if rows else _empty_qa()


def _chosen_direction(rec_dir: str | None, pid_stpids: set[str], sequences: dict[str, pd.DataFrame]) -> str | None:
    """A kept pattern's own direction when it names a sequence; otherwise the sequence holding more of its distinct
    corridor stops (route 157's Westbound / Eastbound); a tie or no corridor stop gives None."""
    if rec_dir in sequences:
        return rec_dir
    counts = {d: len(pid_stpids & set(seq["stpid"].astype(str))) for d, seq in sequences.items()}
    best = max(counts.values(), default=0)
    winners = [d for d, n in counts.items() if n == best]
    return winners[0] if best > 0 and len(winners) == 1 else None


def corridor_stops_from_view(
    view: pd.DataFrame,
    *,
    sequences: dict[str, pd.DataFrame] | None = None,
    kept: list[dict] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Observed Michigan corridor stops per (run, pid) from a run-level view, and the ``corridor`` QA table.

    Replaces ``build_michigan_segment_view`` (no gap rows: ``interpolated`` is always False, kept so
    ``backwards_time_trip_keys`` and ``segment_view_report`` run unchanged). QA reasons: ``pattern_not_kept``,
    ``no_direction_sequence``, ``stop_not_in_sequence``; one per row. QA has one block per pid in the view, plus kept
    pids with no rows.
    """
    sequences = sequences if sequences is not None else direction_stop_sequences()
    kept = load_kept_pid_records() if kept is None else kept
    kept_dir = {str(r["pid"]): str(r["rtdir"]) for r in kept}
    seq_cols = ["stpid", "seq_index", "lat", "stpnm"]
    lookups = {d: seq[seq_cols].astype({"stpid": str}).set_index("stpid") for d, seq in sequences.items()}

    v = view.assign(pattern_id=view["pattern_id"].astype(str), stop_id=view["stop_id"].astype(str))
    frames: list[pd.DataFrame] = []
    qa: dict[str, list[dict]] = {}
    for pid, part in v.groupby("pattern_id", sort=False):
        n = len(part)
        if pid not in kept_dir:
            qa[pid] = qa_rows("corridor", n, 0, {"pattern_not_kept": n})
            continue
        direction = _chosen_direction(kept_dir[pid], set(part["stop_id"]), sequences)
        if direction is None:
            qa[pid] = qa_rows("corridor", n, 0, {"no_direction_sequence": n})
            continue
        lk = lookups[direction]
        inside = part[part["stop_id"].isin(lk.index)]
        qa[pid] = qa_rows("corridor", n, len(inside), {"stop_not_in_sequence": n - len(inside)})
        meta = lk.loc[inside["stop_id"]]
        frames.append(
            pd.DataFrame(
                {
                    "unique_trip_vehicle_day": inside["run_id"].to_numpy(),
                    "stpid": inside["stop_id"].to_numpy(),
                    "pid": pid,
                    "route": inside["route"].astype(str).to_numpy(),
                    "rtdir": direction,
                    "seq_index": meta["seq_index"].astype("int64").to_numpy(),
                    "lat": meta["lat"].astype("float64").to_numpy(),
                    "stpnm": meta["stpnm"].astype(str).to_numpy(),
                    "bus_stop_time": inside["arrival_time"].to_numpy(),
                    "interpolated": False,
                    "source": inside["source"].to_numpy(),
                    "service_date": inside["service_date"].to_numpy(),
                    "calendar_flag": inside["calendar_flag"].to_numpy(),
                    "bracket_gap_s": inside["bracket_gap_s"].astype("float64").to_numpy(),
                }
            )
        )
    for pid in kept_dir:  # kept pids with no rows at all still get a zero-row QA block
        qa.setdefault(pid, qa_rows("corridor", 0, 0, {}))
    if frames:
        out = pd.concat(frames, ignore_index=True)
        out["bus_stop_time"] = pd.to_datetime(out["bus_stop_time"], utc=True)
        out = out.sort_values(["pid", "unique_trip_vehicle_day", "seq_index"], kind="mergesort").reset_index(drop=True)
    else:
        out = pd.DataFrame({c: pd.Series(dtype="object") for c in CORRIDOR_STOP_COLUMNS})
        out["bus_stop_time"] = pd.to_datetime(out["bus_stop_time"], utc=True)
        out["seq_index"] = out["seq_index"].astype("int64")
        out["interpolated"] = out["interpolated"].astype(bool)
    return out[CORRIDOR_STOP_COLUMNS], _qa_table(qa)


def _segment_sequences(stop_sequences: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for direction, seq in stop_sequences.items():
        seq = seq.sort_values("seq_index").reset_index(drop=True)
        a, b = seq.iloc[:-1].reset_index(drop=True), seq.iloc[1:].reset_index(drop=True)
        out[direction] = pd.DataFrame(
            {
                "seg_index": a["seq_index"].astype("int64"),
                "from_stpid": a["stpid"].astype(str),
                "to_stpid": b["stpid"].astype(str),
                "lat": (a["lat"].astype(float) + b["lat"].astype(float)) / 2,
                "stpnm": a["stpnm"].astype(str) + " to " + b["stpnm"].astype(str),
            }
        )
    return out


def direction_segment_sequences(path: Path | None = None) -> dict[str, pd.DataFrame]:
    """One row per consecutive stop pair of each direction sequence; ``seg_index`` is the from stop's ``seq_index``."""
    return _segment_sequences(direction_stop_sequences(path))


def corridor_segment_speeds(
    stops: pd.DataFrame,
    pattern_stops: pd.DataFrame,
    *,
    sequences: dict[str, pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Segment speeds (ADR-010) from ``corridor_stops_from_view`` output, and the ``hops`` QA table.

    A hop joins consecutive observed stops of a run; speed = getpatterns ``pdist_ft`` difference over the arrival-time
    difference, and every segment the hop covers gets it (``hop_n_segments`` says how many). QA rows are candidate hops
    (observed stops minus runs); reasons, in priority: ``missing_pdist``, ``nonpositive_hop_distance``, ``detour_hop``
    (route distance over ``MAX_HOP_DETOUR_RATIO`` times straight line), ``nonpositive_hop_time``.
    """
    sequences = sequences if sequences is not None else direction_stop_sequences()
    segs = _segment_sequences(sequences)
    lonlat = {d: s.astype({"stpid": str}).set_index("stpid")[["lat", "lon"]] for d, s in sequences.items()}
    pdist = (
        pattern_stops.assign(pid=pattern_stops["pid"].astype(str), stpid=pattern_stops["stpid"].astype(str))
        .drop_duplicates(["pid", "stpid"])
        .set_index(["pid", "stpid"])["pdist_ft"]
    )

    s = stops.sort_values(["pid", "unique_trip_vehicle_day", "seq_index"], kind="mergesort").reset_index(drop=True)
    grp = s.groupby(["pid", "unique_trip_vehicle_day"], sort=False)
    prev = pd.DataFrame({c: grp[c].shift(1) for c in ("stpid", "seq_index", "bus_stop_time", "bracket_gap_s")})
    has_prev = prev["stpid"].notna()
    hops = s.loc[has_prev].copy()
    prev = prev.loc[has_prev]
    hops["hop_from_stpid"] = prev["stpid"].astype(str)
    hops["i"] = prev["seq_index"].astype("int64")
    hops["hop_to_stpid"] = hops["stpid"].astype(str)
    hops["j"] = hops["seq_index"].astype("int64")
    hops["t_from"] = prev["bus_stop_time"]
    hops["gap"] = np.maximum(prev["bracket_gap_s"].astype("float64"), hops["bracket_gap_s"].astype("float64"))  # NaN if either is
    idx = list(zip(hops["pid"].astype(str), hops["hop_from_stpid"]))
    idx_to = list(zip(hops["pid"].astype(str), hops["hop_to_stpid"]))
    hops["dist_ft"] = pdist.reindex(idx_to).to_numpy() - pdist.reindex(idx).to_numpy()  # NaN when either pdist is unknown

    straight = np.full(len(hops), np.nan)
    for n, r in enumerate(hops.itertuples(index=False)):
        ll = lonlat[r.rtdir]
        a, b = ll.loc[r.hop_from_stpid], ll.loc[r.hop_to_stpid]
        straight[n] = straight_line_feet(a["lat"], a["lon"], b["lat"], b["lon"])
    hops["straight_ft"] = straight
    hops["dt_s"] = (hops["bus_stop_time"] - hops["t_from"]).dt.total_seconds()

    reason = pd.Series("", index=hops.index, dtype=object)  # first matching reason wins, in the documented priority
    for name, bad in (
        ("missing_pdist", hops["dist_ft"].isna()),
        ("nonpositive_hop_distance", hops["dist_ft"] <= 0),
        ("detour_hop", hops["dist_ft"] > MAX_HOP_DETOUR_RATIO * hops["straight_ft"]),
        ("nonpositive_hop_time", hops["dt_s"] <= 0),
    ):
        reason = reason.mask((reason == "") & bad, name)

    qa: dict[str, list[dict]] = {}
    for pid in dict.fromkeys(s["pid"].astype(str)):
        mine = hops["pid"].astype(str) == pid
        counts = reason[mine & (reason != "")].value_counts().to_dict()
        qa[pid] = qa_rows("hops", int(mine.sum()), int((mine & (reason == "")).sum()), counts)

    ok = hops.loc[reason == ""].copy()
    ok["speed_mph"] = ok["dist_ft"] / FEET_PER_MILE / (ok["dt_s"] / 3600.0)
    ok["hop_n_segments"] = (ok["j"] - ok["i"]).astype("int64")
    ok["start_time"] = ok["t_from"]
    rep = ok.loc[ok.index.repeat(ok["hop_n_segments"])].copy()
    offset = rep.groupby(level=0).cumcount()
    rep["seg_index"] = (rep["i"] + offset).astype("int64")
    rep["_dir"] = rep["rtdir"]
    parts = []
    for direction, seg in segs.items():
        sub = rep[rep["_dir"] == direction].merge(
            seg.rename(columns={"lat": "seg_lat", "stpnm": "seg_stpnm"}), on="seg_index", how="left", validate="m:1"
        )
        parts.append(sub)
    out = pd.concat(parts, ignore_index=True) if parts else rep.iloc[0:0]
    out = out.assign(
        lat=out.get("seg_lat"),
        stpnm=out.get("seg_stpnm"),
        bus_stop_time=out.get("start_time"),
        bracket_gap_s=out.get("gap"),
        speed_basis=SPEED_BASIS_SEGMENT,
    )
    out = out.sort_values(["pid", "unique_trip_vehicle_day", "seg_index"], kind="mergesort").reset_index(drop=True)
    return out[SEGMENT_SPEED_COLUMNS], _qa_table(qa)


def corridor_segment_min_per_mile_stats(
    sub: pd.DataFrame,
    segment_sequence: pd.DataFrame,
    *,
    min_obs: int = 10,
) -> pd.DataFrame:
    """Per-segment pooled quantiles on segment-sequence order (one direction); ``lat`` is the segment midpoint."""
    rows: list[dict] = []
    for row in segment_sequence.sort_values("seg_index").itertuples(index=False):
        seg_sub = sub.loc[sub["seg_index"] == row.seg_index]
        mph = pooled_stop_speed_quantiles(seg_sub, min_obs=min_obs)
        rows.append(
            {
                "seg_index": int(row.seg_index),
                "from_stpid": str(row.from_stpid),
                "to_stpid": str(row.to_stpid),
                "lat": float(row.lat),
                "stpnm": str(row.stpnm),
                **mph,
                **speed_quantiles_to_min_per_mile(mph),
            }
        )
    return pd.DataFrame(rows)
