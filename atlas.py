"""Command line interface for coupling REMIND-MFA with the ATLAS trade model."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer
from dotenv import load_dotenv

from remind_mfa.atlas_coupling import (
    ATLAS_DATA_PIPELINE_ROOT,
    ATLAS_TRADE_ROOT,
    AtlasCo2Price,
    AtlasScenarioPkBudg,
    AtlasVariant,
    AtlasShareMode,
    copy_demand_to_atlas,
    copy_trade_to_mfa,
    execute_command,
    get_coupling_paths,
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
            "ATLAS_Trade only produces a single future scenario for this material.",
            err=True,
        )


@app.command()
def run_mfa(
    model: ModelOption,
    stage: Annotated[Literal["one", "two"], typer.Option(help="MFA stage to run.")],
) -> None:
    """Run one model of the MFA: either to produce the demand (stage one) or the actual results (stage two)."""

    config_names = ["default", "atlas_run1"] if stage == "one" else ["default", "atlas_run2"]
    typer.echo(f"Run MFA with model={model} and config={','.join(config_names)}")
    config = load_config(list(config_names), model)
    model_instance = init_model(cfg=config)
    model_instance.run()
    model_instance.export()


@app.command("copy-demands")
def copy_demands(
    model: ModelOption,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing ATLAS demand target.")
    ] = False,
) -> None:
    """Convert an MFA demand export to the format and location ATLAS expects."""

    paths = get_coupling_paths(model, ["default", "atlas_run1"])
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
    paths = get_coupling_paths(model, ["default", "atlas_run2"])
    if not source:
        variant_value = variant.value.replace("-", "_")
        model_folder = "future" if model == ModelNames.STEEL else "future_plastics"
        source = (
            ATLAS_TRADE_ROOT
            / "outputs"
            / "output_no_cet"
            / model_folder
            / variant_value
            / "cache"
            / f"future_projections_summary_{variant_value}.xlsx"
        )
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
    """Run the ATLAS data-preprocessing Snakemake workflow."""

    execute_command(["pixi", "run", "snakemake", "--cores", "5"], ATLAS_DATA_PIPELINE_ROOT)


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
    """Run MFA, preprocessing, ATLAS, and MFA again."""

    run_mfa(model, stage="one")
    copy_demands(model, force=force)
    preprocess()
    calibrate(model)
    validate(model)
    future(model=model, variant=variant, co2price=co2price, scenario_pkbudg=scenario_pkbudg)
    copy_trade(model, variant=variant, co2price=co2price, scenario_pkbudg=scenario_pkbudg)
    run_mfa(model, stage="two")


if __name__ == "__main__":
    load_dotenv()
    app()
