import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Polymer split of ATLAS plastics trade

    ATLAS models primary plastics as a single good. Its bilateral trade gives, per year, the total
    imports and exports of each region, summed over all polymers. The MFA needs this trade per
    polymer. For each flow, think of a region × polymer matrix: ATLAS fixes its row sums (the
    region totals), but not its column sums (the global trade of each polymer). These only have to
    be the same for imports and exports, so that the trade of each polymer clears globally, and add
    up to the global ATLAS total.

    The coupling (`atlas.py copy-trade`) fills the matrices in two steps:

    1. **Before RAS**: each region total is split with the polymer shares of that region in the
       latest historic year. The region totals match ATLAS, but importing and exporting regions
       trade different polymer mixes, so global imports and exports of a polymer differ.
    2. **After RAS**: imports and exports are adjusted together by a RAS (iterative proportional
       fitting). Each iteration sets the global imports and exports of each polymer to their
       geometric mean and then rescales every region back to its ATLAS total. The result keeps the
       ATLAS region totals, clears the trade of each polymer, and stays as close as possible to
       the historic shares.

    Without the RAS, the MFA would rescale each polymer globally, which clears trade but moves the
    region totals away from ATLAS.
    """)
    return


@app.cell
def _(mo):
    mo.md("This notebook is completely AI generated, with very little human checking!").callout(
        kind="danger", title="AI Disclaimer"
    )
    return


@app.cell
def _():
    from pathlib import Path

    import marimo as mo
    import numpy as np
    import pandas as pd
    import plotly.express as px

    from remind_mfa.atlas_coupling import (
        PROJECT_ROOT,
        AtlasScenarioPkBudg,
        AtlasVariant,
        aggregate_bilateral_trade,
        balance_polymer_trade,
        default_atlas_trade_source,
        load_atlas_trade_projection,
        split_plastics_trade,
    )
    from remind_mfa.common.helpers import ModelNames

    return (
        AtlasScenarioPkBudg,
        AtlasVariant,
        ModelNames,
        PROJECT_ROOT,
        Path,
        aggregate_bilateral_trade,
        balance_polymer_trade,
        default_atlas_trade_source,
        load_atlas_trade_projection,
        mo,
        np,
        pd,
        px,
        split_plastics_trade,
    )


@app.cell
def _(AtlasVariant, ModelNames, default_atlas_trade_source, mo):
    default_source = mo.cli_args().get("source") or default_atlas_trade_source(
        ModelNames.PLASTICS, AtlasVariant.GREEN_GREY
    )
    source_input = mo.ui.text(
        value=str(default_source), label="ATLAS trade projection", full_width=True
    )
    source_input
    return (source_input,)


@app.cell
def _(
    AtlasScenarioPkBudg,
    ModelNames,
    PROJECT_ROOT,
    Path,
    aggregate_bilateral_trade,
    load_atlas_trade_projection,
    mo,
    source_input,
):
    source = Path(source_input.value)
    mo.stop(
        not source.is_file(),
        mo.md(
            f"ATLAS trade projection not found: `{source}`. Run "
            "`uv run atlas.py future --model plastics` first or enter the path of another result."
        ).callout(kind="warn"),
    )

    bilateral = load_atlas_trade_projection(
        ModelNames.PLASTICS,
        source,
        # Ignored for plastics, which has a single ATLAS future scenario.
        AtlasScenarioPkBudg.BUDG_1000,
        PROJECT_ROOT / "data_in" / "parameters" / "regionmapping.csv",
    )
    atlas_imports, atlas_exports = aggregate_bilateral_trade(bilateral)
    return atlas_exports, atlas_imports


@app.cell
def _(atlas_exports, atlas_imports, balance_polymer_trade, pd, split_plastics_trade):
    before = split_plastics_trade(atlas_imports, atlas_exports)
    after = balance_polymer_trade(*before)

    trade = pd.concat(
        [
            frame.assign(flow=flow, stage=stage)
            for stage, frames in (("Before RAS", before), ("After RAS", after))
            for flow, frame in zip(("Imports", "Exports"), frames)
        ],
        ignore_index=True,
    )
    atlas_totals = pd.concat(
        [atlas_imports.assign(flow="Imports"), atlas_exports.assign(flow="Exports")]
    ).set_index(["flow", "year", "region"])["quantity"]
    years = sorted(trade["year"].unique())
    regions = sorted(trade["region"].unique())
    STAGE_DASHES = {"Before RAS": "dash", "After RAS": "solid"}
    return STAGE_DASHES, atlas_totals, regions, trade, years


@app.cell
def _(atlas_totals, mo, trade, years):
    mo.md(f"""
    Loaded ATLAS trade for {years[0]}-{years[-1]} and {trade["region"].nunique()} regions,
    {atlas_totals.groupby("year").sum().mean() / 1e6 / 2:.1f} Mt per year on average
    (imports and exports each), split into {trade["material"].nunique()} polymers.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Checks

    - **Region totals**: largest relative deviation of the polymer sum of a region from its
      ATLAS imports or exports.
    - **Polymer balance**: largest difference between global imports and global exports of a
      polymer, relative to the larger of the two.
    """)
    return


@app.cell
def _(atlas_totals, np, pd, trade):
    region_totals = trade.groupby(["stage", "flow", "year", "region"])["quantity"].sum()
    region_deviation = (region_totals - atlas_totals).abs() / atlas_totals.replace(0, np.nan)

    global_trade = (
        trade.groupby(["stage", "year", "material", "flow"])["quantity"].sum().unstack("flow")
    )
    global_trade["imbalance_pct"] = (
        100
        * (global_trade["Imports"] - global_trade["Exports"])
        / global_trade[["Imports", "Exports"]].max(axis=1)
    )

    checks = pd.DataFrame(
        {
            "Max region total deviation (%)": 100 * region_deviation.groupby("stage").max(),
            "Max polymer imbalance (%)": global_trade["imbalance_pct"].abs().groupby("stage").max(),
        }
    ).loc[["Before RAS", "After RAS"]]
    return checks, global_trade


@app.cell
def _(checks, mo):
    mo.ui.table(checks.map(lambda value: f"{value:.2g}").reset_index(), label="Checks")
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Global trade per polymer

    Before the RAS, global imports and exports of a polymer differ. Afterwards they coincide.
    """)
    return


@app.cell
def _(STAGE_DASHES, global_trade, px):
    global_trade_long = (
        global_trade[["Imports", "Exports"]]
        .stack()
        .rename("quantity")
        .reset_index()
        .assign(quantity=lambda df: df["quantity"] / 1e6)
    )
    px.line(
        global_trade_long,
        x="year",
        y="quantity",
        color="flow",
        line_dash="stage",
        line_dash_map=STAGE_DASHES,
        facet_col="material",
        facet_col_wrap=5,
        labels={"quantity": "Global trade (Mt)"},
        title="Global imports and exports per polymer",
        height=600,
    ).update_yaxes(matches=None, showticklabels=True).for_each_annotation(
        lambda annotation: annotation.update(text=annotation.text.split("=")[-1])
    )
    return


@app.cell
def _(global_trade, px):
    px.line(
        global_trade.loc["Before RAS"].reset_index(),
        x="year",
        y="imbalance_pct",
        color="material",
        labels={"imbalance_pct": "(Imports - exports) / max (%)"},
        title="Global imbalance per polymer before the RAS",
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Polymer shares per region

    Before the RAS, each region keeps its latest historic shares in every future year (dashed). The
    RAS shifts them (solid) as far as needed to clear the trade of each polymer.
    """)
    return


@app.cell
def _(mo, regions):
    region_picker = mo.ui.dropdown(options=regions, value=regions[0], label="Region")
    flow_picker = mo.ui.radio(
        options=["Imports", "Exports"], value="Imports", label="Flow", inline=True
    )
    mo.hstack([region_picker, flow_picker], justify="start", gap=2)
    return flow_picker, region_picker


@app.cell
def _(trade):
    shares = trade.assign(
        share=lambda df: 100
        * df["quantity"]
        / df.groupby(["stage", "flow", "year", "region"])["quantity"].transform("sum")
    )
    return (shares,)


@app.cell
def _(STAGE_DASHES, flow_picker, px, region_picker, shares):
    px.line(
        shares.loc[
            (shares["region"] == region_picker.value) & (shares["flow"] == flow_picker.value)
        ],
        x="year",
        y="share",
        color="material",
        line_dash="stage",
        line_dash_map=STAGE_DASHES,
        labels={"share": "Share of regional trade (%)"},
        title=f"{flow_picker.value} polymer shares, {region_picker.value}",
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Changes by region and polymer

    Change of the polymer shares by the RAS (after minus before), in percentage points.
    """)
    return


@app.cell
def _(mo, years):
    year_picker = mo.ui.slider(
        start=years[0], stop=years[-1], value=years[-1], label="Year", show_value=True
    )
    year_picker
    return (year_picker,)


@app.cell
def _(mo, px, shares, year_picker):
    share_change = (
        shares.loc[shares["year"] == year_picker.value]
        .pivot_table(index=["flow", "region", "material"], columns="stage", values="share")
        .pipe(lambda df: df["After RAS"] - df["Before RAS"])
    )
    color_range = max(share_change.abs().max(), 1e-9)
    mo.hstack(
        [
            px.imshow(
                share_change.loc[flow].unstack("material"),
                color_continuous_scale="RdBu",
                zmin=-color_range,
                zmax=color_range,
                text_auto=".1f",
                aspect="auto",
                labels={"color": "pp"},
                title=f"{flow}, {year_picker.value}",
            )
            for flow in ("Imports", "Exports")
        ]
    )
    return


if __name__ == "__main__":
    app.run()
