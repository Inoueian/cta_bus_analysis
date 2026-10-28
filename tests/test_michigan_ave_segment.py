"""Tests for notebooks/michigan_ave_segment.py."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

NOTEBOOKS = Path(__file__).resolve().parent.parent / "notebooks"
if str(NOTEBOOKS) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKS))

from michigan_ave_segment import (  # noqa: E402
    DEFAULT_MIN_ENTRY_EXIT_SHARE,
    backwards_time_trip_keys,
    corridor_hourly_median_speed,
    corridor_street_tick_positions,
    direction_stop_sequences,
    endpoint_coverage,
    filter_dlsd_leak_stops,
    hour_stop_speed_stats,
    interpolate_trip_corridor,
    kept_pid_cache_status,
    longest_corridor_run,
    michigan_day_slice_mask,
    observed_speed_rows,
    pid_timing_summary_row,
    pooled_stop_speed_quantiles,
    segment_from_pattern_stops,
    segment_view_report,
    shared_observation_window,
    slowest_hours,
    speed_quantiles_to_min_per_mile,
    trip_segment_minutes,
)
from michigan_ave_segment import CorridorSegment  # noqa: E402


def test_module_imports():
    import michigan_ave_segment  # noqa: F401


def _stops_df(rows: list[tuple[str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"stpid": s, "lat": lat, "stpnm": name} for s, lat, name in rows]
    )


def test_longest_corridor_run_gap_keeps_longer_side():
    corridor = {"10", "11", "12", "20", "21", "22"}
    stops = _stops_df(
        [
            ("10", 41.87, "A"),
            ("11", 41.88, "B"),
            ("99", 41.885, "off"),
            ("20", 41.89, "C"),
            ("21", 41.90, "D"),
            ("22", 41.91, "E"),
        ]
    )
    run = longest_corridor_run(stops, corridor)
    assert run is not None
    entry, exit_, n, stpids = run
    assert (entry, exit_, n) == ("20", "22", 3)
    assert stpids == ("20", "21", "22")


def test_longest_corridor_run_single_stop_returns_none():
    corridor = {"10", "11"}
    stops = _stops_df([("10", 41.87, "A"), ("99", 41.88, "off")])
    assert longest_corridor_run(stops, corridor) is None


def test_trip_segment_minutes_median():
    entry, exit_ = "100", "102"
    df = pd.DataFrame(
        {
            "unique_trip_vehicle_day": ["t1", "t1", "t1", "t2", "t2", "t2"],
            "stpid": ["100", "101", "102", "100", "101", "102"],
            "bus_stop_time": pd.to_datetime(
                [
                    "2024-01-01 08:00:00",
                    "2024-01-01 08:03:00",
                    "2024-01-01 08:10:00",
                    "2024-01-01 09:00:00",
                    "2024-01-01 09:02:00",
                    "2024-01-01 09:04:00",
                ]
            ),
        }
    )
    minutes = trip_segment_minutes(df, entry, exit_)
    assert minutes["t1"] == 10.0
    assert minutes["t2"] == 4.0
    assert float(minutes.median()) == 7.0

    seg = CorridorSegment(
        pid="1",
        route="1",
        rtdir="Northbound",
        entry_stpid=entry,
        exit_stpid=exit_,
        entry_stpnm="A",
        exit_stpnm="C",
        n_stops=3,
        stop_stpids=("100", "101", "102"),
    )
    row = pid_timing_summary_row(seg, minutes)
    assert row["median_minutes"] == 7.0
    assert row["n_trips"] == 2
    assert row["share_under_5_min"] == 0.5


def test_endpoint_coverage_entry_without_exit():
    """6402-like: many trips at entry, zero at pattern exit."""
    corridor = {"1097", "1103", "18396"}
    df = pd.DataFrame(
        {
            "unique_trip_vehicle_day": [f"t{i}" for i in range(3)] * 2,
            "stpid": ["1097", "1103", "1097", "1103", "1097", "1103"],
            "stop_sequence": [10, 11, 10, 11, 10, 11],
            "bus_stop_time": pd.to_datetime(
                [
                    "2024-01-01 08:00:00",
                    "2024-01-01 08:05:00",
                    "2024-01-01 09:00:00",
                    "2024-01-01 09:04:00",
                    "2024-01-01 10:00:00",
                    "2024-01-01 10:06:00",
                ]
            ),
        }
    )
    cov = endpoint_coverage(df, "1097", "18396", corridor)
    assert cov["n_trips_entry"] == 3
    assert cov["n_trips_exit"] == 0
    assert cov["n_trips_both"] == 0
    assert cov["share_entry_with_exit"] == 0.0
    assert cov["low_entry_exit_coverage"] is True
    assert cov["mode_last_corridor_stpid"] == "1103"
    assert cov["share_entry_with_exit"] < DEFAULT_MIN_ENTRY_EXIT_SHARE


def test_segment_from_pattern_stops():
    corridor = {"1591", "1580", "1097"}
    stops = _stops_df(
        [
            ("999", 41.86, "off"),
            ("1591", 41.867, "Michigan & Roosevelt"),
            ("1580", 41.868, "Michigan & Roosevelt NB"),
            ("1097", 41.899, "Delaware"),
        ]
    )
    seg = segment_from_pattern_stops("6351", "1", "Southbound", stops, corridor)
    assert seg is not None
    assert seg.entry_stpid == "1591"
    assert seg.exit_stpid == "1097"
    assert seg.n_stops == 3


def test_direction_stop_sequences_lat_order():
    seqs = direction_stop_sequences()
    nb = seqs["Northbound"]
    sb = seqs["Southbound"]
    assert len(nb) > 0 and len(sb) > 0
    assert nb["lat"].is_monotonic_increasing
    assert sb["lat"].is_monotonic_decreasing
    assert nb["seq_index"].tolist() == list(range(len(nb)))
    assert sb["seq_index"].tolist() == list(range(len(sb)))


def _mini_sequence() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "seq_index": [0, 1, 2, 3],
            "stpid": ["100", "101", "102", "103"],
            "lat": [41.87, 41.88, 41.89, 41.90],
            "stpnm": ["A", "B", "C", "D"],
        }
    )


def test_interpolate_trip_corridor_skipped_middle_stop():
    sequence = _mini_sequence()
    trip = pd.DataFrame(
        {
            "unique_trip_vehicle_day": ["t1"] * 3,
            "stpid": ["100", "102", "103"],
            "bus_stop_time": pd.to_datetime(
                [
                    "2024-01-01 08:00:00",
                    "2024-01-01 08:10:00",
                    "2024-01-01 08:15:00",
                ]
            ),
            "speed_mph": [10.0, 30.0, 20.0],
        }
    )
    out = interpolate_trip_corridor(
        "t1", trip, sequence, pid="1", route="1", rtdir="Northbound"
    )
    assert len(out) == 4
    mid = out.loc[out["stpid"] == "101"].iloc[0]
    assert bool(mid["interpolated"])
    assert mid["speed_mph"] == 20.0
    assert pd.isna(mid["bus_stop_time"])
    assert set(out["stpid"]) == {"100", "101", "102", "103"}


def test_interpolate_trip_corridor_outside_span_omitted():
    sequence = _mini_sequence()
    trip = pd.DataFrame(
        {
            "unique_trip_vehicle_day": ["t1", "t1"],
            "stpid": ["101", "102"],
            "bus_stop_time": pd.to_datetime(
                ["2024-01-01 08:00:00", "2024-01-01 08:05:00"]
            ),
            "speed_mph": [12.0, 18.0],
        }
    )
    out = interpolate_trip_corridor(
        "t1", trip, sequence, pid="1", route="1", rtdir="Northbound"
    )
    assert out["stpid"].tolist() == ["101", "102"]
    assert not out["interpolated"].any()


def test_kept_pid_cache_status_all_missing_when_no_files(monkeypatch, tmp_path):
    kept = tmp_path / "kept.json"
    kept.write_text(
        '{"pids": [{"pid": "99999991", "route": "3", "rtdir": "Northbound", "n_trips": 10}]}'
    )
    status = kept_pid_cache_status(cache_variant="last30d", kept_path=kept)
    assert len(status) == 1
    assert not bool(status.iloc[0]["cache_exists"])


def test_backwards_time_trip_keys_detects_decreasing_times():
    view = pd.DataFrame(
        {
            "unique_trip_vehicle_day": ["t1", "t1"],
            "stpid": ["100", "101"],
            "pid": ["1", "1"],
            "route": ["3", "3"],
            "rtdir": ["Northbound", "Northbound"],
            "seq_index": [0, 1],
            "lat": [41.87, 41.88],
            "stpnm": ["A", "B"],
            "bus_stop_time": pd.to_datetime(
                ["2024-01-01 08:10:00", "2024-01-01 08:00:00"]
            ),
            "speed_mph": [10.0, 10.0],
            "interpolated": [False, False],
        }
    )
    backwards = backwards_time_trip_keys(view)
    assert len(backwards) == 1
    assert backwards.iloc[0]["unique_trip_vehicle_day"] == "t1"


def test_segment_view_report_synthetic_with_kept_path(tmp_path):
    kept = tmp_path / "kept.json"
    kept.write_text(
        '{"cache_variant": "last30d", "pids": ['
        '{"pid": "1", "route": "3", "rtdir": "Northbound", "n_trips": 5},'
        '{"pid": "2", "route": "4", "rtdir": "Southbound", "n_trips": 1}'
        "]}"
    )
    view = pd.DataFrame(
        {
            "unique_trip_vehicle_day": ["t1"],
            "stpid": ["100"],
            "pid": ["1"],
            "route": ["3"],
            "rtdir": ["Northbound"],
            "seq_index": [0],
            "lat": [41.87],
            "stpnm": ["A"],
            "bus_stop_time": pd.to_datetime(["2024-01-01 08:00:00"]),
            "speed_mph": [10.0],
            "interpolated": [False],
        }
    )
    cache = kept_pid_cache_status(cache_variant="last30d", kept_path=kept)
    report = segment_view_report(view, kept_path=kept, cache_status=cache)
    assert report["n_kept_pids"] == 2
    assert report["n_pids_in_view"] == 1
    assert report["pids_missing_from_view"] == ["2"]
    assert report["null_speed_mph_observed"] == 0
    assert not cache["cache_exists"].any()

    view_null = view.copy()
    view_null.loc[0, "speed_mph"] = np.nan
    report_null = segment_view_report(view_null, kept_path=kept, cache_status=cache)
    assert report_null["null_speed_mph_observed"] == 1


def test_michigan_day_slice_mask_all_and_weekday():
    times = pd.to_datetime(
        [
            "2024-01-01 08:00",  # Mon
            "2024-01-02 08:00",  # Tue
            "2024-01-05 08:00",  # Fri
            "2024-01-06 08:00",  # Sat
        ]
    )
    df = pd.DataFrame({"bus_stop_time": times})
    assert michigan_day_slice_mask(df, "all").all()
    wd = michigan_day_slice_mask(df, "weekday")
    assert wd.tolist() == [True, True, False, False]
    assert michigan_day_slice_mask(df, "friday").tolist() == [False, False, True, False]
    assert michigan_day_slice_mask(df, "weekend").tolist() == [False, False, False, True]


def test_shared_observation_window_720_hours_from_max():
    end = pd.Timestamp("2026-07-28 12:00:00")
    inside = end - pd.Timedelta(hours=720)
    outside = end - pd.Timedelta(hours=721)
    obs = pd.DataFrame(
        {
            "bus_stop_time": [end, inside, outside],
            "pid": ["1", "1", "2"],
            "speed_mph": [10.0, 11.0, 12.0],
            "interpolated": [False, False, False],
            "hour": [12, 12, 12],
            "day_of_week": [0, 0, 0],
        }
    )
    filtered, start, end_out = shared_observation_window(obs, hours=720)
    assert end_out == end
    assert start == end - pd.Timedelta(hours=720)
    assert len(filtered) == 2
    assert set(filtered["pid"].astype(str)) == {"1"}
    assert "2" not in filtered["pid"].astype(str).tolist()


def test_observed_speed_rows_drops_interpolated():
    view = pd.DataFrame(
        {
            "interpolated": [False, True],
            "bus_stop_time": pd.to_datetime(["2024-01-01 09:30:00", None]),
            "speed_mph": [10.0, 12.0],
        }
    )
    out = observed_speed_rows(view)
    assert len(out) == 1
    assert out.iloc[0]["hour"] == 9
    assert out.iloc[0]["day_of_week"] == 0


def test_hour_stop_speed_stats_quantiles_and_min_obs():
    sub = pd.DataFrame(
        {
            "hour": [8] * 10 + [9] * 5,
            "speed_mph": list(range(1, 11)) + [20.0, 21.0, 22.0, 23.0, 24.0],
        }
    )
    out = hour_stop_speed_stats(sub, hours=[8, 9], min_obs=10)
    assert out.loc[out["hour"] == 8, "n"].iloc[0] == 10
    assert out.loc[out["hour"] == 8, "median_mph"].iloc[0] == 5.5
    assert out.loc[out["hour"] == 8, "q05_mph"].iloc[0] == 1.45
    assert out.loc[out["hour"] == 9, "n"].iloc[0] == 5
    assert pd.isna(out.loc[out["hour"] == 9, "median_mph"].iloc[0])


def test_hour_stop_speed_stats_empty_sub():
    out = hour_stop_speed_stats(pd.DataFrame(), hours=[8, 9], min_obs=10)
    assert list(out["hour"]) == [8, 9]
    assert out["median_mph"].isna().all()


def test_filter_dlsd_leak_stops_direction_specific():
    df = pd.DataFrame(
        {
            "rtdir": ["Northbound", "Southbound", "Northbound", "Southbound"],
            "stpid": ["1127", "1097", "1580", "1098"],
            "speed_mph": [1.0, 2.0, 3.0, 4.0],
        }
    )
    out = filter_dlsd_leak_stops(df)
    assert len(out) == 1
    assert out.iloc[0]["stpid"] == "1580"


def test_slowest_hours_picks_low_median_hours():
    obs = pd.DataFrame(
        {
            "bus_stop_time": pd.to_datetime(["2024-01-01 08:00"] * 5 + ["2024-01-01 17:00"] * 5),
            "speed_mph": [5.0] * 5 + [20.0] * 5,
            "stpid": ["1580"] * 10,
            "rtdir": ["Northbound"] * 10,
            "interpolated": [False] * 10,
        }
    )
    obs = observed_speed_rows(obs)
    hours = slowest_hours(obs, "weekday", n=1, hours=[8, 9, 17])
    assert hours == [8]


def test_speed_quantiles_to_min_per_mile_slow_tail():
    mph = pooled_stop_speed_quantiles(
        pd.DataFrame({"speed_mph": list(range(1, 11))}),
        min_obs=10,
    )
    mpi = speed_quantiles_to_min_per_mile(mph)
    assert mpi["median_min_mi"] == 60.0 / 5.5
    assert mpi["q95_min_mi"] == 60.0 / mph["q05_mph"]
    assert mpi["q25_min_mi"] == 60.0 / mph["q75_mph"]
    assert mpi["q75_min_mi"] == 60.0 / mph["q25_mph"]


def test_corridor_street_tick_positions_averages_directions():
    sequences = {
        "Northbound": pd.DataFrame(
            {
                "stpnm": ["Michigan & Roosevelt", "Michigan & Madison"],
                "lat": [41.0, 42.0],
            }
        ),
        "Southbound": pd.DataFrame(
            {
                "stpnm": ["Michigan & Roosevelt", "Michigan & Monroe"],
                "lat": [41.2, 41.5],
            }
        ),
    }
    ticks = corridor_street_tick_positions(sequences)
    roosevelt = ticks.loc[ticks["label"] == "Roosevelt", "lat"].iloc[0]
    assert roosevelt == (41.0 + 41.2) / 2
    madison = ticks.loc[ticks["label"] == "Madison", "lat"].iloc[0]
    assert madison == 42.0


def test_corridor_hourly_median_speed_respects_day_slice():
    obs = pd.DataFrame(
        {
            "bus_stop_time": pd.to_datetime(
                ["2024-01-01 08:00", "2024-01-06 08:00"]
            ),
            "speed_mph": [10.0, 30.0],
            "stpid": ["1580", "1580"],
            "rtdir": ["Northbound", "Northbound"],
            "interpolated": [False, False],
        }
    )
    obs = observed_speed_rows(obs)
    wd = corridor_hourly_median_speed(obs, "weekday", hours=[8])
    we = corridor_hourly_median_speed(obs, "weekend", hours=[8])
    assert wd.iloc[0]["median_mph"] == 10.0
    assert we.iloc[0]["median_mph"] == 30.0


def test_interpolate_trip_corridor_single_stop_not_padded():
    sequence = _mini_sequence()
    trip = pd.DataFrame(
        {
            "unique_trip_vehicle_day": ["t1"],
            "stpid": ["102"],
            "bus_stop_time": pd.to_datetime(["2024-01-01 08:00:00"]),
            "speed_mph": [15.0],
        }
    )
    out = interpolate_trip_corridor(
        "t1", trip, sequence, pid="1", route="1", rtdir="Northbound"
    )
    assert len(out) == 1
    assert out.iloc[0]["stpid"] == "102"
    assert not bool(out.iloc[0]["interpolated"])
