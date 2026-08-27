"""
compare_h12_iso249.py
---------------------
Cross-check a plastics MFA run computed at native **H12** region resolution
against a run computed at **iso249** (country) resolution, with the iso249
results aggregated up to H12 regions.

The two runs should agree closely once the country-level run is aggregated:
region-aggregated results must be (near) invariant to the spatial resolution at
which the model was solved.  Where they diverge, the difference is caused by
resolution-dependent steps (per-capita stock extrapolation over GDP/capita,
lifetime cohort dynamics, trade equilibrium) that are non-linear in region size.

Compared quantities (per H12 region + global):
  1. In-use stock per capita  vs  GDP per capita   (the stock regression view)
  2. Stock inflow (demand)
  3. Primary production        (polymerization => primary_market)

Aggregation rule: extensive quantities (stock, inflow, production, population,
GDP = gdppc*population) are SUMMED over the countries of each H12 region; the
per-capita / intensive quantities (stock-pc, GDP-pc) are then recomputed from
the summed totals.

Usage:
  uv run --no-sync python scripts/compare_h12_iso249.py
  uv run --no-sync python scripts/compare_h12_iso249.py <h12.pickle> <iso249.pickle>
  uv run --no-sync python scripts/compare_h12_iso249.py --show
  uv run --no-sync python scripts/compare_h12_iso249.py --mapping I:\\mappings\\regionmappingH12.csv

Note: `--no-sync` avoids a TLS error on this machine; a `pyam` stub is injected
because importing the export module (done during unpickling) otherwise aborts
the process.  Pickles written on a branch with extra config classes are loaded
with a tolerant unpickler that stubs any missing config class.

NOTE: This script is un-reviewed vibe-coding.
"""

import argparse
import importlib
import pathlib
import pickle
import sys
import types

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.colors as plc
from plotly.subplots import make_subplots
from pydantic import ConfigDict

# ── make unpickling safe on this machine ───────────────────────────────────────
# importing remind_mfa.plastics.plastics_export (triggered by unpickling) does a
# top-level `import pyam`, which C-aborts on this Windows box.  A dummy module is
# enough because nothing we touch actually calls into pyam.
sys.modules.setdefault("pyam", types.ModuleType("pyam"))

from remind_mfa.common.helpers import RemindMFABaseModel  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]

DEFAULT_H12 = REPO / (
    "data/plastics/output/export/pickle/model_plastics_SSP2_h12_2026-08-26--15-51-55.pickle"
)
DEFAULT_ISO = REPO / (
    "data/plastics/output/export/pickle/model_plastics_SSP2_iso249_2026-08-24--17-33-52.pickle"
)
DEFAULT_MAPPING = pathlib.Path(r"I:\mappings\regionmappingH12.csv")
DEFAULT_OUT = REPO / "data" / "compare_h12_iso249"

# flow whose (t, r) sum is reported as "production"
PRODUCTION_FLOW = "polymerization => primary_market"

COLOR_H12 = "#1f77b4"  # solid
COLOR_ISO = "#d62728"  # dashed
SUMMARY_YEARS = [2020, 2050, 2100]


# ── tolerant loader ─────────────────────────────────────────────────────────────


class _TolerantUnpickler(pickle.Unpickler):
    """Unpickler that stubs config classes removed from the current branch.

    The iso249 run was produced on a branch carrying extra
    ``*ExportCfg`` classes.  We only ever read ``model.future_mfa``, so a
    permissive pydantic stub (reconstructed via ``__setstate__``) is sufficient.
    """

    def find_class(self, module, name):
        try:
            return super().find_class(module, name)
        except (AttributeError, ModuleNotFoundError):
            mod = importlib.import_module(module)
            stub = type(name, (RemindMFABaseModel,), {"model_config": ConfigDict(extra="allow")})
            setattr(mod, name, stub)
            return stub


def load_mfa(path: pathlib.Path):
    print(f"  loading {path.name} …")
    with path.open("rb") as fh:
        model = _TolerantUnpickler(fh).load()
    return model.future_mfa


# ── data extraction ──────────────────────────────────────────────────────────────


def tidy_tr(arr) -> pd.DataFrame:
    """Sum a FlodymArray to (Time, Region) and return a tidy DataFrame.

    Columns: ``year`` (int), ``region`` (str), ``value`` (float).
    """
    df = arr.sum_to(("t", "r")).to_df().reset_index()
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns={"time": "year", "region": "region"})
    df["year"] = df["year"].astype(int)
    df["region"] = df["region"].astype(str)
    return df[["year", "region", "value"]]


def extract_extensive(mfa) -> pd.DataFrame:
    """Return a long DataFrame of the extensive quantities for one run.

    Columns: year, region, population, stock, inflow, production, gdp_total.
    All are summed to (Time, Region); ``gdp_total = gdppc * population``.
    """
    population = tidy_tr(mfa.parameters["population"]).rename(columns={"value": "population"})
    gdppc = tidy_tr(mfa.parameters["gdppc"]).rename(columns={"value": "gdppc"})
    stock = tidy_tr(mfa.stocks["in_use"].stock).rename(columns={"value": "stock"})
    inflow = tidy_tr(mfa.stocks["in_use"].inflow).rename(columns={"value": "inflow"})
    if PRODUCTION_FLOW not in mfa.flows:
        raise KeyError(f"production flow {PRODUCTION_FLOW!r} not present in run")
    production = tidy_tr(mfa.flows[PRODUCTION_FLOW]).rename(columns={"value": "production"})

    df = population
    for other in (gdppc, stock, inflow, production):
        df = df.merge(other, on=["year", "region"], how="outer")
    df["gdp_total"] = df["gdppc"] * df["population"]
    return df.drop(columns="gdppc")


def read_region_mapping(path: pathlib.Path) -> dict[str, str]:
    """Map ISO3 country code -> H12 region code from the madrat region mapping."""
    df = pd.read_csv(path, delimiter=";")
    return dict(zip(df["CountryCode"].astype(str), df["RegionCode"].astype(str)))


def aggregate_to_h12(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Aggregate a country-level extensive DataFrame to H12 regions."""
    out = df.copy()
    unmapped = sorted(set(out["region"]) - set(mapping))
    if unmapped:
        print(f"  WARNING: {len(unmapped)} country codes not in mapping, dropped: {unmapped}")
        out = out[out["region"].isin(mapping)]
    out["region"] = out["region"].map(mapping)
    ext_cols = ["population", "stock", "inflow", "production", "gdp_total"]
    return out.groupby(["year", "region"], as_index=False)[ext_cols].sum()


def add_intensive(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-capita / intensive columns recomputed from the summed totals."""
    out = df.copy()
    out["stock_pc"] = out["stock"] / out["population"]
    out["gdppc"] = out["gdp_total"] / out["population"]
    return out


def add_global(df: pd.DataFrame) -> pd.DataFrame:
    """Append a synthetic ``GLOBAL`` region (sum of all regions) to the frame."""
    ext_cols = ["population", "stock", "inflow", "production", "gdp_total"]
    glob = df.groupby("year", as_index=False)[ext_cols].sum()
    glob["region"] = "GLOBAL"
    return pd.concat([df, glob], ignore_index=True)


# ── figures ──────────────────────────────────────────────────────────────────────


def _subplot_grid(regions: list[str]):
    n_cols = min(4, len(regions))
    n_rows = int(np.ceil(len(regions) / n_cols))
    fig = make_subplots(rows=n_rows, cols=n_cols, subplot_titles=regions)
    return fig, n_rows, n_cols


def _add(fig, x, y, name, color, dash, row, col, show_legend):
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines",
            name=name,
            legendgroup=name,
            showlegend=show_legend,
            line=dict(color=color, dash=dash, width=2),
        ),
        row=row,
        col=col,
    )


def plot_regional(
    h12: pd.DataFrame,
    iso: pd.DataFrame,
    regions: list[str],
    y_col: str,
    x_col: str,
    title: str,
    x_label: str,
    y_label: str,
    log_x: bool,
    last_hist_year: int,
    out: pathlib.Path,
    slug: str,
    show: bool,
):
    fig, n_rows, n_cols = _subplot_grid(regions)
    for i, region in enumerate(regions):
        row, col = i // n_cols + 1, i % n_cols + 1
        first = i == 0
        for src, color, dash, name in (
            (h12, COLOR_H12, "solid", "H12"),
            (iso, COLOR_ISO, "dash", "iso249→H12"),
        ):
            sub = src[src["region"] == region].sort_values(x_col)
            _add(fig, sub[x_col], sub[y_col], name, color, dash, row, col, first)
        if not log_x:
            fig.add_vline(x=last_hist_year, line_width=1, line_dash="dot", line_color="grey",
                          row=row, col=col)
    if log_x:
        fig.update_xaxes(type="log")
    fig.update_xaxes(title_text=x_label)
    fig.update_yaxes(title_text=y_label)
    fig.update_layout(
        title_text=f"<b>{title}</b>  ·  solid = H12, dashed = iso249 aggregated to H12",
        height=max(500, 300 * n_rows),
        hovermode="x unified" if not log_x else "closest",
    )
    for ann in fig.layout.annotations:
        ann.font.size = 12
    _save(fig, out, slug, show)


def _save(fig, out: pathlib.Path, slug: str, show: bool):
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{slug}.html"
    fig.write_html(path)
    print(f"  wrote {path.relative_to(REPO) if path.is_relative_to(REPO) else path}")
    if show:
        fig.show()


# ── numeric summary ───────────────────────────────────────────────────────────────


def summary_table(h12: pd.DataFrame, iso: pd.DataFrame, out: pathlib.Path):
    """Relative difference (iso-agg vs H12) for key metrics at SUMMARY_YEARS."""
    metrics = ["stock", "inflow", "production", "stock_pc", "gdppc"]
    merged = h12.merge(iso, on=["year", "region"], suffixes=("_h12", "_iso"))
    rows = []
    for _, r in merged[merged["year"].isin(SUMMARY_YEARS)].iterrows():
        for metric in metrics:
            a, b = r[f"{metric}_h12"], r[f"{metric}_iso"]
            rel = (b - a) / a * 100.0 if a else np.nan
            rows.append(
                {
                    "year": int(r["year"]),
                    "region": r["region"],
                    "metric": metric,
                    "h12": a,
                    "iso_agg": b,
                    "rel_diff_%": rel,
                }
            )
    table = pd.DataFrame(rows)
    out.mkdir(parents=True, exist_ok=True)
    csv = out / "summary_reldiff.csv"
    table.to_csv(csv, index=False)
    print(f"  wrote {csv.relative_to(REPO) if csv.is_relative_to(REPO) else csv}")

    glob = table[table["region"] == "GLOBAL"].pivot_table(
        index="metric", columns="year", values="rel_diff_%"
    )
    print("\nGlobal iso249->H12 vs H12 relative difference [%]:")
    print(glob.round(2).to_string())
    worst = (
        table[table["region"] != "GLOBAL"]
        .assign(abs_diff=lambda d: d["rel_diff_%"].abs())
        .sort_values("abs_diff", ascending=False)
        .head(10)
    )
    print("\nLargest regional discrepancies:")
    print(
        worst[["year", "region", "metric", "rel_diff_%"]]
        .round(2)
        .to_string(index=False)
    )
    return table


# ── main ─────────────────────────────────────────────────────────────────────────


def parse_args():
    p = argparse.ArgumentParser(description="Compare H12 vs aggregated iso249 plastics runs.")
    p.add_argument("h12", nargs="?", type=pathlib.Path, default=DEFAULT_H12)
    p.add_argument("iso", nargs="?", type=pathlib.Path, default=DEFAULT_ISO)
    p.add_argument("--mapping", type=pathlib.Path, default=DEFAULT_MAPPING)
    p.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    p.add_argument("--show", action="store_true", help="Open figures in the browser too")
    return p.parse_args()


def main():
    args = parse_args()

    print("Loading runs …")
    mfa_h12 = load_mfa(args.h12)
    mfa_iso = load_mfa(args.iso)

    regions_h12 = list(mfa_h12.dims["r"].items)
    last_hist_year = int(mfa_h12.dims["h"].items[-1])

    print("Reading region mapping …")
    mapping = read_region_mapping(args.mapping)

    print("Extracting & aggregating …")
    df_h12 = extract_extensive(mfa_h12)
    df_iso = aggregate_to_h12(extract_extensive(mfa_iso), mapping)

    # sanity: iso-aggregated regions should match the H12 region set
    missing = set(regions_h12) - set(df_iso["region"])
    if missing:
        print(f"  WARNING: H12 regions absent after aggregation: {sorted(missing)}")

    # append GLOBAL (sum of extensive totals) BEFORE deriving intensives, so the
    # global per-capita values are totals/totals rather than a mean of regions.
    df_h12 = add_intensive(add_global(df_h12))
    df_iso = add_intensive(add_global(df_iso))
    panel_regions = regions_h12 + ["GLOBAL"]

    print("Plotting …")
    # 1) stock per capita over GDP per capita
    plot_regional(
        df_h12, df_iso, panel_regions,
        y_col="stock_pc", x_col="gdppc",
        title="In-use stock per capita over GDP per capita",
        x_label="GDP per capita [USD]", y_label="In-use stock per capita [t]",
        log_x=True, last_hist_year=last_hist_year,
        out=args.out, slug="stock_pc_over_gdp_pc", show=args.show,
    )
    # 2) stock inflow (demand)
    plot_regional(
        df_h12, df_iso, panel_regions,
        y_col="inflow", x_col="year",
        title="Stock inflow (demand)",
        x_label="Year", y_label="Inflow [t]",
        log_x=False, last_hist_year=last_hist_year,
        out=args.out, slug="stock_inflow", show=args.show,
    )
    # 3) primary production
    plot_regional(
        df_h12, df_iso, panel_regions,
        y_col="production", x_col="year",
        title=f"Primary production ({PRODUCTION_FLOW})",
        x_label="Year", y_label="Production [t]",
        log_x=False, last_hist_year=last_hist_year,
        out=args.out, slug="production", show=args.show,
    )

    print("\nSummary …")
    summary_table(df_h12, df_iso, args.out)
    print(f"\nDone. Outputs in {args.out}")


if __name__ == "__main__":
    main()
