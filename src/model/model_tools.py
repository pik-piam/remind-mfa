import numpy as np
from src.tools.tools import get_np_from_df
from src.read_data.load_data import load_stocks


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


def get_stock_data_country_specific_areas(country_specific):
    df_stocks = load_stocks(country_specific=country_specific, per_capita=True)
    areas = list(df_stocks.index.unique(level=0))

    return areas


if __name__ == '__main__':
    print('test')
