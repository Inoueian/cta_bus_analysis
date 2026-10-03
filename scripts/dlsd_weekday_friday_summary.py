#!/usr/bin/env python3
"""Compare Mon–Thu vs Friday DLSD run volumes and dlsd_minutes distributions."""

from __future__ import annotations

import argparse
import sys
from io import StringIO
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS = REPO_ROOT / "notebooks"
if str(NOTEBOOKS) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKS))

from dlsd_run_quality import (  # noqa: E402
    ALL_DAY_DLSD_ROUTES,
    DEFAULT_PLOT_HOURS,
    RUSH_ROUTES,
    build_dlsd_runs,
    day_slice_mask,
    hour_dlsd_stats,
    hour_run_counts,
    load_dlsd_boundaries,
    valid_rush_plot_cells,
)


def parse_routes(spec: str) -> frozenset[str]:
    if spec == "rush":
        return RUSH_ROUTES
    if spec == "all":
        return RUSH_ROUTES | ALL_DAY_DLSD_ROUTES
    return frozenset(r.strip() for r in spec.split(",") if r.strip())


def slice_sub(dlsd_runs: pd.DataFrame, slice_name: str, routes: frozenset[str]) -> pd.DataFrame:
    return dlsd_runs.loc[
        day_slice_mask(dlsd_runs, slice_name)
        & dlsd_runs["route"].astype(str).isin({str(r) for r in routes})
    ]


def quant_summary(series: pd.Series) -> dict[str, float | int]:
    if series.empty:
        return {"n": 0, "median": float("nan"), "p25": float("nan"), "p75": float("nan"), "mean": float("nan")}
    return {
        "n": int(len(series)),
        "median": float(series.median()),
        "p25": float(series.quantile(0.25)),
        "p75": float(series.quantile(0.75)),
        "mean": float(series.mean()),
    }


def median_at_hour(
    dlsd_runs: pd.DataFrame,
    slice_name: str,
    route: str,
    rtdir: str,
    hour: int,
) -> float:
    sub = dlsd_runs.loc[
        day_slice_mask(dlsd_runs, slice_name)
        & (dlsd_runs["route"].astype(str) == str(route))
        & (dlsd_runs["rtdir"] == rtdir)
    ]
    stats = hour_dlsd_stats(
        sub,
        DEFAULT_PLOT_HOURS,
        route=str(route),
        rtdir=rtdir,
        valid_cells=None,
    )
    row = stats.loc[stats["hour"] == hour]
    if row.empty:
        return float("nan")
    val = row.iloc[0]["median_min"]
    return float(val) if pd.notna(val) else float("nan")


def _df_to_markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if pd.isna(v):
                cells.append("")
            elif c in ("weekday_n", "friday_n", "hour", "n"):
                cells.append(str(int(v)))
            elif isinstance(v, float) and (c.endswith("_min") or c == "delta_median"):
                cells.append(f"{v:.2f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_report(
    dlsd_runs: pd.DataFrame,
    routes: frozenset[str],
    cache_variant: str,
) -> str:
    out = StringIO()
    w = out.write

    ok = dlsd_runs.loc[dlsd_runs["analysis_ok"]].copy()
    ok["route"] = ok["route"].astype(str)
    ok = ok.loc[ok["route"].isin({str(r) for r in routes})]

    w(f"# DLSD Mon–Thu vs Friday summary\n\n")
    w(f"Cache: `{cache_variant}`; routes: `{','.join(sorted(routes))}`; population: `analysis_ok` only.\n\n")

    wd = slice_sub(ok, "weekday", routes)
    fr = slice_sub(ok, "friday", routes)

    w("## 1. Global volume\n\n")
    w("| slice | n_runs | entry_time min | entry_time max |\n")
    w("|-------|--------|----------------|----------------|\n")
    for name, sub in [("weekday (Mon–Thu)", wd), ("friday", fr)]:
        tmin = sub["entry_time"].min() if len(sub) else pd.NaT
        tmax = sub["entry_time"].max() if len(sub) else pd.NaT
        w(f"| {name} | {len(sub):,} | {tmin} | {tmax} |\n")
    ratio = len(fr) / len(wd) if len(wd) else float("nan")
    w(f"\nFriday / weekday count ratio: **{ratio:.3f}**.\n")
    w(
        "Mon–Thu spans four calendar days vs one for Friday; "
        f"rough runs-per-day: weekday **{len(wd) / 4:,.0f}**/day, "
        f"friday **{len(fr):,.0f}**/day.\n\n"
    )

    w("## 2. Pooled dlsd_minutes\n\n")
    w("| pool | slice | n | median | p25 | p75 | mean |\n")
    w("|------|-------|---|--------|-----|-----|------|\n")
    for pool_name, pool_routes in [
        ("rush", RUSH_ROUTES & routes),
        ("146+147", ALL_DAY_DLSD_ROUTES & routes),
    ]:
        if not pool_routes:
            continue
        for slice_name, label in [("weekday", "Mon–Thu"), ("friday", "Friday")]:
            sub = slice_sub(ok, slice_name, pool_routes)
            q = quant_summary(sub["dlsd_minutes"])
            w(
                f"| {pool_name} | {label} | {q['n']:,} | {q['median']:.2f} | "
                f"{q['p25']:.2f} | {q['p75']:.2f} | {q['mean']:.2f} |\n"
            )
    w("\n")

    w("## 3. Per route × direction\n\n")
    rows = []
    for (route, rtdir), grp in ok.groupby(["route", "rtdir"], sort=True):
        wd_g = grp.loc[day_slice_mask(grp, "weekday")]
        fr_g = grp.loc[day_slice_mask(grp, "friday")]
        wd_med = wd_g["dlsd_minutes"].median() if len(wd_g) else float("nan")
        fr_med = fr_g["dlsd_minutes"].median() if len(fr_g) else float("nan")
        delta = fr_med - wd_med if pd.notna(wd_med) and pd.notna(fr_med) else float("nan")
        rows.append(
            {
                "route": route,
                "rtdir": rtdir,
                "weekday_n": len(wd_g),
                "friday_n": len(fr_g),
                "weekday_median_min": wd_med,
                "friday_median_min": fr_med,
                "delta_median": delta,
            }
        )
    rtdf = pd.DataFrame(rows)
    rtdf["abs_delta"] = rtdf["delta_median"].abs()
    rtdf = rtdf.sort_values("abs_delta", ascending=False, na_position="last")
    w(_df_to_markdown(rtdf.drop(columns=["abs_delta"])))
    w("\n\n")

    w("## 4. Rush valid plot cells (weekday ≥30 targets)\n\n")
    valid = valid_rush_plot_cells(ok)
    wd_counts = hour_run_counts(ok, routes=RUSH_ROUTES, day_slice="weekday")
    fr_counts = hour_run_counts(ok, routes=RUSH_ROUTES, day_slice="friday")
    cell_rows = []
    for _, cell in valid.iterrows():
        route = str(cell["route"])
        rtdir = cell["rtdir"]
        hour = int(cell["hour"])
        wd_n = int(
            wd_counts.loc[
                (wd_counts["route"].astype(str) == route)
                & (wd_counts["rtdir"] == rtdir)
                & (wd_counts["hour"] == hour),
                "n_runs",
            ].sum()
        )
        fr_match = fr_counts.loc[
            (fr_counts["route"].astype(str) == route)
            & (fr_counts["rtdir"] == rtdir)
            & (fr_counts["hour"] == hour),
            "n_runs",
        ]
        fr_n = int(fr_match.iloc[0]) if len(fr_match) else 0
        wd_med = median_at_hour(ok, "weekday", route, rtdir, hour)
        fr_med = median_at_hour(ok, "friday", route, rtdir, hour)
        delta = fr_med - wd_med if pd.notna(wd_med) and pd.notna(fr_med) else float("nan")
        cell_rows.append(
            {
                "route": route,
                "rtdir": rtdir,
                "hour": hour,
                "weekday_n": wd_n,
                "friday_n": fr_n,
                "weekday_median_min": wd_med,
                "friday_median_min": fr_med,
                "delta_median": delta,
            }
        )
    cdf = pd.DataFrame(cell_rows)
    w(_df_to_markdown(cdf))
    w("\n\n")
    below30 = int((cdf["friday_n"] < 30).sum())
    w(f"Valid cells with Friday `n_runs` < 30: **{below30}** / {len(cdf)}.\n")
    with_fr = cdf.loc[cdf["friday_n"] > 0, "delta_median"].dropna()
    if len(with_fr):
        w(f"Median `delta_median` (Fri − Mon–Thu) among cells with Friday data: **{with_fr.median():.2f}** min.\n")

    return out.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-variant",
        default="last365d",
        help="Mansueto cache suffix (default: last365d)",
    )
    parser.add_argument(
        "--routes",
        default="rush",
        help='Route filter: "rush", "all", or comma-separated route numbers',
    )
    parser.add_argument(
        "--write-md",
        type=Path,
        default=None,
        help="Optional path to write markdown report",
    )
    args = parser.parse_args()
    routes = parse_routes(args.routes)

    print("Loading dlsd_runs ...", file=sys.stderr)
    boundaries = load_dlsd_boundaries()
    dlsd_runs = build_dlsd_runs(
        boundaries,
        prefer_local=True,
        cache_variant=args.cache_variant,
    )
    report = build_report(dlsd_runs, routes, args.cache_variant)

    if args.write_md:
        args.write_md.parent.mkdir(parents=True, exist_ok=True)
        args.write_md.write_text(report)
        print(f"Wrote {args.write_md}", file=sys.stderr)
    print(report)


if __name__ == "__main__":
    main()
