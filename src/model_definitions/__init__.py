from src.tools.config import cfg
from src.model_definitions.plastics import PlasticsMFASystem
from src.model_definitions.steel import SteelMFASystem


def init_mfa():
    """
    Choose MFA subclass from config and return an initialized instance.
    """
    if cfg.model_class == 'plastics':
        mfa = PlasticsMFASystem()
    elif cfg.model_class == 'steel':
        mfa = SteelMFASystem()
    else:
        raise ValueError(f"Model class {cfg.model_class} not supported.")
    return mfa
