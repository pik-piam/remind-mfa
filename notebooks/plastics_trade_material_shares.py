import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(r"""
    # Material shares in historic primary plastics trade

    The parameters `pl_primary_his_exports.cs4r` and `pl_primary_his_imports.cs4r` resolve
    historic primary plastics trade (1950-2024) by region and polymer. This notebook computes,
    for every year, the share each material contributes to total trade and checks whether those
    shares are constant enough that a time-independent split could be used for future projections.
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
    import pandas as pd
    import plotly.express as px

    return Path, mo, pd, px


@app.cell
def _(Path, pd):
    repo_root = Path.cwd().parent
    if not (repo_root / "pyproject.toml").exists():
        raise FileNotFoundError(
            "Run this notebook from the `notebooks` directory of the repository."
        )

    def read_trade_cs4r(flow: str) -> pd.DataFrame:
        """Read a historic primary plastics trade parameter file.

        Args:
            flow: Either `"exports"` or `"imports"`.

        Returns:
            Long-format frame with columns `Time`, `Region`, `Type`, `Material`, `value`
            and an added `Flow` column, values in t plastic.
        """
        path = repo_root / "data_in" / "parameters" / f"pl_primary_his_{flow}.cs4r"
        trade = pd.read_csv(
            path,
            comment="*",
            header=None,
            names=["Time", "Region", "Type", "Material", "value"],
        )
        trade["Flow"] = flow.capitalize()
        return trade

    trade_long = pd.concat(
        [read_trade_cs4r("exports"), read_trade_cs4r("imports")], ignore_index=True
    )
    materials = sorted(trade_long["Material"].unique())
    regions = sorted(trade_long["Region"].unique())
    return regions, trade_long


@app.cell
def _(mo, trade_long):
    mo.md(f"""
    Loaded {len(trade_long):,} rows covering
    {trade_long["Time"].min()}-{trade_long["Time"].max()},
    {trade_long["Region"].nunique()} regions and
    {trade_long["Material"].nunique()} materials.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Global shares per year
    """)
    return


@app.cell
def _(pd, trade_long):
    def material_shares(trade: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
        """Compute the share of each material within each group.

        Args:
            trade: Long-format trade frame with a `Material` and a `value` column.
            group_columns: Columns whose combinations the shares should sum to one over.

        Returns:
            Wide frame indexed by `group_columns` with one column per material.
        """
        totals = trade.pivot_table(
            index=group_columns, columns="Material", values="value", aggfunc="sum"
        )
        return totals.div(totals.sum(axis=1), axis=0)

    global_shares = material_shares(trade_long, ["Flow", "Time"])
    return global_shares, material_shares


@app.cell
def _(global_shares, mo):
    mo.ui.table(
        (100 * global_shares).round(2).reset_index(),
        label="Global material shares per year (%)",
    )
    return


@app.cell
def _(global_shares, px):
    global_shares_long = (
        global_shares.stack()
        .rename("share")
        .reset_index()
        .assign(share=lambda df: 100 * df["share"])
    )
    px.area(
        global_shares_long,
        x="Time",
        y="share",
        color="Material",
        facet_col="Flow",
        labels={"share": "Share of total trade (%)"},
        title="Global material shares in primary plastics trade",
    )
    return (global_shares_long,)


@app.cell
def _(global_shares_long, px):
    px.line(
        global_shares_long,
        x="Time",
        y="share",
        color="Material",
        facet_col="Flow",
        labels={"share": "Share of total trade (%)"},
        title="Global material shares, per material",
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## How constant are the shares?

    Two measures per material, computed over 1950-2024:

    - **range**: `max - min` of the yearly share, in percentage points.
    - **relative range**: that range divided by the mean share; a value of 0.5 means the share
      swings by half of its own average size.
    """)
    return


@app.cell
def _(global_shares, pd):
    def stability(shares: pd.DataFrame) -> pd.DataFrame:
        """Summarise how much each material share varies over time.

        Args:
            shares: Wide frame indexed by year with one share column per material.

        Returns:
            Frame indexed by material with mean, min, max, range (percentage points),
            standard deviation (percentage points) and the range relative to the mean.
        """
        summary = pd.DataFrame(
            {
                "mean_pct": 100 * shares.mean(),
                "min_pct": 100 * shares.min(),
                "max_pct": 100 * shares.max(),
                "std_pp": 100 * shares.std(),
            }
        )
        summary["range_pp"] = summary["max_pct"] - summary["min_pct"]
        summary["relative_range"] = summary["range_pp"] / summary["mean_pct"]
        return summary.sort_values("range_pp", ascending=False)

    global_stability = pd.concat(
        {flow: stability(group.droplevel("Flow")) for flow, group in global_shares.groupby("Flow")},
        names=["Flow", "Material"],
    )
    return global_stability, stability


@app.cell
def _(global_stability, mo):
    mo.ui.table(
        global_stability.round(3).reset_index(), label="Stability of global material shares"
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Three distinct eras

    The underlying BACI data only starts in the mid-1990s; earlier years are backfilled. Splitting
    the period shows that the apparent stability of the full series is an artefact of that
    backfilling, so the eras have to be looked at separately.
    """)
    return


@app.cell
def _(global_shares, pd, stability):
    ERAS = {
        "1950-1989 (backfilled)": (1950, 1989),
        "1990-1994": (1990, 1994),
        "1995-2024 (BACI)": (1995, 2024),
    }

    era_stability = pd.concat(
        {
            (flow, era): stability(group.droplevel("Flow").loc[start:end])
            for era, (start, end) in ERAS.items()
            for flow, group in global_shares.groupby("Flow")
        },
        names=["Flow", "Era", "Material"],
    )
    return ERAS, era_stability


@app.cell
def _(era_stability, mo):
    mo.ui.table(
        era_stability["range_pp"].unstack("Era").round(2).reset_index(),
        label="Range of global material shares per era (percentage points)",
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Regional shares

    Global shares can hide regional structure: a region exporting mostly PVC and one exporting
    mostly PP average out. The chart below shows the shares for a single region.
    """)
    return


@app.cell
def _(mo, regions):
    region_picker = mo.ui.dropdown(options=regions, value="EUR", label="Region")
    flow_picker = mo.ui.radio(
        options=["Exports", "Imports"], value="Exports", label="Flow", inline=True
    )
    mo.hstack([region_picker, flow_picker], justify="start", gap=2)
    return flow_picker, region_picker


@app.cell
def _(material_shares, trade_long):
    regional_shares = material_shares(trade_long, ["Flow", "Region", "Time"])
    return (regional_shares,)


@app.cell
def _(flow_picker, px, region_picker, regional_shares):
    selected_shares = (
        regional_shares.xs((flow_picker.value, region_picker.value), level=("Flow", "Region"))
        .stack()
        .rename("share")
        .reset_index()
        .assign(share=lambda df: 100 * df["share"])
    )
    px.area(
        selected_shares,
        x="Time",
        y="share",
        color="Material",
        labels={"share": "Share of regional trade (%)"},
        title=f"{flow_picker.value} material shares, {region_picker.value}",
    )
    return


@app.cell
def _(ERAS, mo, pd, regional_shares):
    within_region_range = pd.concat(
        {
            (flow, era): pd.Series(
                {
                    region: 100
                    * (
                        group.loc[(flow, region, start):(flow, region, end)].max()
                        - group.loc[(flow, region, start):(flow, region, end)].min()
                    ).max()
                    for region in group.index.get_level_values("Region").unique()
                },
                name="max_range_pp",
            )
            for era, (start, end) in ERAS.items()
            for flow, group in regional_shares.groupby("Flow")
        },
        names=["Flow", "Era", "Region"],
    )
    mo.ui.table(
        within_region_range.unstack("Era").round(2).reset_index(),
        label="Largest share swing of any material within a region, per era (percentage points)",
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Answer: the shares are *not* constant

    - **1950-1989 the shares are constant by construction.** Every material share moves by at most
      ~2.5 pp over four decades, and for most region/material pairs not at all. These years are
      backfilled from the first data year by scaling a fixed split, so their stability says nothing
      about reality.
    - **From 1995 onwards, where BACI data exists, the shares move substantially.** Globally, PS
      falls from ~12% to ~5%, "Other thermoplastics" rises from ~13% to ~19%, PET more than doubles
      from ~3.6% to ~8.7%, and LDPE drops from ~15.6% to ~9.6%. These are directed multi-decade
      trends, not noise around a mean.
    - **Regionally the drift is much larger.** Between 1995 and 2024 every region has at least one
      material whose share swings by ~8 pp or more; the median across regions is ~22 pp for exports
      and ~18 pp for imports, and SSA and IND exports swing by ~46 pp and ~45 pp. Regional mixes
      diverge rather than cancel, so a region-specific constant split is an even worse approximation
      than a global one.
    - **Exports and imports share the same global split.** From 1995 onwards the global export and
      import shares are identical to numerical precision (global exports must mirror global imports
      per material); they differ only by <1 pp in the backfilled years. The two files therefore do
      not carry independent information about the material mix at the global level, only about its
      regional distribution.

    **Conclusion:** a time-constant material split is defensible only for the pre-1990 period, where
    it is already what the data contains. For 1995-2024 the mix shifts steadily - away from PS, LDPE
    and PVC and towards PET, HDPE and other thermoplastics - so the time dimension of these
    parameters has to be kept.
    """)
    return


if __name__ == "__main__":
    app.run()
