from remind_mfa.common.config_loader import load_config
from remind_mfa.common.helpers import ModelNames, init_model


import logging


def run_batch(config_names: list[str], models: list[ModelNames]) -> None:
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
        model.visualize()
        logging.info("Visualization completed.")
