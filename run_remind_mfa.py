import logging
import yaml
import sys

from remind_mfa.common.helpers import ModelNames
from remind_mfa.common.common_model import CommonModel
from remind_mfa.cement.cement_model import CementModel
from remind_mfa.plastics.plastics_model import PlasticsModel
from remind_mfa.steel.steel_model import SteelModel


def run_remind_mfa(cfg_file: str):
    configure_logger()
    model_config = read_model_config(cfg_file)
    model = init_model(cfg=model_config)
    logging.info(f"{type(model).__name__} instance created.")
    model.run()
    logging.info("Model computations completed.")
    model.export()
    logging.info("Export completed.")
    model.visualize()
    logging.info("Visualization completed.")


def configure_logger():
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def read_model_config(filename):
    with open(filename, "r") as stream:
        data = yaml.safe_load(stream)
    return {k: v for k, v in data.items()}


def init_model(cfg: dict) -> CommonModel:
    """Choose MFA subclass and return an initialized instance."""

    if "model" not in cfg:
        raise ValueError("'model' must be given.")
    model_name = ModelNames(cfg["model"])

    models = {
        ModelNames.PLASTICS: PlasticsModel,
        ModelNames.STEEL: SteelModel,
        ModelNames.CEMENT: CementModel,
    }
    return models[model_name](cfg=cfg)


if __name__ == "__main__":
    try:
        cfg_file = sys.argv[1]
    except IndexError:
        raise ValueError("Please provide a configuration file as an argument.")
    run_remind_mfa(cfg_file)
