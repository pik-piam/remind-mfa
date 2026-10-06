"""Run the MFA model for all CE scenario x trade scenario combinations.

The baseline run (no CE measures, default trade) is executed first and its export folder is
chained into the `fix_supply` runs, which need it as `transience.baseline_pickle_path`.

Must be run from the repository root, as `config_loader.CONFIG_DIR` is `Path.cwd() / "config"`.

Usage:
    uv run python scripts/run_transience_all.py steel
    uv run python scripts/run_transience_all.py plastics --config default --config myoverlay
    uv run python scripts/run_transience_all.py steel \\
        --baseline 2026-10-02--12-37-08_steel_SSP2_h12_Baseline_Steel_01_06_2026_default
"""

import copy
import logging
import os
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from remind_mfa.cli.helper import prompt_for_config_names
from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames, init_model

app = typer.Typer(add_completion=False)

CE_SCENARIOS = {
    "steel": [
        "Downsizing_Conservative_Steel_01_06_2026",
        "Downsizing_Highly_Ambitious_Steel_result_01_06_2026",
        "Redesign_ Conservative_Steel",
        "Redesign_ Highly_Ambitious_Steel",
        "Remanufacturing_Conservative_Steel",
        "Remanufacturing_Highly_Ambitious_Steel",
        "AHSS & HSS_ Conservative_Steel",
        "AHSS & HSS_ Highly_Ambitious_Steel",
        "Combined_Conservative_Steel",
        "Combined_Highly_Ambitious_Steel",
    ],
    "plastics": [
        "CE-PET_fd_plastics_S1",
        "CE-PET_fd_plastics_S2",
    ],
}

# The no-CE reference run that all fix_supply runs are compared against.
BASELINE_SCENARIO = {
    "steel": "Baseline_Steel_01_06_2026",
    "plastics": "CE-PET_fd_plastics_S0",
}

TRADE_SCENARIOS = ["default", "fix_supply_alpha0", "fix_supply_alpha1"]


def configure_logging():
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    for package in ["alembic", "plotly", "kaleido", "choreographer"]:
        logging.getLogger(package).setLevel(logging.WARNING)


def prepare_base_cfg(base_cfg: dict, show_figs: bool, save_figs: bool) -> dict:
    """Apply the batch-run settings a long unattended run needs."""
    base_cfg["visualization"]["do_show_figs"] = show_figs
    base_cfg["visualization"]["do_save_figs"] = save_figs
    logging.info(f"Figures: show={show_figs}, save={save_figs}.")

    # the baseline pickle is only written when both of these are on
    base_cfg["export"]["do_export"] = True
    base_cfg["export"]["pickle"]["do_export"] = True

    if base_cfg["export"].get("prefix") is not None:
        raise typer.BadParameter(
            f"export.prefix is set to {base_cfg['export']['prefix']!r}. All runs would share one "
            "export folder and overwrite each other. Remove it from the configuration."
        )
    if base_cfg["export"].get("bundle_export"):
        logging.warning(
            "export.bundle_export is on: all runs are collected in a single series folder."
        )
    return base_cfg


def do_run(cfg: dict, export_path: str) -> str:
    """Run, export and visualize one model, and return its export folder name."""
    model = init_model(cfg=cfg)
    logging.info(f"{type(model).__name__} instance created.")
    model.run()
    logging.info("Model computations completed.")
    model.export()
    logging.info("Export completed.")
    model.visualize()
    logging.info("Visualization completed.")
    # run_path() is created lazily on export, so it is only available now
    return os.path.relpath(model.data_writer.run_path(), export_path)


def run_baseline(base_cfg: dict, material: str, export_path: str) -> str:
    """Run the no-CE baseline and return the export folder name of its pickle."""
    baseline_scenario = BASELINE_SCENARIO[material]
    logging.info("=" * 103)
    logging.info(f"=== Baseline run: CE={baseline_scenario!r}, trade='default' ===")

    cfg = copy.deepcopy(base_cfg)
    cfg["transience"]["transience_scenario"] = baseline_scenario
    cfg["transience"]["trade_scenario"] = "default"
    cfg["transience"]["baseline_pickle_path"] = None

    run_name = do_run(cfg, export_path)

    pickle_path = Path(export_path) / run_name / "model.pickle"
    if not pickle_path.is_file():
        raise RuntimeError(
            f"Baseline run did not write {pickle_path}. The fix_supply runs cannot proceed."
        )
    logging.info(f"Baseline available as {run_name!r}.")
    return run_name


def run_all(
    config_names: list[str],
    material: str,
    baseline: str | None,
    show_figs: bool,
    save_figs: bool,
):
    base_cfg = load_config(config_names, ModelNames(material))
    base_cfg = prepare_base_cfg(base_cfg, show_figs, save_figs)
    export_path = base_cfg["export"]["path"]

    if baseline is None:
        baseline = run_baseline(base_cfg, material, export_path)
    else:
        pickle_path = Path(export_path) / baseline / "model.pickle"
        if not pickle_path.is_file():
            raise typer.BadParameter(f"No baseline pickle found at {pickle_path}.")
        logging.info(f"Reusing baseline {baseline!r}.")

    ce_scenarios = CE_SCENARIOS[material]
    total = len(ce_scenarios) * len(TRADE_SCENARIOS)
    completed = []
    failed = []

    for i, ce_scenario in enumerate(ce_scenarios):
        for j, trade_scenario in enumerate(TRADE_SCENARIOS):
            run_num = i * len(TRADE_SCENARIOS) + j + 1
            logging.info("=" * 103)
            logging.info(
                f"=== Run {run_num}/{total}: CE={ce_scenario!r}, trade={trade_scenario!r} ==="
            )

            cfg = copy.deepcopy(base_cfg)
            cfg["transience"]["transience_scenario"] = ce_scenario
            cfg["transience"]["trade_scenario"] = trade_scenario
            cfg["transience"]["baseline_pickle_path"] = (
                None if trade_scenario == "default" else baseline
            )

            try:
                run_name = do_run(cfg, export_path)
                completed.append(run_name)
                logging.info(f"Completed run {run_num}/{total}: {run_name}")
            except Exception:
                logging.exception(f"Failed run {run_num}/{total} ({ce_scenario}, {trade_scenario})")
                failed.append((ce_scenario, trade_scenario))

    logging.info("=" * 103)
    logging.info(f"{len(completed)}/{total} run(s) exported to {export_path}:")
    for run_name in completed:
        logging.info(f"  {run_name}")

    if failed:
        logging.warning(f"{len(failed)} run(s) failed:")
        for ce, trade in failed:
            logging.warning(f"  CE={ce!r}, trade={trade!r}")
        raise typer.Exit(1)
    logging.info("All runs completed successfully.")


@app.command()
def main(
    material: Annotated[str, typer.Argument(help=f"Material to run: {' or '.join(CE_SCENARIOS)}.")],
    config_names: Annotated[
        list[str] | None,
        typer.Option("--config", help="Configuration name under config/. Repeat to stack."),
    ] = None,
    baseline: Annotated[
        str | None,
        typer.Option(
            "--baseline",
            help="Name of an existing baseline export folder to reuse instead of running the "
            "baseline scenario.",
        ),
    ] = None,
    show_figs: Annotated[
        bool, typer.Option("--show/--no-show", help="Open figures interactively.")
    ] = False,
    save_figs: Annotated[
        bool, typer.Option("--save/--no-save", help="Save figures to each run folder.")
    ] = True,
) -> None:
    """Run all TRANSIENCE CE x trade scenario combinations for one material."""
    load_dotenv()
    configure_logging()

    if material not in CE_SCENARIOS:
        raise typer.BadParameter(
            f"No TRANSIENCE scenarios defined for {material!r}. "
            f"Choose one of: {', '.join(CE_SCENARIOS)}."
        )
    if config_names is None:
        config_names = ["default"]
    elif not config_names:
        config_names = prompt_for_config_names()

    run_all(config_names, material, baseline, show_figs, save_figs)


if __name__ == "__main__":
    app()
