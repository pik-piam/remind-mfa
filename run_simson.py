import logging
import yaml
import flodym as fd

from simson.common.common_cfg import CommonCfg
from simson.plastics.plastics_model import PlasticsModel
from simson.steel.steel_model import SteelModel
from simson.cement.cement_model import CementModel


allowed_models = {
    "plastics": PlasticsModel,
    "steel": SteelModel,
    "cement": CementModel,
}
configurations = {
    "plastics": CommonCfg,
    "steel": CommonCfg,
    "cement": CommonCfg,
}


def get_model_config(filename):
    with open(filename, "r") as stream:
        data = yaml.safe_load(stream)
    return {k: v for k, v in data.items()}


def init_mfa(cfg: dict) -> fd.MFASystem:
    """Choose MFA subclass and return an initialized instance."""
    model_name = cfg["model_class"]
    if model_name not in allowed_models:
        raise ValueError(f"Model class {model_name} not supported.")

    cfg = configurations[model_name](**cfg)
    mfa = allowed_models[model_name](cfg=cfg)
    return mfa


def recalculate_mfa(model_config):
    mfa = init_mfa(cfg=model_config)
    logging.info(f"{type(mfa).__name__} instance created.")
    mfa.run()
    logging.info("Model computations completed.")


def visualize_mfa(model_config):
    # TODO: Implement load of MFA to visualize without recalculating
    pass


def run_simson(cfg_file: str):
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    model_config = get_model_config(cfg_file)
    recalculate_mfa(model_config)


if __name__ == "__main__":
    cfg_file = "config/plastics.yml"
    run_simson(cfg_file)
