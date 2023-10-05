import numpy as np
from src.read_data.load_data import load_trade_factor, load_scrap_trade_factor
from src.tools.tools import get_np_from_df


def get_all_trade(country_specific, dsms):
    model_use = _get_model_use(dsms)
    trade = _get_trade(country_specific, model_use)
    scrap_trade = _get_scrap_trade(country_specific, model_use, trade)

    return trade, scrap_trade


def _get_trade(country_specific, model_use):
    df_trade_factor = load_trade_factor(country_specific=country_specific)
    trade_factor = get_np_from_df(df_trade_factor, data_split_into_categories=False)
    trade = model_use * trade_factor
    trade = balance_trade(trade)
    return trade


def _get_scrap_trade(country_specific, trade, model_use):
    df_scrap_trade_factor = load_scrap_trade_factor(country_specific=country_specific)
    scrap_trade_factor = get_np_from_df(df_scrap_trade_factor, data_split_into_categories=False)
    scrap_trade = (model_use - trade) * scrap_trade_factor
    scrap_trade = balance_trade(scrap_trade)
    return scrap_trade


def balance_trade(trade):
    net_trade = trade.sum(axis=1)
    sum_trade = np.abs(trade).sum(axis=1)
    balancing_factor = net_trade / sum_trade
    balancing_factor = np.expand_dims(balancing_factor, axis=1)
    balanced_trade = trade * (1 - np.sign(trade) * balancing_factor)

    return balanced_trade


def _get_model_use(dsms):
    inflows = np.array(
        [[[dsm_scenario.i for dsm_scenario in dsms_category] for dsms_category in dsms_region] for dsms_region in dsms])
    model_use = inflows.sum(axis=1)
    return np.swapaxes(model_use, 0, 1)


def _test():
    from src.model.load_dsms import load_dsms
    dsms = load_dsms(country_specific=False)
    trade, scrap_trade = get_all_trade(country_specific=False, dsms=dsms)
    trade_balance = trade.sum(axis=0).sum(axis=0)
    scrap_trade_balance = scrap_trade.sum(axis=0).sum(axis=0)
    if trade_balance < 0.001:
        print('Trade is loaded and balanced.')
    if scrap_trade_balance < 0.001:
        print('Scrap trade_all_areas is loaded and balanced.')


if __name__ == '__main__':
    _test()
