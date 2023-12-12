import os
import pickle
import numpy as np
from src.odym_extension.MultiDim_DynamicStockModel import MultiDim_DynamicStockModel
from src.tools.config import cfg
from src.model.model_tools import calc_change_timeline
from src.predict.calc_steel_stocks import get_np_steel_stocks_with_prediction
from src.read_data.load_data import load_lifetimes, load_region_names_list


def load_dsms(country_specific, recalculate=cfg.recalculate_data):
    file_name_end = '_countries' if country_specific else f'_{cfg.region_data_source}_regions'
    file_name = f"dsms_{file_name_end}.p"
    file_path = os.path.join(cfg.data_path, 'models', file_name)
    if os.path.exists(file_path) and not recalculate:
        dsms = pickle.load(open(file_path, "rb"))
        return dsms
    else:
        dsms = _get_dsms(country_specific)
        pickle.dump(dsms, open(file_path, "wb"))
        return dsms


def _get_dsms(country_specific):
    stocks_data = get_np_steel_stocks_with_prediction(country_specific=country_specific,
                                                      get_per_capita=True)
    area_names = load_region_names_list()
    mean, std_dev = load_lifetimes()

    if cfg.do_change_inflow:
        inflow_change_timeline = calc_change_timeline(cfg.inflow_change_factor, cfg.inflow_change_base_year)

    dsms = [[[_create_dsm(stocks_data[:, area_idx, cat_idx, scenario_idx],
                          mean[cat_idx], std_dev[cat_idx],
                          inflow_change_timeline[:, cat_idx, scenario_idx] if cfg.do_change_inflow else None)
              for scenario_idx in range(cfg.n_scenarios)]
             for cat_idx in range(cfg.n_use_categories)]
            for area_idx, area_name in enumerate(area_names)]
    return dsms


def _create_dsm(stocks, lifetime, st_dev, inflow_change=None):
    time = np.array(range(cfg.n_years))
    steel_stock_dsm = MultiDim_DynamicStockModel(t=time,
                                                 s=stocks,
                                                 lt={'Type': 'Normal', 'Mean': [lifetime],
                                                     'StdDev': [st_dev]})

    steel_stock_dsm.compute_all_stock_driven()

    if inflow_change is not None:
        inflows = steel_stock_dsm.i
        inflows = np.einsum('t,t->t', inflows, inflow_change)  # TODO just normal multiplication?
        steel_stock_dsm = MultiDim_DynamicStockModel(t=time,
                                                     i=inflows,
                                                     lt={'Type': 'Normal', 'Mean': [lifetime],
                                                         'StdDev': [st_dev]})
        steel_stock_dsm.compute_all_inflow_driven()

    return steel_stock_dsm


def _test():
    dsms = load_dsms(country_specific=False, recalculate=True)
    print(dsms)


if __name__ == '__main__':
    _test()
