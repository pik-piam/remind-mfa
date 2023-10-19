from ODYM.odym.modules import dynamic_stock_model as dsm
from src.model.load_dsms import load_dsms
from src.tools.config import cfg


def load_econ_dsms(country_specific, p_st, p_0_st, recalculate):
    dsms = load_dsms(country_specific, recalculate)
    factor = (p_st / p_0_st) ** cfg.elasticity_steel
    for region_dsms in dsms:
        for category_dsms in region_dsms:
            for scenario_idx, scenario_dsm in enumerate(category_dsms):
                scenario_dsm.i[cfg.econ_base_year - cfg.start_year + 1:] *= factor[:, scenario_idx]
                new_scenarion_dsm = dsm.DynamicStockModel(t=scenario_dsm.t,
                                                          i=scenario_dsm.i,
                                                          lt=scenario_dsm.lt)
                new_scenarion_dsm.compute_s_c_inflow_driven()
                new_scenarion_dsm.compute_o_c_from_s_c()
                new_scenarion_dsm.compute_stock_total()
                new_scenarion_dsm.compute_outflow_total()
                new_scenarion_dsm.compute_stock_change()
                scenario_dsm.i = new_scenarion_dsm.i
                scenario_dsm.o = new_scenarion_dsm.o
                scenario_dsm.o_c = new_scenarion_dsm.o_c
                scenario_dsm.s = new_scenarion_dsm.s
                scenario_dsm.s_c = new_scenarion_dsm.s_c
    return dsms


def _test():
    load_econ_dsms(country_specific=False, p_st=10, p_0_st=5)


if __name__ == '__main__':
    _test()
