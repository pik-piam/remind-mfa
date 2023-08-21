import numpy as np
from src.tools.tools import get_np_from_df


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
