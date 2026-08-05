import marimo

__generated_with = "0.23.15"
app = marimo.App(width="medium")


@app.cell
def _():
    import io
    import os
    import tarfile
    from pathlib import Path

    import marimo as mo
    import pandas as pd
    import plotly.express as px
    from dotenv import load_dotenv

    return Path, io, load_dotenv, mo, os, pd, px, tarfile


@app.cell
def _(Path, load_dotenv, mo, os):
    repo_root = Path.cwd().parent
    if not (repo_root / "pyproject.toml").exists():
        raise FileNotFoundError("Run this notebook from the repository root.")

    load_dotenv()
    madrat_output_dir = Path(os.environ["MADRAT_OUTPUTFOLDER"])
    if not madrat_output_dir.is_absolute():
        madrat_output_dir = repo_root / madrat_output_dir

    if not madrat_output_dir.exists():
        raise FileNotFoundError(
            f"MADRAT_OUTPUTFOLDER {madrat_output_dir} does not exist. "
            "Set the environment variable MADRAT_OUTPUTFOLDER."
        )

    remind_archives = sorted(madrat_output_dir.glob("*_remind.tgz"))
    if not remind_archives:
        raise FileNotFoundError(f"No *_remind.tgz archives found in {madrat_output_dir}.")

    archive_picker = mo.ui.dropdown(
        options={archive.name: archive for archive in remind_archives},
        value=remind_archives[-1].name,
        label="REMIND archive",
    )
    archive_picker
    return archive_picker, repo_root


@app.cell
def _(Path, archive_picker, io, mo, pd, tarfile):
    archive_path = Path(archive_picker.value)


    def read_cs4r_from_archive(
        archive: Path, filename: str, columns: list[str]
    ) -> pd.DataFrame:
        with tarfile.open(archive, "r:gz") as tar:
            filename = f"./{filename}" if not filename.startswith("./") else filename
            try:
                stream = tar.extractfile(filename)
                if stream is None:
                    raise ValueError(f"Could not read {filename} from {archive.name}.")
            except KeyError:
                raise ValueError(
                    f"{filename} not found in {archive.name}. Other files: {tar.getnames()}"
                )
            text = io.TextIOWrapper(stream, encoding="utf-8")
            return pd.read_csv(text, comment="*", header=None, names=columns)


    remind_fedemand_industry = read_cs4r_from_archive(
        archive_path,
        "f_fedemandInd.cs4r",
        ["Time", "Region", "Scenario", "Variable", "value"],
    ).pivot_table(
        index=["Time", "Region", "Scenario"],
        columns="Variable",
        values="value",
        aggfunc="sum",
    )
    mo.ui.table(remind_fedemand_industry, label="f_fedemandInd.cs4r")
    return archive_path, read_cs4r_from_archive, remind_fedemand_industry


@app.cell
def _(archive_path, mo, read_cs4r_from_archive):
    remind_secondary_share = (
        read_cs4r_from_archive(
            archive_path,
            "p37_steel_secondary_max_share.cs4r",
            ["Time", "Region", "Scenario", "value"],
        )
        .rename(columns={"value": "steel_secondary_share"})
        .pivot_table(
            index=["Time", "Region", "Scenario"],
            values="steel_secondary_share",
            aggfunc="sum",
        )
    )
    mo.ui.table(remind_secondary_share, label="p37_steel_secondary_max_share.cs4r")
    return (remind_secondary_share,)


@app.cell
def _(archive_path, mo, read_cs4r_from_archive):
    remind_clinker_ratio = (
        read_cs4r_from_archive(
            archive_path,
            "p37_clinker-to-cement-ratio.cs4r",
            ["Time", "Region", "value"],
        )
        .rename(columns={"value": "cement_clinker_ratio"})
        .pivot_table(
            index=["Time", "Region"],
            values="cement_clinker_ratio",
            aggfunc="sum",
        )
    )
    mo.ui.table(remind_clinker_ratio, label="p37_clinker-to-cement-ratio.cs4r")
    return (remind_clinker_ratio,)


@app.cell
def _(pd, repo_root):
    mfa_steel_dir = repo_root / "data/steel/output/export/mrindustry"
    mfa_steel_production = pd.read_csv(mfa_steel_dir / "steel_production_total.csv")
    mfa_steel_production_secondary = pd.read_csv(
        mfa_steel_dir / "steel_production_secondary.csv"
    )
    mfa_steel_scrap = pd.read_csv(mfa_steel_dir / "steel_scrap.csv")

    mfa_steel = (
        mfa_steel_scrap.groupby(["Time", "Region"], as_index=False)["steel_scrap"]
        .sum()
        .merge(mfa_steel_production, on=["Time", "Region"], how="outer")
        .merge(mfa_steel_production_secondary, on=["Time", "Region"], how="outer")
        .fillna(0)
    )
    mfa_steel["steel_production_total"] = mfa_steel["steel_production_total"] / 1e9
    mfa_steel["steel_production_secondary"] = mfa_steel["steel_production_secondary"] / 1e9
    mfa_steel["steel_scrap"] = mfa_steel["steel_scrap"] / 1e9
    return (mfa_steel,)


@app.cell
def _(pd, repo_root):
    mfa_cement_dir = repo_root / "data/cement/output/export/mrindustry"
    mfa_cement_production = pd.read_csv(mfa_cement_dir / "cement_production.csv")
    mfa_cement_clinker_ratio = pd.read_csv(mfa_cement_dir / "cement_clinker_ratio.csv")

    mfa_cement = mfa_cement_production.merge(
        mfa_cement_clinker_ratio, on=["Time", "Region"], how="outer"
    )
    mfa_cement["cement_production"] = mfa_cement["cement_production"] / 1e9
    return (mfa_cement,)


@app.cell
def _(mfa_cement, mfa_steel, remind_fedemand_industry):
    remind_regions = sorted(remind_fedemand_industry.reset_index()["Region"].unique())
    missing_mfa_regions = {
        "cement": set(remind_regions) - set(mfa_cement["Region"].unique()),
        "steel": set(remind_regions) - set(mfa_steel["Region"].unique()),
    }
    missing_mfa_regions = {
        material: regions for material, regions in missing_mfa_regions.items() if regions
    }
    if missing_mfa_regions:
        raise ValueError(
            "Regions in REMIND archive not found in MFA exports: "
            f"{missing_mfa_regions}. Make sure that the MFAs use the same region "
            "mapping as REMIND."
        )
    return (remind_regions,)


@app.cell
def _(mo, remind_fedemand_industry, remind_regions):
    remind_scenarios = sorted(
        set(remind_fedemand_industry.reset_index()["Scenario"].unique())
    )
    scenario_picker = mo.ui.dropdown(
        options=remind_scenarios,
        value="SSP2" if "SSP2" in remind_scenarios else remind_scenarios[0],
        label="Scenario",
    )
    region_picker = mo.ui.dropdown(
        options=remind_regions,
        value=remind_regions[0],
        label="Region",
    )
    mo.vstack([scenario_picker, region_picker])
    return region_picker, scenario_picker


@app.cell
def _(region_picker, scenario_picker):
    scenario = scenario_picker.value
    region = region_picker.value
    return region, scenario


@app.cell
def _(mfa_steel, pd, remind_fedemand_industry, remind_secondary_share):
    remind_steel = pd.concat([remind_fedemand_industry, remind_secondary_share]).query(
        "Scenario == @scenario and Region == @region"
    )
    remind_steel["ue_steel_total"] = (
        remind_steel["ue_steel_primary"] + remind_steel["ue_steel_secondary"]
    )
    remind_steel["steel_secondary_share_calc"] = remind_steel[
        "ue_steel_secondary"
    ] / remind_steel["ue_steel_total"].where(remind_steel["ue_steel_total"] != 0)

    mfa_steel_region = mfa_steel.query("Region == @region").drop(columns="Region")
    comparison_steel = (
        remind_steel.merge(
            mfa_steel_region,
            on="Time",
            how="outer",
        ).sort_values("Time")
    )[
        [
            "Time",
            "ue_steel_total",
            "ue_steel_secondary",
            "steel_secondary_share_calc",
            "steel_secondary_share",
            "steel_scrap",
            "steel_production_total",
            "steel_production_secondary",
        ]
    ].rename(
        columns={
            "ue_steel_total": "remind_steel_production_total",
            "ue_steel_secondary": "remind_steel_production_secondary",
            "steel_secondary_share_calc": "remind_secondary_share_calc",
            "steel_secondary_share": "remind_secondary_share",
            "steel_scrap": "mfa_steel_scrap",
            "steel_production_total": "mfa_steel_production_total",
            "steel_production_secondary": "mfa_steel_production_secondary",
        }
    )
    comparison_steel
    return (comparison_steel,)


@app.cell
def _(comparison_steel, px, region, scenario):
    # TODO: plotly doesn't want to add lines for the remind steel production before 2100 (probably because of different year resolution)
    px.line(
        comparison_steel,
        x="Time",
        y=[
            "mfa_steel_production_total",
            "remind_steel_production_total",
        ],
        title=f"Steel production for {scenario} ({region})",
        markers=True,
    )
    return


@app.cell
def _(comparison_steel, px, region, scenario):
    px.line(
        comparison_steel,
        x="Time",
        y=[
            "mfa_steel_production_secondary",
            "remind_steel_production_secondary",
        ],
        title=f"Secondary steel production for {scenario} ({region})",
        markers=True,
    )
    return


@app.cell
def _(comparison_steel, px, region, scenario):
    px.line(
        comparison_steel,
        x="Time",
        y=[
            "remind_secondary_share",
            "remind_secondary_share_calc",
        ],
        title=f"Steel secondary share for {scenario} ({region})",
        markers=True,
    )
    return


@app.cell
def _(comparison_steel, px, region, scenario):
    px.line(
        comparison_steel,
        x="Time",
        y=[
            "mfa_steel_scrap",
        ],
        title=f"Steel scrap for {scenario} ({region})",
        markers=True,
    )
    return


@app.cell
def _(mfa_cement, remind_clinker_ratio, remind_fedemand_industry):
    remind_cement = (
        remind_fedemand_industry.reset_index()
        .query("Scenario == @scenario and Region == @region")[["Time", "ue_cement"]]
        .merge(
            remind_clinker_ratio.reset_index()
            .query("Region == @region")[["Time", "cement_clinker_ratio"]]
            .rename(columns={"cement_clinker_ratio": "remind_cement_clinker_ratio"}),
            on="Time",
            how="outer",
        )
        .rename(columns={"ue_cement": "remind_cement_production"})
    )
    mfa_cement_region = (
        mfa_cement.query("Region == @region")
        .drop(columns="Region")
        .rename(
            columns={
                "cement_production": "mfa_cement_production",
                "cement_clinker_ratio": "mfa_cement_clinker_ratio",
            }
        )
    )
    cement_comparison = remind_cement.merge(
        mfa_cement_region, on="Time", how="outer"
    ).sort_values("Time")
    cement_comparison
    return (cement_comparison,)


@app.cell
def _(cement_comparison, px, region, scenario):
    px.line(
        cement_comparison,
        x="Time",
        y=[
            "mfa_cement_production",
            "remind_cement_production",
        ],
        title=f"Cement production for {scenario} ({region})",
        markers=True,
    )
    return


@app.cell
def _(cement_comparison, px, region, scenario):
    px.line(
        cement_comparison,
        x="Time",
        y=[
            "mfa_cement_clinker_ratio",
            "remind_cement_clinker_ratio",
        ],
        title=f"Cement clinker ratio for {scenario} ({region})",
        markers=True,
    )
    return


if __name__ == "__main__":
    app.run()
