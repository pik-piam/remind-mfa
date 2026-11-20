"""Command line interface for coupling REMIND-MFA with the ATLAS trade model."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer
from dotenv import load_dotenv

from remind_mfa.atlas_coupling import (
    ATLAS_DATA_PIPELINE_ROOT,
    ATLAS_TRADE_ROOT,
    PIPELINE_INPUT_MODELS,
    AtlasCo2Price,
    AtlasScenarioPkBudg,
    AtlasShareMode,
    AtlasGreySupplySource,
    AtlasVariant,
    copy_demand_to_atlas,
    copy_trade_to_mfa,
    default_atlas_trade_source,
    execute_command,
    find_missing_pipeline_inputs,
    get_coupling_paths,
    get_model_spec,
    scenario_pkbudg_is_effective,
)
from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames, init_model

app = typer.Typer(help="Run the model-specific REMIND-MFA and ATLAS coupling workflow.")

ModelOption = Annotated[
    ModelNames,
    typer.Option("--model", help="MFA model."),
]
ConfigOption = Annotated[
    list[str],
    typer.Option("--config", help="Configuration name under config/. Repeat to stack layers."),
]
VariantOption = Annotated[AtlasVariant, typer.Option(help="ATLAS technology variant.")]
ShareModeOption = Annotated[AtlasShareMode, typer.Option(help="ATLAS share mode.")]
GreySupplySourceOption = Annotated[
    AtlasGreySupplySource, typer.Option(help="ATLAS grey-supply source.")
]
Co2PriceOption = Annotated[AtlasCo2Price, typer.Option(help="ATLAS CO2-price option.")]
ScenarioPkBudgOption = Annotated[
    AtlasScenarioPkBudg, typer.Option(help="ATLAS PkBudg scenario selection.")
]


def _warn_if_scenario_pkbudg_ignored(
    model: ModelNames, scenario_pkbudg: AtlasScenarioPkBudg
) -> None:
    if not scenario_pkbudg_is_effective(model) and scenario_pkbudg != AtlasScenarioPkBudg.BUDG_1000:
        typer.echo(
            f"[WARN] --scenario-pkbudg={scenario_pkbudg.value} has no effect for model={model}: "
            "ATLAS-Trade only produces a single future scenario for this material.",
            err=True,
        )


@app.command()
def run_mfa(
    model: ModelOption,
    stage: Annotated[Literal["one", "two"], typer.Option(help="MFA stage to run.")],
) -> None:
    """Run one model of the MFA: either to produce the demand (stage one) or the actual results (stage two)."""

    config_names = (
        ["default", "hpc", "atlas_run1"] if stage == "one" else ["default", "hpc", "atlas_run2"]
    )
    typer.echo(f"Run MFA with model={model} and config={','.join(config_names)}")
    config = load_config(list(config_names), model)
    model_instance = init_model(cfg=config)
    model_instance.run()
    model_instance.export()
    if stage == "two":
        model_instance.visualize()


@app.command("copy-demands")
def copy_demands(
    model: ModelOption,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing ATLAS demand target.")
    ] = False,
) -> None:
    """Convert the MFA demand (and, for steel, scrap) exports to the format and location ATLAS expects."""

    paths = get_coupling_paths(model, ["default", "hpc", "atlas_run1"])
    for demand_source, demand_target in paths.mfa_pipeline_mapping.items():
        result = copy_demand_to_atlas(model, demand_source, demand_target, force)
        typer.echo(f"Wrote {len(result)} demand rows to {demand_target}")


@app.command("copy-trade")
def copy_trade(
    model: ModelOption,
    source: Annotated[
        Path | None,
        typer.Option("--source", help="Path to trade projection produced by the ATLAS model."),
    ] = None,
    variant: VariantOption = AtlasVariant.GREEN_GREY,
    co2price: Co2PriceOption = AtlasCo2Price.NONE,
    scenario_pkbudg: ScenarioPkBudgOption = AtlasScenarioPkBudg.BUDG_1000,
    input_data_path: Annotated[
        Path | None, typer.Option(help="MFA input-data root override.")
    ] = None,
) -> None:
    """Aggregate ATLAS bilateral trade into MFA CS4R parameters."""

    _warn_if_scenario_pkbudg_ignored(model, scenario_pkbudg)
    paths = get_coupling_paths(model, ["default", "hpc", "atlas_run2"])
    if not source:
        source = default_atlas_trade_source(model, variant)
    imports_path, exports_path = copy_trade_to_mfa(
        model,
        source,
        scenario_pkbudg,
        input_data_path=input_data_path or paths.input_data_path,
        region_dimension_path=paths.region_dimension_path,
    )
    typer.echo(f"Wrote ATLAS trade inputs: {imports_path}, {exports_path}")


@app.command()
def preprocess() -> None:
    """Run the ATLAS data-preprocessing Snakemake workflow.

    The workflow builds the inputs of all goods at once, so it needs the copied MFA exports of all
    models, not only of the one that is coupled.
    """

    missing_inputs = find_missing_pipeline_inputs(["default", "hpc", "atlas_run1"])
    if missing_inputs:
        missing_files = "\n".join(
            f"  {path}" for paths in missing_inputs.values() for path in paths
        )
        commands = "\n".join(
            f"  uv run atlas.py run-mfa --model {model.value} --stage one"
            f" && uv run atlas.py copy-demands --model {model.value}"
            for model in missing_inputs
        )
        typer.echo(
            "[ERROR] The ATLAS data pipeline reads the MFA exports of "
            f"{', '.join(model.value for model in PIPELINE_INPUT_MODELS)}, "
            f"but these files are missing:\n{missing_files}\nCreate them with:\n{commands}",
            err=True,
        )
        raise typer.Exit(code=1)

    execute_command(
        [
            "pixi",
            "run",
            "snakemake",
            "--cores",
            "5",
            "--config",
            "steel_mfa={region_resolution: H12}",
            "--rerun-incomplete",
        ],
        ATLAS_DATA_PIPELINE_ROOT,
    )


@app.command()
def calibrate(model: ModelOption) -> None:
    """Calibrate the ATLAS trade model."""

    execute_command(
        [
            "pixi",
            "run",
            "python",
            "run/run_history_calibration.py",
            "--good",
            model,
            "--region-set",
            "REMIND",
        ],
        ATLAS_TRADE_ROOT,
    )


@app.command()
def validate(model: ModelOption) -> None:
    """Validate the ATLAS trade model against historical data."""

    execute_command(
        [
            "pixi",
            "run",
            "python",
            "run/run_history_validation.py",
            "--good",
            model,
            "--region-set",
            "REMIND",
        ],
        ATLAS_TRADE_ROOT,
    )


@app.command()
def future(
    model: ModelOption,
    variant: VariantOption = AtlasVariant.GREEN_GREY,
    share_mode: ShareModeOption = AtlasShareMode.SINGLE_FOSSIL,
    grey_supply_source: GreySupplySourceOption = AtlasGreySupplySource.MIC3_BASELINE,
    co2price: Co2PriceOption = AtlasCo2Price.NONE,
    scenario_pkbudg: ScenarioPkBudgOption = AtlasScenarioPkBudg.BUDG_1000,
    projection_years: Annotated[
        str, typer.Option(help="Comma-separated list of projection years.")
    ] = ",".join(str(year) for year in range(2023, 2051)),
) -> None:
    """Calculate ATLAS future trade projections."""

    _warn_if_scenario_pkbudg_ignored(model, scenario_pkbudg)
    execute_command(
        [
            "pixi",
            "run",
            "python",
            "run/run_future_scenarios.py",
            "--good",
            model,
            "--run-model",
            variant.value,
            "--green-grey-share-mode",
            share_mode.value,
            "--grey-supply-source",
            grey_supply_source.value,
            "--model",
            "--region-set",
            "REMIND",
            "--co2price",
            co2price.value,
            "--scenario-PkBudg",
            scenario_pkbudg.value,
            "--projection-years",
            projection_years,
            "--excel",
        ],
        ATLAS_TRADE_ROOT,
    )


@app.command()
def couple(
    model: ModelOption,
    variant: VariantOption = AtlasVariant.GREEN_GREY,
    co2price: Co2PriceOption = AtlasCo2Price.NONE,
    scenario_pkbudg: ScenarioPkBudgOption = AtlasScenarioPkBudg.BUDG_1000,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Run MFA, preprocessing, ATLAS, and MFA again.

    The first MFA stage runs for all models that the ATLAS data pipeline reads, so that their
    exports are current, not only for the model that is coupled.
    """

    get_model_spec(model)
    for pipeline_model in PIPELINE_INPUT_MODELS:
        run_mfa(pipeline_model, stage="one")
        copy_demands(pipeline_model, force=force)
    preprocess()
    calibrate(model)
    validate(model)
    future(model=model, variant=variant, co2price=co2price, scenario_pkbudg=scenario_pkbudg)
    copy_trade(model, variant=variant, co2price=co2price, scenario_pkbudg=scenario_pkbudg)
    run_mfa(model, stage="two")


if __name__ == "__main__":
    load_dotenv()
    app()
