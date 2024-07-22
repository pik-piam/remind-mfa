from src.tools.config import cfg
from src.model_definitions.plastics import PlasticsMFASystem


def init_mfa():
    """
    Choose MFA subclass from config and return an initialized instance.
    """
    if cfg.model_class == 'plastics':
        mfa = PlasticsMFASystem()
    else:
        raise ValueError(f"Model class {cfg.model_class} not supported.")
    return mfa
