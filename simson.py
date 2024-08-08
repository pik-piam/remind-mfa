import logging
import yaml

from sodym.classes.data_reader import JakobsDataReader
from sodym.classes.mfa_system import MFASystem
from sodym.tools.visualize import visualize_mfa_sankey
from sodym.tools.export import export

from src.model_definitions.plastics import PlasticsMFASystem
from src.model_definitions.steel import SteelMFASystem
from src.model_extensions.custom_visualization import visualize_production


allowed_models = {
    'plastics': PlasticsMFASystem,
    'steel': SteelMFASystem,
}


def get_model_config(filename):
    with open(filename, 'r') as stream:
        data = yaml.safe_load(stream)
    return {k: v for k, v in data.items()}


def init_mfa(model_name: str) -> MFASystem:
    """
    Choose MFA subclass and return an initialized instance.
    """
    if model_name not in allowed_models:
        raise ValueError(f"Model class {model_name} not supported.")

    cfg = get_model_config(f'config/{model_name}.yml')
    data_reader = JakobsDataReader(input_data_path=cfg['input_data_path'])
    mfa = allowed_models[model_name](data_reader=data_reader, model_cfg=cfg['model_customization'])
    return mfa


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    mfa = init_mfa(model_name='plastics')
    logging.info(f'{type(mfa).__name__} instance created.')
    mfa.compute()
    logging.info('Model computations completed.')

    visualize_mfa_sankey(mfa)
    visualize_production(mfa)
    export(mfa)
