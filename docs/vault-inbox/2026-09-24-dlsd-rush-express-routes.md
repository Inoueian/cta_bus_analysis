---
title: "DLSD rush-hour express routes: 134, 135, 136, 143, 148 — stop pairs and comparison plan"
category: projects
project: cta-bus-analysis
tags: [dlsd, express, rush-hour, 134, 135, 136, 143, 148, comparison]
created: 2026-09-24
source: null
---

Rush-hour-only DLSD express routes **134, 135, 136, 143, 148** extend the existing all-day DLSD work on **146, 147** (`notebooks/dlsd_travel_time_146_147.ipynb`). Separate notebook for stop discovery + comparison (not the 146/147 file).

## Service shape

- **134, 135, 136, 143, 148**: rush-hour-only express on DuSable Lake Shore Drive (DLSD).
- **146, 147**: all-day express on DLSD (baseline notebook exists).

## Downtown DLSD entry (south)

| Route family | Downtown DLSD on-ramp |
|---|---|
| 13x (134, 135, 136) | **Wacker Drive** (further south) |
| 14x (143, 146, 147, 148) | **Michigan & Delaware** (north of Wacker entry) |

Pairing 13x with 14x at the **same northern exit** isolates congestion difference between the two downtown exits.

## Northern DLSD exits (north) — comparison panes

| Northern exit | Routes on same pane |
|---|---|
| Stockton / Arlington (pane title **Fullerton**) | **134**, **143** |
| Belmont | **135**, **146** |
| Irving Park (or nearby) | **136**, **148** |
| Foster (solo pane; was Marine Drive) | **147** alone (furthest north) |

## Primary metric

- Time (and implied speed) on the DLSD segment between the **two stops sandwiching DLSD** (pre-DLSD → post-DLSD bracket), same framing as 146/147 `dlsd_minutes` / bracket logic in `notebooks/dlsd_run_quality.py`.

## Plot specs

- **By hour of day**: median line, IQR band (25–75%), **95th percentile** (worst-case).
- **Comparison notebook** (`notebooks/dlsd_express_comparison_plots.ipynb`): **DLSD minutes only** (13x blue / 14x purple); implied mph omitted for readability. Other artifacts may still use `implied_dlsd_mph` from `hour_dlsd_stats`.
- **Day-of-week slices**: weekday (Mon–Thu), **Friday only**, **weekend** (146/147 only on weekend pane).
- **Rush-only routes (134–136, 143, 148)**: plot stats only at **`valid_rush_plot_cells()`** targets (weekday Mon–Thu **`n_runs >= 30`**). **Friday** panes reuse the same target set; do not require Friday ≥30. Leave gaps outside targets. See vault **`dlsd-rush-hour-min-sample`**; tables: `notebooks/dlsd_rush_sample_counts.ipynb`.

## Boundary pairs (route + direction)

Discovered 2026-09-24 via `notebooks/dlsd_stop_discovery_rush_routes.ipynb` (`getpatterns`, hop **> 10_000 ft**). **11 PIDs** merged into `notebooks/dlsd_boundaries_snapshot.json` (29 PIDs total with 146/147).

| route | rtdir | entry stpid | entry name | exit stpid | exit name |
|-------|-------|-------------|------------|------------|-----------|
| 134 | Northbound | 3954 | Wacker (Upper) & Columbus | 1145 | Stockton & Arlington |
| 134 | Southbound | 1080 | Stockton & Arlington | 14222 | Wacker (Upper) & Columbus |
| 135 | Northbound | 3954 | Wacker (Upper) & Columbus | 1155 | Inner Lake Shore Drive & Belmont |
| 135 | Southbound | 4867 | Lake Shore Drive & Belmont | 14222 | Wacker (Upper) & Columbus |
| 136 | Northbound | 3954 | Wacker (Upper) & Columbus | 4888 | Marine Drive & Irving Park |
| 136 | Southbound | 4864 | Marine Drive & Bittersweet | 14222 | Wacker (Upper) & Columbus |
| 143 | Northbound | 1128 | Michigan & Delaware/Walton | 1145 | Stockton & Arlington |
| 143 | Southbound | 1080 | Stockton & Arlington | 1097 | Michigan & Delaware |
| 148 | Northbound | 1128 | Michigan & Delaware/Walton | 4928 | Irving Park & Marine Drive |
| 148 | Southbound | 4927 | Irving Park & Marine Drive | 1097 | Michigan & Delaware |

- Downtown Wacker anchor for 13x: `3954` (NB entry) / `14222` (SB exit after DLSD hop).
- Shared Michigan & Delaware anchor with 146/147: `1128` (NB entry) / `1097` (SB exit) on 143/148.
- Route **136** SB northern hop uses **Marine Drive & Bittersweet** (`4864`) on some patterns; NB exit **Marine Drive & Irving Park** (`4888`).

After updating snapshot: `env/bin/python scripts/cache_dlsd_parquets.py` then `build_dlsd_runs()` from `notebooks/dlsd_run_quality.py`.

## Repo artifacts

| File | Role |
|---|---|
| `notebooks/dlsd_run_quality.py` | `build_dlsd_runs`, `add_quality_flags`, `load_dlsd_boundaries` |
| `notebooks/dlsd_boundaries_snapshot.json` | PID → entry/exit stops, hop distance |
| `scripts/cache_dlsd_parquets.py` | Cache PIDs listed in boundaries JSON |
| `notebooks/dlsd_stop_discovery_rush_routes.ipynb` | Stop discovery for 134–136, 143, 148; merges into snapshot when `WRITE_SNAPSHOT = True` |
| `notebooks/dlsd_rush_sample_counts.ipynb` | Per-hour run counts; **`valid_rush_plot_cells`** (weekday ≥30 targets) |
| `notebooks/dlsd_express_comparison_plots.ipynb` | Fullerton / Belmont / Irving / Foster panes; weekday, Friday, weekend; minutes-only overlays |

Requires `CTA_API_KEY` in repo-root `.env` for boundary discovery (see `.env.example`).
