"""Great-circle distances in feet (specs/stop-validity-measurement.md).

Imports nothing from ``cta``, so any module can use it without a cycle: ``cta.michigan_ave_segment`` imports
``cta.views``, and ``cta.views`` imports ``cta.stop_validity``, which needs the distance helpers.
"""

from __future__ import annotations

import numpy as np

EARTH_RADIUS_FEET = 20_902_260.0  # mean earth radius 6,371,008.8 m; the detour ratio test is far coarser than the sphere error


def straight_line_feet(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two points, in feet."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return float(2 * EARTH_RADIUS_FEET * np.arcsin(np.sqrt(a)))


def nearest_feet(lat: float, lon: float, lats, lons) -> float:
    """Haversine distance in feet from one point to the nearest of many (``lats`` and ``lons`` aligned, non-empty)."""
    lats, lons = np.asarray(lats, dtype="float64"), np.asarray(lons, dtype="float64")
    if lats.size == 0 or lats.shape != lons.shape:
        raise ValueError(f"nearest_feet needs one or more aligned points, got {lats.shape} latitudes and {lons.shape} longitudes")
    p1, p2 = np.radians(lat), np.radians(lats)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lons - lon) / 2) ** 2
    return float(2 * EARTH_RADIUS_FEET * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))).min())
