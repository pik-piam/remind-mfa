from simulation.src.load_excel_dicts import load_excel_dicts
from simulation.src.load_yaml_dicts import load_yaml_dicts
from src.tools.config import cfg
from src.model.simson_model import load_simson_model
from src.economic_model.simson_econ_model import load_simson_econ_model

def run_simulations():
    dicts = _load_dicts()
    for dict in dicts:
        _run_and_save_simulation(dict)

def _run_and_save_simulation(dict):
    cfg.customize(dict)
    print(cfg.simulation_name)
    model = load_simson_econ_model(recalculate=True) if cfg.do_model_economy else load_simson_model(recalculate=True)
    # TODO save model



def _load_dicts():
    return load_excel_dicts() + load_yaml_dicts()


if __name__=='__main__':
    run_simulations()