import logging
from copy import deepcopy

from remind_mfa.common.config_loader import load_config, merge_config
from remind_mfa.common.helpers import ModelNames, init_model
from remind_mfa.common.scenarios import ALL_SCENARIOS, list_runnable_scenarios


def run_batch(
    config_names: list[str],
    models: list[ModelNames],
    scenarios: list[str] | None = None,
    bundle_export: bool | None = None,
) -> None:
    """Run every selected model in each of its scenarios.

    Args:
        config_names: Configuration layers to stack, in order.
        models: Models to run.
        scenarios: Scenario names, or `ALL_SCENARIOS`, overriding `model_switches.scenarios` of
            every model.
        bundle_export: If given, overrides `export.bundle_export` of every model.
    """
    config_tables = load_config(config_names)
    batch_overrides: dict = {}
    if scenarios is not None:
        batch_overrides["model_switches"] = {"scenarios": scenarios}
    if bundle_export is not None:
        batch_overrides["export"] = {"bundle_export": bundle_export}
    run_configs = [
        run_config
        for model_name in models
        for run_config in _expanded_run_configs(config_tables, model_name, batch_overrides)
    ]

    for run_config in run_configs:
        run_model(run_config)


def _expanded_run_configs(
    config_tables: dict, model_name: ModelNames, batch_overrides: dict
) -> list[dict]:
    """Return the configuration of the model for each scenario it runs.

    Args:
        config_tables: Merged configuration tables, see `load_config`.
        model_name: Model to configure.
        batch_overrides: Settings applying to all runs, in the layout of a model table.
    """
    # Overrides go into the model table, so they also win over model-specific layers.
    model_config = merge_config(
        config_tables, model_name, overrides={model_name.value: batch_overrides}
    )
    scenarios = model_config["model_switches"]["scenarios"]
    if ALL_SCENARIOS in scenarios:
        scenarios = list_runnable_scenarios(model_config["input"]["scenarios_path"])
    run_configs = []
    for scenario in dict.fromkeys(scenarios):
        run_config = deepcopy(model_config)
        run_config["model_switches"]["scenarios"] = [scenario]
        run_configs.append(run_config)
    return run_configs


def run_model(model_config: dict) -> None:
    """Initialize, run, export and visualize one model.

    Args:
        model_config: Validated configuration of the model, e.g. from `load_config`.
    """
    scenarios = ", ".join(model_config["model_switches"]["scenarios"])
    logging.info("=" * 103)
    logging.info(f"Starting {model_config['model']} {scenarios} run...")
    model = init_model(cfg=model_config)
    logging.info(f"{type(model).__name__} instance created.")
    model.run()
    logging.info("Model computations completed.")
    model.export()
    logging.info("Export completed.")
    model.visualize()
    logging.info("Visualization completed.")
