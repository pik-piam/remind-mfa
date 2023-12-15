import numpy as np
from src.calc_trade.calc_trade_tools import get_trade_category_percentages, \
    expand_trade_to_past_and_future, get_imports_and_exports_from_net_trade, get_trade_test_data, visualize_trade
from src.tools.tools import get_np_from_df
from src.read_data.load_data import load_scrap_trade_1971_2022


def get_scrap_trade(country_specific, scaler, available_scrap_by_category):
    scrap_trade_1971_2022 = _get_net_scrap_trade_1971_2022(country_specific)
    net_scrap_trade = expand_trade_to_past_and_future(scrap_trade_1971_2022,
                                                      scaler=scaler,
                                                      first_available_year=1971,
                                                      last_available_year=2022)

    scrap_imports, scrap_exports = _recalculate_scrap_trade_based_on_scrap_availability(net_scrap_trade,
                                                                                        available_scrap_by_category)
    scrap_imports, scrap_exports = _split_scrap_trade_into_waste_categories(scrap_imports,
                                                                            scrap_exports,
                                                                            available_scrap_by_category)
    return scrap_imports, scrap_exports


def _get_net_scrap_trade_1971_2022(country_specific):
    df_scrap_imports, df_scrap_exports = load_scrap_trade_1971_2022(country_specific=country_specific)
    scrap_imports = get_np_from_df(df_scrap_imports, data_split_into_categories=False)
    scrap_exports = get_np_from_df(df_scrap_exports, data_split_into_categories=False)

    net_scrap_trade_1971_2022 = scrap_imports - scrap_exports
    net_scrap_trade_1971_2022 = net_scrap_trade_1971_2022.transpose()

    return net_scrap_trade_1971_2022


def _recalculate_scrap_trade_based_on_scrap_availability(projected_scrap_trade, available_scrap_by_category):
    """
    Reduce projected scrap exports to maximum available scrap, and reduce all scrap imports by a factor so that
    scrap imports equal scrap exports again (revised scrap balance).

    :param projected_scrap_trade:
    :param available_scrap_by_category:
    :return:
    """
    scrap_imports, scrap_exports = get_imports_and_exports_from_net_trade(projected_scrap_trade)

    available_scrap = np.sum(available_scrap_by_category, axis=2)

    overload = np.maximum(scrap_exports - available_scrap, 0)
    overload = np.sum(overload, axis=1)
    global_scrap_imports = np.sum(scrap_imports, axis=1)
    factor = (global_scrap_imports - overload) / global_scrap_imports

    scrap_imports = np.einsum('trs,ts->trs', scrap_imports, factor)
    scrap_exports = np.minimum(scrap_exports, available_scrap)

    return scrap_imports, scrap_exports


def _split_scrap_trade_into_waste_categories(scrap_imports, scrap_exports, available_scrap_by_category):
    """
    Exports are split according to share of waste category in exporting country. Imports are split according
    to share of waste category of total exports.
    :param scrap_imports:
    :param scrap_exports:
    :param available_scrap_by_category:
    :return:
    """

    available_scrap_waste_share = get_trade_category_percentages(available_scrap_by_category, category_axis=2)

    scrap_exports = np.einsum('trs,trws->trws', scrap_exports, available_scrap_waste_share)

    global_exports = np.sum(scrap_exports, axis=1)
    scrap_exports_waste_share = get_trade_category_percentages(global_exports, category_axis=1)

    scrap_imports = np.einsum('trs,tws->trws', scrap_imports, scrap_exports_waste_share)

    return scrap_imports, scrap_exports


def _test():
    country_specific = False
    production, demand, available_scrap_by_category = get_trade_test_data(country_specific)
    scrap_imports, scrap_exports = get_scrap_trade(country_specific=country_specific,
                                                   scaler=production,
                                                   available_scrap_by_category=available_scrap_by_category)
    scrap_trade = scrap_imports - scrap_exports

    print(f'Scrap trade is loaded with shape: {scrap_trade.shape}')
    visualize_trade(scrap_trade, steel_type='scrap')


if __name__ == '__main__':
    _test()
