import logging
import yaml

from sodym.classes.data_reader import JakobsDataReader
from sodym.classes.mfa_system import MFASystem
from sodym.export.data_writer import DataWriter

from src.model_definitions.plastics import PlasticsMFASystem
from src.model_definitions.steel import SteelMFASystem
from src.model_extensions.custom_visualization import CustomDataVisualizer


allowed_models = {
    'plastics': PlasticsMFASystem,
    'steel': SteelMFASystem,
}


def get_model_config(filename):
    with open(filename, 'r') as stream:
        data = yaml.safe_load(stream)
    return {k: v for k, v in data.items()}


def init_mfa(cfg: dict) -> MFASystem:
    """
    Choose MFA subclass and return an initialized instance.
    """
    model_name = cfg['model_class']
    if model_name not in allowed_models:
        raise ValueError(f"Model class {model_name} not supported.")

    data_reader = JakobsDataReader(input_data_path=cfg['input_data_path'])
    mfa = allowed_models[model_name](data_reader=data_reader, model_cfg=cfg['model_customization'])
    return mfa


def define_data_writer(cfg: dict, mfa: MFASystem) -> DataWriter:
    data_writer = CustomDataVisualizer(mfa=mfa, **cfg)
    return data_writer


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    cfg_file = 'config/plastics.yml'
    model_config = get_model_config(cfg_file)
    mfa = init_mfa(cfg=model_config)
    logging.info(f'{type(mfa).__name__} instance created.')
    mfa.compute()
    logging.info('Model computations completed.')
    dw = define_data_writer(cfg=model_config, mfa=mfa)
    dw.export()
    dw.visualize_results()
