import numpy as np
from ODYM.odym.modules import dynamic_stock_model as dsm  # import the dynamic stock model library
from src.tools.config import cfg
from src.read_data.load_data import load_stocks, load_lifetimes, load_trade
from src.tools.tools import get_np_from_df


def get_trade_factors():
    df_use, df_production, df_scrap_imports, df_scrap_exports = load_trade(country_specific=False)

    np_trade_factor = _calc_trade_factor(df_use, df_production, df_production)
    np_scrap_trade_factor = _calc_trade_factor(df_scrap_imports, df_scrap_exports, df_production)

    print('yeah')
    print(np_trade_factor.shape)

    return np_trade_factor, np_scrap_trade_factor


def balance_trade(trade_factor, use):
    trade = trade_factor * use


def _calc_trade_factor(df_add, df_sub, df_div):
    df_trade = df_add.sub(df_sub, fill_value=0)
    df_trade_factor = df_trade.div(df_div, fill_value=1)
    np_trade_factor = get_np_from_df(df_trade_factor, data_split_into_categories=False)
    return np_trade_factor


def get_dsm_data(stock_data):
    mean, std_dev = load_lifetimes()
    dsms = [_create_dsm(stocks, mean[i], std_dev[i]) for i, stocks in enumerate(stock_data)]
    stocks = np.array([dsm.s for dsm in dsms]).transpose()
    inflows = np.array([dsm.i for dsm in dsms]).transpose()
    outflows = np.array([dsm.o for dsm in dsms]).transpose()

    return stocks, inflows, outflows


def _create_dsm(stocks, lifetime, st_dev):
    time = np.array(range(cfg.n_years))
    steel_stock_dsm = dsm.DynamicStockModel(t=time,
                                            s=stocks,
                                            lt={'Type': 'Normal', 'Mean': [lifetime],
                                                'StdDev': [st_dev]})

    steel_stock_dsm.compute_stock_driven_model()
    steel_stock_dsm.compute_outflow_total()
    steel_stock_dsm.compute_stock_change()

    return steel_stock_dsm


def _check_steel_stock_dsm(steel_stock_dsm):
    balance = steel_stock_dsm.check_stock_balance()
    balance = np.abs(balance).sum()
    if balance > 1:  # 1 tonne accuracy
        raise RuntimeError("Stock balance for dynamic stock model is too high: " + str(balance))
    elif balance > 0.001:
        print("Stock balance for model dynamic stock model is noteworthy: " + str(balance))


def _test_dynamic_models():
    """
    Recalculates dynamic stock models from steel and population data for all REMIND regions.
    Both datasets need to be complete, so a total needs to be available for all years past and future
    (1900-2100) and for steel also for the respective using_categories. Additionally, lifetime (and it's SD)
    values are used to calculate outflow from steel stock.
    :return: dict[region][category]=dynamic_stock_model
    """
    df_stocks = load_stocks(country_specific=False, per_capita=True)
    stocks_data = get_np_from_df(df_stocks, data_split_into_categories=True)
    for data in stocks_data:
        get_dsm_data(data)
    print('DSM test successful.')


if __name__ == '__main__':
    _test_dynamic_models()
