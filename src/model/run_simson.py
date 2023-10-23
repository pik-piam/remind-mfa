from src.model.simson_base_model import create_base_model
from src.economic_model.simson_econ_model import create_economic_model
from src.tools.config import cfg

def run_simson(config_dict):
    cfg.customize(config_dict)
    model = create_economic_model(country_specific=False, recalculate_dsms=False) if cfg.do_model_economy \
        else create_base_model(country_specific=False,recalculate_dsms=True)
    return model


def _test():
    run_simson(cfg.__dict__)


if __name__=='__main__':
    _test()