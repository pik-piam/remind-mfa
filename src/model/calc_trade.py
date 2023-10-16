import numpy as np
from src.read_data.load_data import load_trade_factor, load_scrap_trade_factor
from src.tools.tools import get_np_from_df


def get_trade(country_specific, fabrication_demand):
    df_trade_factor = load_trade_factor(country_specific=country_specific)
    trade_factor = get_np_from_df(df_trade_factor, data_split_into_categories=False)
    trade = fabrication_demand * trade_factor
    trade = balance_trade(trade)
    imports = np.maximum(trade, 0).transpose()
    exports = -np.minimum(trade, 0).transpose()
    return imports, exports


def get_scrap_trade(country_specific, production, available_scrap_by_category):
    df_scrap_trade_factor = load_scrap_trade_factor(country_specific=country_specific)
    scrap_trade_factor = get_np_from_df(df_scrap_trade_factor, data_split_into_categories=False)
    scrap_trade = production * scrap_trade_factor
    scrap_trade = balance_trade(scrap_trade)
    scrap_imports, scrap_exports =  _recalculate_scrap_trade_based_on_scrap_availability(scrap_trade,
                                                                                         available_scrap_by_category)
    return scrap_imports, scrap_exports


def _recalculate_scrap_trade_based_on_scrap_availability(projected_scrap_trade, available_scrap_by_category):
    available_scrap = np.sum(available_scrap_by_category, axis=2)
    projected_scrap_trade = projected_scrap_trade.transpose()

    projected_exports = np.minimum(0, projected_scrap_trade)

    projected_exports = np.abs(projected_exports)
    factor = np.divide(available_scrap, projected_exports, out=np.ones(available_scrap.shape) * np.inf,
                       where=projected_exports != 0)
    factor = np.min(factor, axis=1)
    factor = np.expand_dims(factor, axis=1)
    factor = factor * 0.999  # avoid slightly negative numbers
    new_trade = projected_scrap_trade * factor

    total_scrap_imports = np.maximum(new_trade, 0)
    total_scrap_exports = np.minimum(new_trade, 0)

    available_scrap_expanded = np.expand_dims(available_scrap, axis=2)
    eol_by_scrap_category_percent = np.divide(available_scrap_by_category, available_scrap_expanded,
                                              out=np.zeros_like(available_scrap_by_category),
                                              where=available_scrap_expanded != 0)
    scrap_exports = eol_by_scrap_category_percent * np.expand_dims(total_scrap_exports, axis=2)

    scrap_exports_sum_areas = np.sum(scrap_exports, axis=1)
    scrap_exports_sum_categories = np.sum(scrap_exports_sum_areas, axis=1)
    scrap_exports_percent_by_category = scrap_exports_sum_areas / np.expand_dims(scrap_exports_sum_categories, axis=1)
    scrap_exports_percent_by_category = np.expand_dims(scrap_exports_percent_by_category, axis=1)
    total_scrap_imports = np.expand_dims(total_scrap_imports, axis=2)
    scrap_imports = total_scrap_imports * scrap_exports_percent_by_category

    return scrap_imports, -scrap_exports


def balance_trade(trade):
    net_trade = trade.sum(axis=1)
    sum_trade = np.abs(trade).sum(axis=1)
    balancing_factor = net_trade / sum_trade
    balancing_factor = np.expand_dims(balancing_factor, axis=1)
    balanced_trade = trade * (1 - np.sign(trade) * balancing_factor)

    return balanced_trade


def _test():
    import os
    import csv
    from src.tools.config import cfg
    from src.model.load_dsms import load_dsms
    from src.model.model_tools import get_dsm_data

    cullen_path = os.path.join(cfg.data_path, 'original', 'cullen', 'cullen_fabrication_yield_matrix.csv')
    with open(cullen_path) as csv_file:
        cullen_reader = csv.reader(csv_file, delimiter=',')
        cullen_list = list(cullen_reader)
        fabrication_yield = [float(line[1]) for line in cullen_list[1:]]

    dsms = load_dsms(country_specific=False)
    stocks, inflows, outflows = get_dsm_data(dsms)
    inverse_fabrication_yield = 1 / fabrication_yield
    production = np.einsum('trgs,g->trgs', inflows, inverse_fabrication_yield)
    trade, scrap_trade = get_all_trade(country_specific=False, fabrication_demand=production.transpose())

    trade_balance = trade.sum(axis=0).sum(axis=0)
    scrap_trade_balance = scrap_trade.sum(axis=0).sum(axis=0)
    if trade_balance < 0.001:
        print('Trade is loaded and balanced.')
    if scrap_trade_balance < 0.001:
        print('Scrap trade_all_areas is loaded and balanced.')


if __name__ == '__main__':
    _test()
