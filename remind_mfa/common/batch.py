from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames, init_model


import logging
from pathlib import Path


def run_batch(config_names: list[str], models: list[ModelNames]) -> list[Path]:
    """Run and export the models one after the other.

    Args:
        config_names: The configuration layers, in order.
        models: The models to run.

    Returns:
        The run folders of the models that exported a pickle.
    """
    run_paths = []
    for model_name in models:
        logging.info("=" * 103)
        logging.info(f"Starting {model_name.value} run...")
        model_config = load_config(config_names, model_name)
        model = init_model(cfg=model_config)
        logging.info(f"{type(model).__name__} instance created.")
        model.run()
        logging.info("Model computations completed.")
        model.export()
        logging.info("Export completed.")
        export_cfg = model.data_writer.cfg
        if export_cfg.do_export and export_cfg.pickle.do_export:
            run_paths.append(Path(model.data_writer.run_path()))
    return run_paths
