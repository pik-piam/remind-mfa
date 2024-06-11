from src.tools.config import cfg
from src.dsm.load_dsms import load_dsms
from src.tools.visualize import visualize_mfa_sankey
from src.tools.export import export_to_dict
from src.model_definitions.plastics import PlasticsMFASystem


def load_simson_mfa():

    mfa = init_mfa()
    dsms = load_dsms(mfa)
    mfa.compute(dsms)

    return mfa


def init_mfa():
    if cfg.model_class == 'plastics':
        mfa = PlasticsMFASystem()
    else:
        raise ValueError(f"Model class {cfg.model_class} not supported.")
    return mfa


if __name__ == "__main__":
    mfa = load_simson_mfa()
    if cfg.do_visualize['sankey']:
        visualize_mfa_sankey(mfa)
    export_to_dict(mfa, 'data/output/mfa.pickle')
