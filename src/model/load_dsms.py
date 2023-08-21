import os
import pickle
import numpy as np
from ODYM.odym.modules import dynamic_stock_model as dsm  # import the dynamic stock model library
from src.tools.config import cfg
from src.model.model_tools import get_np_from_df
from src.read_data.load_data import load_stocks, load_lifetimes


def load_dsms(country_specific):
    file_name_end = '_countries' if country_specific else f'_{cfg.region_data_source}_regions'
    file_name = f"dsms_{file_name_end}.p"
    file_path = os.path.join(cfg.data_path, 'models', file_name)
    if os.path.exists(file_path) and not cfg.recalculate_data:
        dsms = pickle.load(open(file_path, "rb"))
        return dsms
    else:
        dsms = _get_dsms(country_specific)
        pickle.dump(dsms, open(file_path, "wb"))
        return dsms


def _get_dsms(country_specific):
    df_stocks = load_stocks(country_specific=country_specific, per_capita=True)
    area_names = list(df_stocks.index.get_level_values(0).unique())
    stocks_data = get_np_from_df(df_stocks, data_split_into_categories=True)
    mean, std_dev = load_lifetimes()
    dsms = [[_create_dsm(stocks, mean[i], std_dev[i]) for i, stocks in enumerate(stocks_data[area_idx])] for area_idx, area_name in enumerate(area_names)]
    return dsms

def _create_dsm(stocks, lifetime, st_dev):
    time = np.array(range(cfg.n_years))
    steel_stock_dsm = dsm.DynamicStockModel(t=time,
                                            s=stocks,
                                            lt={'Type': 'Normal', 'Mean': [lifetime],
                                                'StdDev': [st_dev]})

    steel_stock_dsm.compute_stock_driven_model()
    steel_stock_dsm.compute_outflow_total()
    steel_stock_dsm.compute_stock_change()
    check_steel_stock_dsm(steel_stock_dsm)

    return steel_stock_dsm


def check_steel_stock_dsm(steel_stock_dsm):
    balance = steel_stock_dsm.check_stock_balance()
    balance = np.abs(balance).sum()
    if balance > 1:  # 1 tonne accuracy
        raise RuntimeError("Stock balance for dynamic stock model is too high: " + str(balance))
    elif balance > 0.001:
        print("Stock balance for model dynamic stock model is noteworthy: " + str(balance))


def _test():
    dsms = load_dsms(False)
    print(dsms)


if __name__=='__main__':
    _test()

