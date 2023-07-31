import numpy as np
from ODYM.odym.modules import dynamic_stock_model as dsm  # import the dynamic stock model library
from src.tools.config import cfg
from src.read_data.load_data import load_stocks, load_lifetimes, load_trade
from src.tools.tools import get_np_from_df


def get_trade(use_inflows):
    return


def get_trade_factors():
    df_use, df_production, df_scrap_imports, df_scrap_exports = load_trade(country_specific=False)

    np_trade_factor = _calc_trade_factor(df_use, df_production, df_production)
    np_scrap_trade_factor = _calc_trade_factor(df_scrap_imports, df_scrap_exports, df_production)

    return np_trade_factor, np_scrap_trade_factor


def balance_trade(trade_factor, use):
    trade = trade_factor * use



def _calc_trade_factor(df_add, df_sub, df_div):
    df_trade = df_add.sub(df_sub, fill_value=0)
    df_trade_factor = df_trade.div(df_div, fill_value=1)
    np_trade_factor = get_np_from_df(df_trade_factor, data_split_into_categories=False)
    return np_trade_factor


def get_dsm_data(dsms_by_category):
    stocks = np.array([dsm.s for dsm in dsms_by_category]).transpose()
    inflows = np.array([dsm.i for dsm in dsms_by_category]).transpose()
    outflows = np.array([dsm.o for dsm in dsms_by_category]).transpose()

    return stocks, inflows, outflows



if __name__ == '__main__':
    print('test')
