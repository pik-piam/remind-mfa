import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md("""
    # Worldsteel vs. BIR steel scrap data

    Compares steel scrap statistics from the two sources used by `mrmfa`:

    - **BIR** (Bureau of International Recycling, *World Steel Recycling in Figures*):
      scrap consumption by region 1998-2025 (Mt) and scrap share in crude steel
      production 2005-2023 (%). Read by `readBIR.R`.
    - **Worldsteel**: scrap consumption digitised from the Steel Statistical Yearbooks
      (`readWorldSteelDigitised.R`, per-country 1975-2008, global 1975-2008) and crude
      steel / EAF production from the online database (`readWorldSteelDatabase.R`,
      2002-2022).

    Data are read directly from the madrat source folder, applying the same unit
    conversions as the `mrmfa` read functions. Region aggregates are taken from the
    aggregate rows of the yearbook tables (which `toolCleanSteelRegions` drops), so the
    comparison is at BIR's regional resolution.
    """)
    return


@app.cell
def _():
    import os
    import re
    from pathlib import Path

    import marimo as mo
    import numpy as np
    import pandas as pd
    import plotly.express as px
    from dotenv import load_dotenv

    return Path, load_dotenv, mo, np, os, pd, px


@app.cell
def _(Path, load_dotenv, os):
    repo_root = next(
        (p for p in [Path.cwd(), *Path.cwd().parents] if (p / "pyproject.toml").exists()),
        Path.cwd(),
    )

    load_dotenv(repo_root / ".env")
    madrat_main_folder = Path(os.environ.get("MADRAT_MAINFOLDER", repo_root.parent / ".madrat"))
    sources_dir = madrat_main_folder / "sources"
    if not sources_dir.exists():
        raise FileNotFoundError(
            f"madrat source folder {sources_dir} does not exist. Set MADRAT_MAINFOLDER."
        )

    bir_dir = sources_dir / "BIR" / "v1.0"
    ws_digitised_dir = sources_dir / "WorldSteelDigitised" / "v1.0"
    ws_database_dir = sources_dir / "WorldSteelDatabase" / "v1.0"
    return bir_dir, ws_database_dir, ws_digitised_dir


@app.cell
def _(mo):
    mo.md("""
    ## BIR data
    """)
    return


@app.cell
def _(bir_dir, mo, pd):
    # BIR scrap consumption, unit Mt (see readBIR.R subtype "scrapConsumption")
    bir_consumption = (
        pd.read_excel(
            bir_dir / "BIR_ScrapConsumption_Ammended.xlsx",
            sheet_name="Data",
            skiprows=1,
        )
        .melt(id_vars="region", var_name="year", value_name="value")
        .astype({"year": int})
        .dropna(subset="value")
        .assign(source="BIR")
    )
    mo.ui.table(bir_consumption, label="BIR scrap consumption [Mt]")
    return (bir_consumption,)


@app.cell
def _(bir_dir, pd):
    # BIR scrap share in crude steel production.
    bir_share = (
        pd.read_excel(bir_dir / "BIR_ScrapShareProduction.xlsx", sheet_name="Data")
        .rename(columns={"Scrap share in production": "region"})
        .melt(id_vars="region", var_name="year", value_name="value")
        .astype({"year": int})
        .dropna(subset="value")
        .assign(source="BIR")
    )
    bir_share
    return (bir_share,)


@app.cell
def _(mo):
    mo.callout(
        mo.md(
            "The source sheet mixes percent (e.g. 55.8) and fractions (e.g. 0.562), so values below 1.0 are rescaled to percent."
        ),
        kind="danger",
    )
    return


@app.cell
def _(bir_share):
    bir_share[bir_share["value"] <= 1.0]
    return


@app.cell
def _(bir_share, mo):
    bir_share["value"] = bir_share["value"].where(
        bir_share["value"] > 1.0, bir_share["value"] * 100
    )
    mo.ui.table(bir_share, label="BIR scrap share in production [%]")
    return


@app.cell
def _(mo):
    mo.md("""
    ## Worldsteel yearbook data

    The yearbook tables for 2000-2008 report scrap consumption in Mt per
    country and per aggregate region (the earlier decades (1975-1998) are in kt and are
    not needed here because BIR starts in 2004). The global series 1975-2008 is in kt.
    """)
    return


@app.cell
def _(mo, pd, ws_digitised_dir):
    # Global scrap consumption 1975-2008, unit kt -> Mt
    ws_scrap_global = (
        pd.read_excel(
            ws_digitised_dir / "scrap_consumption" / "global_scrap_consumption_1975-2008.xlsx",
            sheet_name="Data",
        )
        .melt(id_vars="Year", var_name="year", value_name="value")
        .drop(columns="Year")
        .astype({"year": int})
        .dropna(subset="value")
        .assign(region="World", source="Worldsteel", value=lambda df: df["value"] / 1e3)
        .set_index(["region", "year"])
    )
    mo.ui.table(ws_scrap_global, label="Worldsteel World scrap consumption [Mt]")
    return (ws_scrap_global,)


@app.cell
def _(pd, ws_digitised_dir):
    # Per-country / per-region scrap consumption from the yearbooks 2000-2008, unit Mt
    def _read_ws_yearbook(year: int) -> pd.DataFrame:
        df = pd.read_excel(
            ws_digitised_dir / "scrap_consumption" / f"scrap_consumption_{year}.xlsx"
        )
        df = df[["country_name", "Consumption"]].rename(
            columns={"country_name": "region", "Consumption": "value"}
        )
        df["region"] = df["region"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        # unify the varying EU aggregate labels, e.g. "European Union ( 15 )"
        # df["region"] = df["region"].str.replace(
        #    r"^European Union.*$", "European Union", regex=True
        # )
        df["year"] = year
        return df.dropna(subset="value")

    ws_scrap_yearbook = pd.concat(
        [_read_ws_yearbook(y) for y in range(2000, 2009)], ignore_index=True
    ).assign(source="Worldsteel Yearbook")
    ws_scrap_yearbook
    return (ws_scrap_yearbook,)


@app.cell
def _(mo, ws_scrap_yearbook):
    eu_labels = ws_scrap_yearbook.loc[
        ws_scrap_yearbook["region"].str.contains(r"^European Union.*$", regex=True),
        "region",
    ].unique()
    mo.md(
        f"Note: EU aggregate labels found in the yearbooks: `{eu_labels}` (membership differs by year)."
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Worldsteel database
    """)
    return


@app.cell
def _(mo, pd, ws_database_dir):
    def read_ws_database(filename: str) -> pd.DataFrame:
        """Read a Worldsteel database export (kt) into a long frame in Mt.

        Mirrors readWorldSteelDatabase.R: skip the two header rows and drop the five
        trailing copyright/retrieval rows.
        """
        df = pd.read_excel(ws_database_dir / filename, skiprows=2).iloc[:-5]
        return (
            df.rename(columns={"Country": "region"})
            .melt(id_vars="region", var_name="year", value_name="value")
            .astype({"year": int})
            .dropna(subset="value")
            .assign(value=lambda d: d["value"] / 1e3)
            .set_index(["region", "year"])
        )

    ws_crude = read_ws_database("P01_crude_2023-10-23.xlsx")
    ws_crude.query("region == 'World'").sort_values("year").pipe(
        lambda df: mo.ui.table(df, label="Worldsteel World crude steel production [Mt]")
    )
    return read_ws_database, ws_crude


@app.cell
def _(mo, read_ws_database):
    ws_eaf = read_ws_database("P06_eaf_2023-10-23.xlsx")
    mo.ui.table(
        ws_eaf.query("region == 'World'").sort_values("year"),
        label="Worldsteel World EAF crude steel production [Mt]",
    )
    return (ws_eaf,)


@app.cell
def _(mo, read_ws_database):
    ws_bof = read_ws_database("P05_bof_2023-10-23.xlsx")
    mo.ui.table(
        ws_bof.query("region == 'World'").sort_values("year"),
        label="Worldsteel World BOF crude steel production [Mt]",
    )
    return (ws_bof,)


@app.cell
def _(mo, read_ws_database):
    ws_otherproc = read_ws_database("P07_otherproc_2023-10-23.xlsx")
    mo.ui.table(
        ws_otherproc.query("region == 'World'").sort_values("year"),
        label="Worldsteel World other process crude steel production [Mt]",
    )
    return (ws_otherproc,)


@app.cell
def _(pd, px, ws_bof, ws_crude, ws_eaf, ws_otherproc):
    # Worldsteel steel production consistency check: total production vs sum of EAF, BOF and other processes.
    ws_by_type = pd.concat(
        [
            ws_eaf.assign(type="EAF"),
            ws_bof.assign(type="BOF"),
            ws_otherproc.assign(type="Other process"),
        ],
    )
    ws_by_type = ws_by_type.groupby(["region", "year"]).agg(total_by_type=("value", "sum"))
    ws_by_type_comparison = ws_crude.join(
        ws_by_type,
        how="outer",
    )
    ws_by_type_comparison_world = ws_by_type_comparison.query("region == 'World'")
    px.line(
        ws_by_type_comparison_world,
        x=ws_by_type_comparison_world.index.get_level_values("year"),
        y=["value", "total_by_type"],
        markers=True,
        title="Worldsteel World crude steel production by process type [Mt]",
    ).show()
    return (ws_by_type_comparison,)


@app.cell
def _(px, ws_by_type_comparison):
    ws_by_type_gap = ws_by_type_comparison.assign(
        gap=lambda df: df["value"] - df["total_by_type"],
        gap_percent=lambda df: (
            abs((df["value"] - df["total_by_type"])) / df["value"].where(df["value"] != 0) * 100
        ),
    ).where(lambda df: df["gap_percent"] > 0.05)
    px.histogram(
        ws_by_type_gap,
        x="gap_percent",
        color=ws_by_type_gap.index.get_level_values("region"),
        hover_data=[
            ws_by_type_gap.index.get_level_values("region"),
            "value",
            "total_by_type",
        ],
        labels="region",
        title="Worldsteel World crude steel production gap by process type [%]",
    ).show()
    return (ws_by_type_gap,)


@app.cell
def _(mo, ws_by_type_gap):
    ws_by_type_gap.sort_values("gap_percent", ascending=False).pipe(
        lambda df: mo.ui.table(
            df, label="Worldsteel World crude steel production gap by process type [%]"
        )
    )
    return


@app.cell
def _(mo, read_ws_database):
    ws_pigiron_import = read_ws_database("T12_imports_pigiron-2023-10-23.xlsx").rename(
        columns={"value": "pigiron_import"}
    )
    ws_pigiron_export = read_ws_database("T11_exports_pigiron-2023-10-23.xlsx").rename(
        columns={"value": "pigiron_export"}
    )
    ws_pigiron_trade = (
        ws_pigiron_import.merge(
            ws_pigiron_export,
            on=["region", "year"],
            how="outer",
        )
        .assign(pigiron_trade_net=lambda df: df["pigiron_import"] - df["pigiron_export"])
        .sort_values(["region", "year"])
    )
    mo.ui.table(
        ws_pigiron_trade.query("region == 'World'").sort_values("year")[
            ["pigiron_import", "pigiron_export", "pigiron_trade_net"]
        ],
        label="Worldsteel World pig iron trade [Mt]",
    )
    return (ws_pigiron_trade,)


@app.cell
def _(mo, ws_pigiron_trade):
    # According to Metalloinvest p.157: Outside of China and India, the largest sources of steelmaking demand for merchant pig iron are in the U.S.,
    # Japan, Brazil, Italy and South Korea. The U.S. has led the way in terms of EAF-based flat rolled steel. In Europe,
    # there is a single producer each in Italy and Spain, though the latter is not currently operating at full capacity
    # The following table shows that this is indeed the case except:
    # - India and Brazil have a low pig iron import in Worldsteel data, but are exporters
    # - Türkiye, Taiwan, Germany and Thailand also have a sizable pig iron import in Worldsteel data
    ws_pigiron_trade_totals = (
        ws_pigiron_trade.groupby("region")
        .agg(
            pigiron_import_total=("pigiron_import", "sum"),
            pigiron_export_total=("pigiron_export", "sum"),
            pigiron_trade_net_total=("pigiron_trade_net", "sum"),
        )
        .sort_values("pigiron_import_total", ascending=False)
    )
    mo.ui.table(ws_pigiron_trade_totals, label="Worldsteel World pig iron trade totals [Mt]")
    return (ws_pigiron_trade_totals,)


@app.cell
def _(px, ws_pigiron_trade, ws_pigiron_trade_totals):
    # According to Metalloinvest p.157: demand for merchant pig iron has declined over recent years in most of the major markets
    # That doesn't seem to be really the case in Worldsteel data - seems to be rather constant
    top_regions = ws_pigiron_trade_totals.query("pigiron_import_total > 0").head(10).index.tolist()
    trade_top_regions = ws_pigiron_trade.query("region in @top_regions & region != 'World'")
    px.line(
        trade_top_regions,
        x=trade_top_regions.index.get_level_values("year"),
        color=trade_top_regions.index.get_level_values("region"),
        y="pigiron_import",
        markers=True,
        title="Worldsteel pig iron trade in major markets [Mt]",
    ).show()
    return


@app.cell
def _(mo, read_ws_database, ws_pigiron_trade):
    ws_pigiron = read_ws_database("P26_pigiron_2023-10-23.xlsx").rename(
        columns={"value": "pigiron"}
    )
    ws_dri = read_ws_database("P27_driron_2023-10-23.xlsx").rename(columns={"value": "dri"})
    ws_iron = ws_pigiron.join([ws_pigiron_trade, ws_dri], how="outer").assign(
        total_iron=lambda df: df["pigiron"] + df["dri"],
        pigiron_after_export=lambda df: df["pigiron"] - df["pigiron_export"],
        pigiron_after_import=lambda df: df["pigiron"] + df["pigiron_import"],
    )
    mo.ui.table(ws_iron.query("region != 'World'"), label="Worldsteel World iron production [Mt]")
    return (ws_iron,)


@app.cell
def _(ws_bof, ws_eaf, ws_iron):
    # According to JRC69967 Table 7.3, in 1t of BOF crude steel products (after casting and other losses), 788 – 931kg of pig iron is used, so let's take the average of 860kg
    # According to Metalloinvest p.156, merchandised pig iron is either used in EAF steelmaking (flat-rolled) or for foundries producing grey or ductile iron castings.
    # so we don't expect traded pig iron to be used in BOF steelmaking.
    ws_bof_consistency = (
        ws_iron.join(
            [
                ws_bof.rename(columns={"value": "bof"}),
                ws_eaf.rename(columns={"value": "eaf"}),
            ],
            how="outer",
        )
        .assign(
            bof_share=lambda df: (
                df["bof"] / (df["bof"] + df["eaf"]).where((df["bof"] + df["eaf"]) != 0)
            ),
            eaf_share=lambda df: (
                df["eaf"] / (df["bof"] + df["eaf"]).where((df["bof"] + df["eaf"]) != 0)
            ),
            pigiron_bof_rate_raw=lambda df: df["pigiron"] / df["bof"].where(df["bof"] != 0),
            pigiron_bof_rate=lambda df: (
                df["pigiron_after_export"] / df["bof"].where(df["bof"] != 0)
            ),
            bof_gap_raw=lambda df: df["pigiron"] - 0.86 * df["bof"],
            bof_gap=lambda df: df["pigiron_after_export"] - 0.86 * df["bof"],
            bof_gap_percent=lambda df: ((df["bof_gap"] / df["bof"].where(df["bof"] != 0)) * 100),
        )
        .sort_values(["region", "year"])
        .query("region != 'Others'")
    )
    ws_bof_consistency
    return (ws_bof_consistency,)


@app.cell
def _(px, ws_bof_consistency):
    px.scatter(
        ws_bof_consistency,
        x=ws_bof_consistency.index.get_level_values("year"),
        y="pigiron_bof_rate",
        color=ws_bof_consistency.index.get_level_values("region"),
        hover_data=[
            ws_bof_consistency.index.get_level_values("region"),
            "pigiron",
            "bof",
            "pigiron_after_export",
        ],
        labels="region",
        title="Worldsteel World pig iron share in BOF crude steel production",
    ).show()
    return


@app.cell
def _(mo, ws_bof_consistency):
    region_dropdown = mo.ui.dropdown(
        ws_bof_consistency.index.get_level_values("region").unique().tolist(),
        label="Select region",
        value="World",
    )
    region_dropdown
    return (region_dropdown,)


@app.cell
def _(px, region_dropdown, ws_bof_consistency):
    region = region_dropdown.value
    _data = ws_bof_consistency.query("region == @region")
    px.scatter(
        _data,
        x=_data.index.get_level_values("year"),
        y="pigiron_bof_rate",
        color=_data.index.get_level_values("region"),
        hover_data=[
            _data.index.get_level_values("region"),
            "pigiron",
            "bof",
            "pigiron_after_export",
        ],
        labels="region",
        title=f"Worldsteel pig iron share in BOF crude steel production for region {region}",
    ).show()
    return


@app.cell
def _(px, ws_bof_consistency):
    histo = px.histogram(
        ws_bof_consistency,
        x="pigiron_bof_rate",
        color=ws_bof_consistency.index.get_level_values("region"),
        hover_data=[ws_bof_consistency.index.get_level_values("region"), "pigiron", "bof"],
        labels="region",
        title="Worldsteel pig iron rate in BOF crude steel production",
    )
    histo.add_vrect(
        x0=0.788,
        x1=0.931,
        fillcolor="green",
        opacity=0.2,
        layer="below",
        line_width=0,
        annotation_text="EU JRC 69967",
        annotation_position="top left",
    )
    histo.show()
    return


@app.cell
def _(mo, ws_bof_consistency):
    mo.md(
        f"Worldsteel pig iron rate in BOF crude steel production: \n - reported: {ws_bof_consistency['pigiron_bof_rate'].mean():.2%} ± {ws_bof_consistency['pigiron_bof_rate'].std():.2%} \n - raw: {ws_bof_consistency['pigiron_bof_rate_raw'].mean():.2%} ± {ws_bof_consistency['pigiron_bof_rate_raw'].std():.2%}"
    )
    return


@app.cell
def _(px, ws_bof_consistency):
    _data = ws_bof_consistency.query("region != 'World'")
    px.scatter(
        _data,
        x="eaf_share",
        y="pigiron_bof_rate",
        color=_data.index.get_level_values("region"),
        hover_data=[
            _data.index.get_level_values("region"),
            _data.index.get_level_values("year"),
            "pigiron",
            "bof",
            "pigiron_after_export",
            "pigiron_bof_rate",
            "pigiron_bof_rate_raw",
        ],
        labels="region",
        title="Worldsteel pig iron/bof vs EAF share",
    ).show()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Would have expected that the higher the EAF production is the lower the pig iron rate in BOF crude steel production is, but the correlation is not very strong (-0.25). Reason for my expectation is that some pig iron is used in EAF production, so the more EAF production there is, the less overall pig iron is used in BOF production.
    """)
    return


@app.cell
def _(ws_bof_consistency):
    # calculate correlation between EAF share and pig iron rate in BOF crude steel production
    corr = ws_bof_consistency.corr()
    corr
    return


@app.cell
def _(px, ws_bof_consistency):
    px.scatter(
        ws_bof_consistency,
        x=ws_bof_consistency.index.get_level_values("year"),
        y="bof_gap",
        color=ws_bof_consistency.index.get_level_values("region"),
        hover_data=[ws_bof_consistency.index.get_level_values("region"), "pigiron", "bof"],
        labels="region",
        title="Worldsteel pig iron gap in BOF crude steel production (assuming 86% pig iron content in BOF steel)",
    ).show()
    return


@app.cell
def _(px, ws_bof_consistency):
    px.histogram(
        ws_bof_consistency,
        x="bof_gap_percent",
        color=ws_bof_consistency.index.get_level_values("region"),
        hover_data=[ws_bof_consistency.index.get_level_values("region"), "pigiron", "bof"],
        labels="region",
        title="Worldsteel World pig iron gap in BOF crude steel production",
    ).show()
    return


@app.cell
def _(ws_bof_consistency):
    # For one region:
    ws_bof_consistency_region = ws_bof_consistency.xs("Italy", level="region")
    ws_bof_consistency_region
    return


@app.cell
def _(mo, ws_bof_consistency):
    # According to JRC69967 Table 7.3, in 1t of BOF crude steel products (after casting and other losses ??):
    #    - 788-931kg of pig iron is used (average 860kg)
    #    - 101-340kg of scrap is used (average 220kg)
    # According to JRC69967 Table 8.1, in 1t of EAF liquid steel (after casting and other losses ??):
    #    - 0-153kg of pig iron (average 76.5kg)
    #    - 1039-1232kg of scrap (average 1135.5kg)
    #    - 0-215kg of DRI (average 107.5kg)
    #    By far the main iron source for an EAF is scrap. Hot metal and DRI are used by a rather small number of operators, generally in a rather sporadic fashion. Thus, it is difficult to indicate
    #    representative range.
    # According to https://transitionasia.org/wp-content/uploads/2023/02/TA-Steel-Explainer2023-1.pdf,
    #     - EAFs in China use about 50% pig iron
    # According to https://www.majesticsteel.com/pig-iron/
    #     - EAFs (in the US?) use about 15% pig iron

    ws_iron_demand = ws_bof_consistency.assign(
        pigiron_demand=lambda df: 0.86 * df["bof"] + 0.0765 * df["eaf"],
        scrap_demand=lambda df: 0.22 * df["bof"] + 1.1355 * df["eaf"],
        naive_scrap_demand=lambda df: df["eaf"] - df["dri"],
        dri_demand=lambda df: 0.1075 * df["eaf"],
        pigiron_gap=lambda df: (df["pigiron"] - df["pigiron_demand"] + df["pigiron_trade_net"]),
        pigiron_gap_percent=lambda df: (
            (df["pigiron_gap"] / df["bof"].where(df["bof"] != 0)) * 100
        ),
        # scrap_gap=lambda df: df["scrap"] - df["scrap_demand"],
        # scrap_gap_percent=lambda df: (
        #    (df["scrap_gap"] / df["scrap"].where(df["scrap"] != 0)) * 100
        # ),
        dri_gap=lambda df: df["dri"] - df["dri_demand"],
        dri_gap_percent=lambda df: (df["dri_gap"] / df["dri"].where(df["dri"] != 0)) * 100,
    )
    mo.ui.table(
        ws_iron_demand.query("region == 'World'"),
        label="Worldsteel world iron demand vs production [Mt]",
    )
    return (ws_iron_demand,)


@app.cell
def _(px, ws_iron_demand):
    px.histogram(
        ws_iron_demand,
        x="pigiron_gap_percent",
        color=ws_iron_demand.index.get_level_values("region"),
        hover_data=[ws_iron_demand.index.get_level_values("region"), "pigiron", "bof"],
        labels="region",
        title="Worldsteel World pig iron gap in BOF crude steel production vs demand",
    ).show()
    return


@app.cell
def _(mo, ws_iron_demand):
    # Statistics on the pig iron gap in BOF crude steel production vs demand
    _data = ws_iron_demand["pigiron_gap_percent"]
    mo.md(
        f"Worldsteel pig iron gap in BOF crude steel production vs demand: \n - mean: {_data.mean():.2%} ± {_data.std():.2%} \n - median: {_data.median():.2%} \n - min: {_data.min():.2%} \n - max: {_data.max():.2%}"
    )
    return


@app.cell
def _(px, ws_iron_demand):
    px.histogram(
        ws_iron_demand,
        x="dri_gap_percent",
        color=ws_iron_demand.index.get_level_values("region"),
        hover_data=[ws_iron_demand.index.get_level_values("region"), "dri", "eaf"],
        labels="region",
        title="Worldsteel World DRI gap in EAF crude steel production vs demand",
    ).show()
    return


@app.cell
def _(px, ws_iron_demand):
    px.scatter(
        ws_iron_demand,
        x="scrap_demand",
        y="naive_scrap_demand",
        color=ws_iron_demand.index.get_level_values("region"),
        hover_data=[
            ws_iron_demand.index.get_level_values("region"),
            "scrap_demand",
            "naive_scrap_demand",
        ],
        labels="region",
        title="Worldsteel World scrap demand in EAF crude steel production vs naive demand",
    ).show()
    return


@app.cell
def _(px, ws_iron_demand):
    px.scatter(
        ws_iron_demand,
        x="bof",
        y="pigiron",
        color=ws_iron_demand.index.get_level_values("region"),
        hover_data=[
            ws_iron_demand.index.get_level_values("region"),
            "bof",
            "pigiron",
        ],
        labels="region",
        title="Worldsteel World pig iron vs BOF crude steel production",
    ).show()
    return


@app.cell
def _(px, ws_iron_demand):
    _scatter = px.scatter(
        ws_iron_demand,
        x="bof",
        y="pigiron_after_export",
        color=ws_iron_demand.index.get_level_values("region"),
        hover_data=[
            ws_iron_demand.index.get_level_values("region"),
            ws_iron_demand.index.get_level_values("year"),
            "bof",
            "pigiron",
            "pigiron_after_export",
        ],
        labels="region",
        title="Worldsteel World pig iron vs BOF crude steel production",
    )
    _scatter.add_shape(
        type="line",
        x0=ws_iron_demand["bof"].min(),
        x1=ws_iron_demand["bof"].max(),
        y0=0.86 * ws_iron_demand["bof"].min(),
        y1=0.86 * ws_iron_demand["bof"].max(),
        line={"color": "red", "dash": "dash"},
        name="Expected pig iron demand in BOF crude steel production (0.86 * BOF)",
    )

    _scatter.show()
    return


@app.cell
def _(px, ws_iron_demand):
    px.scatter(
        ws_iron_demand,
        x="eaf",
        y="dri",
        color=ws_iron_demand.index.get_level_values("region"),
        hover_data=[
            ws_iron_demand.index.get_level_values("region"),
            ws_iron_demand.index.get_level_values("year"),
            "eaf",
            "dri",
        ],
        labels="region",
        title="Worldsteel World DRI vs EAF crude steel production",
    ).show()
    return


@app.cell
def _(px, ws_iron_demand):
    _scatter = px.scatter(
        ws_iron_demand,
        x="eaf",
        y="naive_scrap_demand",
        color=ws_iron_demand.index.get_level_values("region"),
        hover_data=[
            ws_iron_demand.index.get_level_values("region"),
            ws_iron_demand.index.get_level_values("year"),
            "eaf",
            "dri",
            "dri_demand",
            "naive_scrap_demand",
        ],
        labels="region",
        title="Worldsteel EAF crude steel production vs naive scrap demand (EAF - DRI)",
    )
    _scatter.add_shape(
        type="line",
        x0=ws_iron_demand["eaf"].min(),
        x1=ws_iron_demand["eaf"].max(),
        y0=1.1355 * ws_iron_demand["eaf"].min(),
        y1=1.1355 * ws_iron_demand["eaf"].max(),
        line=dict(color="red", dash="dash"),
        name="Expected scrap demand in EAF crude steel production (1.1355 * EAF)",
    )
    _scatter.show()
    return


@app.cell
def _(mo):
    mo.md("""
    ## Region mapping

    BIR reports a handful of large regions. `ws_yearbook_region` is the matching row in
    the yearbook tables, `ws_database_countries` the countries summed from the online
    database. Regions without a yearbook counterpart (India, Iran) are contained in
    Worldsteel's "Other Asia"/"Middle East" residuals and can only be compared through
    production-based shares.
    """)
    return


@app.cell
def _():
    eu28_countries = [
        "Austria",
        "Belgium",
        "Bulgaria",
        "Croatia",
        "Cyprus",
        "Czechia",
        "Denmark",
        "Estonia",
        "Finland",
        "France",
        "Germany",
        "Greece",
        "Hungary",
        "Ireland",
        "Italy",
        "Latvia",
        "Lithuania",
        "Luxembourg",
        "Malta",
        "Netherlands",
        "Poland",
        "Portugal",
        "Romania",
        "Slovakia",
        "Slovenia",
        "Spain",
        "Sweden",
        "United Kingdom",
    ]

    region_map = {
        "World": {"ws_yearbook_region": "World", "ws_database_countries": ["World"]},
        "China": {"ws_yearbook_region": "China", "ws_database_countries": ["China"]},
        "EU 28": {
            "ws_yearbook_region": "European Union",
            "ws_database_countries": eu28_countries,
        },
        "USA": {
            "ws_yearbook_region": "United States",
            "ws_database_countries": ["United States"],
        },
        "Japan": {"ws_yearbook_region": "Japan", "ws_database_countries": ["Japan"]},
        "Turkey": {
            "ws_yearbook_region": "Turkey",
            "ws_database_countries": ["Türkiye"],
        },
        "Korea": {
            "ws_yearbook_region": "South Korea",
            "ws_database_countries": ["South Korea"],
        },
        "Canada": {
            "ws_yearbook_region": "Canada",
            "ws_database_countries": ["Canada"],
        },
        # BIR reports Russia, the yearbooks only the CIS aggregate (incl. Ukraine etc.)
        "Russia": {"ws_yearbook_region": "CIS", "ws_database_countries": ["Russia"]},
        "India": {"ws_yearbook_region": None, "ws_database_countries": ["India"]},
        "Iran": {"ws_yearbook_region": None, "ws_database_countries": ["Iran"]},
    }

    # BIR uses "EU28"/"South Korea" in the share sheet and "EU 28"/"Korea" in the
    # consumption sheet.
    bir_region_alias = {"EU28": "EU 28", "South Korea": "Korea"}
    return bir_region_alias, region_map


@app.cell
def _(mo, region_map, ws_crude):
    _ws_countries = set(ws_crude.index.get_level_values("region"))
    missing_countries = {
        region: sorted(set(spec["ws_database_countries"] or []) - _ws_countries)
        for region, spec in region_map.items()
    }
    missing_countries = {k: v for k, v in missing_countries.items() if v}
    mo.md(f"Countries not present in the Worldsteel database: `{missing_countries}`")
    return


@app.cell
def _(pd, region_map, ws_bof, ws_crude, ws_eaf):
    def aggregate_ws_database(df: pd.DataFrame) -> pd.DataFrame:
        """Sum a Worldsteel database frame to the BIR regions."""
        frames = []
        for region, spec in region_map.items():
            countries = spec["ws_database_countries"]
            subset = df.loc[df.index.get_level_values("region").isin(countries)]
            if subset.empty:
                continue
            frames.append(
                subset.groupby("year", as_index=False)["value"].sum().assign(region=region)
            )
        return pd.concat(frames, ignore_index=True)

    ws_crude_regional = aggregate_ws_database(ws_crude)
    ws_eaf_regional = aggregate_ws_database(ws_eaf)
    ws_bof_regional = aggregate_ws_database(ws_bof)
    return ws_crude_regional, ws_eaf_regional


@app.cell
def _(pd, region_map, ws_scrap_yearbook):
    _yearbook_rows = []
    for _region, _spec in region_map.items():
        _ws_region = _spec["ws_yearbook_region"]
        if _ws_region is None:
            continue
        _subset = ws_scrap_yearbook[ws_scrap_yearbook["region"] == _ws_region]
        if _subset.empty:
            continue
        _yearbook_rows.append(_subset.assign(region=_region))
    ws_scrap_regional = pd.concat(_yearbook_rows, ignore_index=True)
    ws_scrap_regional
    return (ws_scrap_regional,)


@app.cell
def _(mo):
    mo.md("""
    ## Global scrap consumption
    """)
    return


@app.cell
def _(bir_consumption, pd, px, ws_scrap_global, ws_scrap_regional):
    scrap_global_comparison = pd.concat(
        [
            bir_consumption.query("region == 'World'"),
            ws_scrap_regional.query("region == 'World'"),
            ws_scrap_global.reset_index(),
        ],
        ignore_index=True,
    ).sort_values("year")

    px.line(
        scrap_global_comparison,
        x="year",
        y="value",
        color="source",
        markers=True,
        title="Global steel scrap consumption",
        labels={"value": "Scrap consumption [Mt]", "year": "Year"},
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## Regional scrap consumption
    """)
    return


@app.cell
def _(bir_consumption, mo, ws_scrap_regional):
    comparable_regions = sorted(set(bir_consumption["region"]) & set(ws_scrap_regional["region"]))
    consumption_region_picker = mo.ui.dropdown(
        options=comparable_regions,
        value="World" if "World" in comparable_regions else comparable_regions[0],
        label="Region",
    )
    consumption_region_picker
    return (consumption_region_picker,)


@app.cell
def _(
    bir_consumption,
    consumption_region_picker,
    pd,
    px,
    region_map,
    ws_scrap_regional,
):
    _region = consumption_region_picker.value
    consumption_comparison = (
        pd.concat(
            [
                bir_consumption[bir_consumption["region"] == _region].assign(source="BIR"),
                ws_scrap_regional[ws_scrap_regional["region"] == _region].assign(
                    source="Worldsteel"
                ),
            ],
            ignore_index=True,
        )
        .sort_values("year")
        .pivot_table(index="year", columns="source", values="value")
    )

    px.line(
        consumption_comparison.reset_index(),
        x="year",
        y=[c for c in ("BIR", "Worldsteel") if c in consumption_comparison],
        markers=True,
        title=(
            f"Steel scrap consumption, BIR '{_region}' vs. Worldsteel yearbook "
            f"'{region_map[_region]['ws_yearbook_region']}'"
        ),
        labels={
            "value": "Scrap consumption [Mt]",
            "year": "Year",
            "variable": "Source",
        },
    )
    return (consumption_comparison,)


@app.cell
def _(consumption_comparison, mo):
    _overlap = consumption_comparison.dropna()
    _overlap = _overlap.assign(
        deviation=lambda d: d["BIR"] - d["Worldsteel"],
        relative_deviation_percent=lambda d: ((d["BIR"] - d["Worldsteel"]) / d["Worldsteel"] * 100),
    )
    mo.ui.table(
        _overlap.reset_index(),
        label="Deviation between BIR and Worldsteel scrap consumption [Mt] for selected region",
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## Scrap share in crude steel production

    The direct scrap-consumption overlap is limited to 2004-2008. Over the longer BIR
    period the sources can be compared through the scrap share in crude steel
    production:

    - `BIR share`: share as published by BIR.
    - `BIR consumption / Worldsteel production`: BIR scrap consumption divided by
      Worldsteel database crude steel production (consistency check between the two BIR
      sheets and the production statistics).
    - `Worldsteel consumption / production` — yearbook scrap consumption over the same
      production denominator (2004-2008 only).
    - `Worldsteel EAF share` — EAF share of crude steel production, a lower bound proxy
      for scrap use (BOF routes also charge scrap).
    """)
    return


@app.cell
def _(bir_consumption, bir_region_alias, bir_share, ws_crude_regional):
    _bir_scrap_from_share = (
        bir_share.assign(region=lambda d: d["region"].replace(bir_region_alias))
        .merge(ws_crude_regional.rename(columns={"value": "production"}), on=["region", "year"])
        .assign(scrap_from_share=lambda d: d["value"] / 100 * d["production"])
    )

    bir_scrap = (
        bir_consumption.rename(columns={"value": "scrap_from_consumption"})
        .merge(_bir_scrap_from_share, on=["region", "year"], how="outer")
        .assign(scrap=lambda d: d[["scrap_from_consumption", "scrap_from_share"]].mean(axis=1))[
            ["region", "year", "scrap_from_consumption", "scrap_from_share", "scrap"]
        ]
        .set_index(["region", "year"])
    )
    bir_scrap
    return (bir_scrap,)


@app.cell
def _(
    bir_consumption,
    bir_region_alias,
    bir_scrap,
    bir_share,
    pd,
    ws_crude_regional,
    ws_eaf_regional,
    ws_scrap_regional,
):
    _production = ws_crude_regional.rename(columns={"value": "production"})

    _bir_scrap_share = bir_share.assign(
        region=lambda d: d["region"].replace(bir_region_alias),
        variable="BIR share",
    )[["region", "year", "value", "variable"]]

    _bir_over_ws = bir_consumption.merge(_production, on=["region", "year"]).assign(
        value=lambda d: d["value"] / d["production"] * 100,
        variable="BIR consumption / Worldsteel production",
    )[["region", "year", "value", "variable"]]

    _bir_harmon_over_ws = bir_scrap.merge(_production, on=["region", "year"]).assign(
        value=lambda d: d["scrap"] / d["production"] * 100,
        variable="BIR scrap (combined) / Worldsteel production",
    )[["region", "year", "value", "variable"]]

    _ws_over_ws = ws_scrap_regional.merge(_production, on=["region", "year"]).assign(
        value=lambda d: d["value"] / d["production"] * 100,
        variable="Worldsteel consumption / production",
    )[["region", "year", "value", "variable"]]

    _eaf = ws_eaf_regional.merge(_production, on=["region", "year"]).assign(
        value=lambda d: d["value"] / d["production"] * 100,
        variable="Worldsteel EAF share",
    )[["region", "year", "value", "variable"]]

    share_comparison = pd.concat(
        [_bir_scrap_share, _bir_over_ws, _bir_harmon_over_ws, _ws_over_ws, _eaf],
        ignore_index=True,
    ).sort_values(["region", "year"])
    return (share_comparison,)


@app.cell
def _(mo, share_comparison):
    share_regions = sorted(share_comparison["region"].unique())
    share_region_picker = mo.ui.dropdown(
        options=share_regions,
        value="World" if "World" in share_regions else share_regions[0],
        label="Region",
    )
    share_region_picker
    return (share_region_picker,)


@app.cell
def _(px, share_comparison, share_region_picker):
    _region = share_region_picker.value
    px.line(
        share_comparison[share_comparison["region"] == _region],
        x="year",
        y="value",
        color="variable",
        markers=True,
        title=f"Scrap share in crude steel production, {_region}",
        labels={"value": "Share [%]", "year": "Year", "variable": "Series"},
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    - Difference between BIR reported and BIR consumption / Worldsteel production is due to the fact that BIR's reports slightly different data for the crude steel production denominator in the PDFs (although the source apparently is Worldsteel as well). For example, in 2013: Worldsteel reports 1,653 Mt, BIR reports 1,607 Mt. For a scrap consumption of 580 Mt, this results in a scrap share of 35.1% vs. 36.1%.
    - Difference with Worldsteel consumption / production is due to the fact that the Worldsteel yearbook digitisation reports a lower scrap consumption than BIR (e.g. 2006: 459.3 Mt vs. 500 Mt).
    - It's surprising to me that scrap + EAF share actually decreases over time
    """)
    return


@app.cell
def _(mo, share_comparison):
    mo.ui.table(share_comparison, label="Scrap share in crude steel production [%]")
    return


@app.cell
def _(mo):
    mo.md("""
    ## Regional iron-route regression

    Fit a multiple, multi-output linear regression over the overlapping regional-year
    observations. The inputs are BIR scrap consumption and Worldsteel pig iron and DRI
    production; the outputs are Worldsteel BOF and EAF production. The BOF equation is
    constrained to have a zero DRI coefficient, while the EAF equation uses all three
    inputs. The World aggregate is excluded because it duplicates the regional
    observations and would dominate the fit. All quantities are in Mt.
    """)
    return


@app.cell
def _(bir_scrap, pd, region_map, ws_iron_demand):
    _columns = ["pigiron", "dri", "bof", "eaf"]
    _regional_frames = []
    for _region, _spec in region_map.items():
        if _region == "World":
            continue
        _countries = _spec["ws_database_countries"]
        _subset = ws_iron_demand.loc[
            ws_iron_demand.index.get_level_values("region").isin(_countries), _columns
        ]
        if _subset.empty:
            continue
        _regional_frames.append(
            _subset.groupby("year")[_columns].sum(min_count=1).assign(region=_region).reset_index()
        )

    ws_iron_demand_regional = (
        pd.concat(_regional_frames, ignore_index=True).set_index(["region", "year"]).sort_index()
    )
    regression_data = (
        bir_scrap[["scrap"]]
        .join(ws_iron_demand_regional, how="inner")
        .apply(pd.to_numeric, errors="coerce")
        .dropna(subset=["scrap", *_columns])
        .sort_index()
    )
    regression_data
    return (regression_data,)


@app.cell
def _(np, pd, regression_data):
    regression_inputs = ["scrap", "pigiron", "dri"]
    regression_outputs = ["bof", "eaf"]

    _x = regression_data[regression_inputs].to_numpy()
    _y = regression_data[regression_outputs].to_numpy()
    _design = np.column_stack([np.ones(len(_x)), _x])
    _bof_design = _design[:, [0, 1, 2]]
    _bof_coefficients, _, _bof_rank, _ = np.linalg.lstsq(_bof_design, _y[:, 0], rcond=None)
    _eaf_coefficients, _, _eaf_rank, _ = np.linalg.lstsq(_design, _y[:, 1], rcond=None)
    _coefficients = np.column_stack([np.append(_bof_coefficients, 0.0), _eaf_coefficients])
    _predicted = _design @ _coefficients

    linear_regression_coefficients = pd.DataFrame(
        _coefficients,
        index=["intercept", *regression_inputs],
        columns=regression_outputs,
    )
    regression_predictions = regression_data[regression_outputs].copy()
    regression_predictions[[f"{output}_predicted" for output in regression_outputs]] = _predicted

    _residuals = _y - _predicted
    _total_sum_squares = ((_y - _y.mean(axis=0)) ** 2).sum(axis=0)
    regression_metrics = pd.DataFrame(
        {
            "r_squared": 1 - (_residuals**2).sum(axis=0) / _total_sum_squares,
            "rmse": np.sqrt((_residuals**2).mean(axis=0)),
            "observations": len(regression_data),
            "design_rank": [_bof_rank, _eaf_rank],
        },
        index=regression_outputs,
    )
    return (
        linear_regression_coefficients,
        regression_metrics,
        regression_predictions,
    )


@app.cell
def _(linear_regression_coefficients, mo, regression_metrics):
    mo.vstack(
        [
            mo.ui.table(
                linear_regression_coefficients.reset_index(names="term"),
                label="Regression coefficients [Mt output per Mt input]",
            ),
            mo.ui.table(
                regression_metrics.reset_index(names="output"),
                label="In-sample regression metrics",
            ),
        ]
    )
    return


@app.cell
def _(pd, px, regression_predictions):
    _actual = regression_predictions[["bof", "eaf"]].rename(columns={"bof": "BOF", "eaf": "EAF"})
    _predicted = regression_predictions[["bof_predicted", "eaf_predicted"]].rename(
        columns={"bof_predicted": "BOF", "eaf_predicted": "EAF"}
    )
    comparison = (
        pd.concat(
            [
                _actual.stack().rename("actual"),
                _predicted.stack().rename("predicted"),
            ],
            axis=1,
        )
        .rename_axis(index=["region", "year", "route"])
        .reset_index()
    )
    _plot = px.scatter(
        comparison,
        x="actual",
        y="predicted",
        color="region",
        facet_col="route",
        hover_data=["region", "year"],
        # trendline="ols",
        title="Regional BOF and EAF production: actual vs regression prediction",
        labels={
            "actual": "Actual production [Mt]",
            "predicted": "Predicted production [Mt]",
        },
    )
    _lower = comparison[["actual", "predicted"]].min().min()
    _upper = comparison[["actual", "predicted"]].max().max()
    _plot.add_shape(
        type="line",
        x0=_lower,
        x1=_upper,
        y0=_lower,
        y1=_upper,
        line=dict(color="red", dash="dash"),
        row="all",
        col="all",
    )
    _plot
    return


@app.cell
def _(mo):
    mo.md("""
    ## Per-region iron-route regressions

    Fit the same constrained regression independently for each region. Each BOF model
    uses scrap and pig iron, with its DRI coefficient fixed to zero; each EAF model uses
    scrap, pig iron, and DRI.
    """)
    return


@app.cell
def _(np, pd, regression_data):
    _inputs = ["scrap", "pigiron", "dri"]
    _outputs = ["bof", "eaf"]
    _coefficient_frames = []
    _metric_rows = []
    _prediction_frames = []

    for _region, _data in regression_data.groupby(level="region"):
        _x = _data[_inputs].to_numpy()
        _y = _data[_outputs].to_numpy()
        _design = np.column_stack([np.ones(len(_x)), _x])
        _bof_design = _design[:, [0, 1, 2]]

        _bof_coefficients, _, _bof_rank, _ = np.linalg.lstsq(_bof_design, _y[:, 0], rcond=None)
        _eaf_coefficients, _, _eaf_rank, _ = np.linalg.lstsq(_design, _y[:, 1], rcond=None)
        _coefficients = np.column_stack([np.append(_bof_coefficients, 0.0), _eaf_coefficients])
        _predicted = _design @ _coefficients
        _residuals = _y - _predicted
        _total_sum_squares = ((_y - _y.mean(axis=0)) ** 2).sum(axis=0)
        _r_squared = np.divide(
            (_total_sum_squares - (_residuals**2).sum(axis=0)),
            _total_sum_squares,
            out=np.full(2, np.nan),
            where=_total_sum_squares != 0,
        )

        _coefficient_frames.append(
            pd.DataFrame(
                _coefficients,
                index=["intercept", *_inputs],
                columns=_outputs,
            )
            .rename_axis("term")
            .reset_index()
            .assign(region=_region)
        )
        for _output_index, _output in enumerate(_outputs):
            _metric_rows.append(
                {
                    "region": _region,
                    "output": _output,
                    "r_squared": _r_squared[_output_index],
                    "rmse": np.sqrt((_residuals[:, _output_index] ** 2).mean()),
                    "observations": len(_data),
                    "design_rank": [_bof_rank, _eaf_rank][_output_index],
                }
            )
        _prediction_frames.append(
            _data[_outputs]
            .assign(
                bof_predicted=_predicted[:, 0],
                eaf_predicted=_predicted[:, 1],
            )
            .reset_index()
        )

    regional_regression_coefficients = pd.concat(_coefficient_frames, ignore_index=True)[
        ["region", "term", *_outputs]
    ]
    regional_regression_metrics = pd.DataFrame(_metric_rows)
    regional_regression_predictions = pd.concat(_prediction_frames, ignore_index=True)
    return (
        regional_regression_coefficients,
        regional_regression_metrics,
        regional_regression_predictions,
    )


@app.cell
def _(px, regional_regression_coefficients):
    _coefficient_data = regional_regression_coefficients[
        regional_regression_coefficients["term"] != "intercept"
    ].melt(
        id_vars=["region", "term"],
        value_vars=["bof", "eaf"],
        var_name="route",
        value_name="coefficient",
    )
    px.scatter(
        _coefficient_data,
        x="region",
        y="coefficient",
        color="term",
        facet_col="route",
        hover_data=["region", "term"],
        title="Regression coefficients by region and production route",
        labels={
            "region": "Region",
            "coefficient": "Regression coefficient [Mt/Mt]",
            "term": "Input",
            "route": "Output",
        },
    )
    return


@app.cell
def _(mo, regional_regression_coefficients):
    _regions = sorted(regional_regression_coefficients["region"].unique())
    regional_regression_picker = mo.ui.dropdown(
        options=_regions,
        value=_regions[0],
        label="Region",
    )
    regional_regression_picker
    return (regional_regression_picker,)


@app.cell
def _(
    mo,
    regional_regression_coefficients,
    regional_regression_metrics,
    regional_regression_picker,
):
    _region = regional_regression_picker.value
    mo.vstack(
        [
            mo.ui.table(
                regional_regression_coefficients[
                    regional_regression_coefficients["region"] == _region
                ],
                label=f"Regression coefficients for {_region}",
            ),
            mo.ui.table(
                regional_regression_metrics[regional_regression_metrics["region"] == _region],
                label=f"In-sample regression metrics for {_region}",
            ),
        ]
    )
    return


@app.cell
def _(pd, px, regional_regression_predictions):
    _actual = (
        regional_regression_predictions.set_index(["region", "year"])[["bof", "eaf"]]
        .rename(columns={"bof": "BOF", "eaf": "EAF"})
        .stack()
        .rename("actual")
    )
    _predicted = (
        regional_regression_predictions.set_index(["region", "year"])[
            ["bof_predicted", "eaf_predicted"]
        ]
        .rename(columns={"bof_predicted": "BOF", "eaf_predicted": "EAF"})
        .stack()
        .rename("predicted")
    )
    _comparison = pd.concat([_actual, _predicted], axis=1).reset_index(
        names=["region", "year", "route"]
    )
    _plot = px.scatter(
        _comparison,
        x="actual",
        y="predicted",
        color="region",
        facet_col="route",
        hover_data=["year"],
        title="Actual vs regression-predicted production",
        labels={
            "actual": "Actual production [Mt]",
            "predicted": "Predicted production [Mt]",
        },
    )
    _plot.update_yaxes(matches=None)
    _plot.update_xaxes(matches=None)
    _plot
    return


if __name__ == "__main__":
    app.run()
