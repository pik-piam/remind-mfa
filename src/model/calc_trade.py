import numpy as np
from src.read_data.load_data import load_production, \
    load_scrap_trade_1971_2022, load_use_1970_2021, load_indirect_trade_2001_2019
from src.tools.tools import get_np_from_df
from src.tools.config import cfg


def get_trade(country_specific, scaler):
    net_trade_1970_2021 = _get_net_trade_1970_2021(country_specific)
    net_trade = _expand_trade_to_past_and_future(net_trade_1970_2021,
                                                 scaler=scaler,
                                                 first_available_year=1970,
                                                 last_available_year=2021)

    imports, exports = _get_imports_and_exports_from_net_trade(net_trade)

    return imports, exports


def get_scrap_trade(country_specific, scaler, available_scrap_by_category):
    scrap_trade_1971_2022 = _get_net_scrap_trade_1971_2022(country_specific)
    net_scrap_trade = _expand_trade_to_past_and_future(scrap_trade_1971_2022,
                                                       scaler=scaler,
                                                       first_available_year=1971,
                                                       last_available_year=2022)

    scrap_imports, scrap_exports = _recalculate_scrap_trade_based_on_scrap_availability(net_scrap_trade,
                                                                                        available_scrap_by_category)
    scrap_imports, scrap_exports = _split_scrap_trade_into_waste_categories(scrap_imports,
                                                                            scrap_exports,
                                                                            available_scrap_by_category)
    return scrap_imports, scrap_exports


def get_indirect_trade(country_specific, scaler, inflows, outflows):
    net_indirect_trade_2001_2019 = _get_net_indirect_trade_2001_2019(country_specific)
    net_indirect_trade = _expand_trade_to_past_and_future(net_indirect_trade_2001_2019,
                                                          scaler=scaler,
                                                          first_available_year=2001,
                                                          last_available_year=2019)
    indirect_imports, indirect_exports = _get_imports_and_exports_from_net_trade(net_indirect_trade)
    indirect_imports, indirect_exports = _split_indirect_trade_into_use_categories(indirect_imports,
                                                                                   indirect_exports,
                                                                                   inflows, outflows)
    return indirect_imports, indirect_exports


def _get_imports_and_exports_from_net_trade(net_trade):
    imports = np.maximum(net_trade, 0)
    exports = np.minimum(net_trade, 0)
    exports[exports<0] *= -1
    return imports, exports



def _expand_trade_to_past_and_future(trade, scaler, first_available_year, last_available_year):
    def _scale_trade_via_trade_factor(do_before):
        if do_before:
            scaler_data = scaler[:start_idx]
            trade_factor = trade[0] / scaler[start_idx]
        else:
            scaler_data = scaler[end_idx+1:]
            trade_factor = trade[-1] / scaler[end_idx]
        new_trade_data = np.einsum('trs,rs->trs', scaler_data, trade_factor)
        new_trade_data = balance_trade(new_trade_data)

        return new_trade_data

    # broadcast trade to five scenarios
    trade = np.expand_dims(trade, axis=2)
    trade = np.broadcast_to(trade, trade.shape[:2]+(len(cfg.scenarios),))

    # get start and end idx
    start_idx = first_available_year - cfg.start_year
    end_idx = last_available_year - cfg.start_year

    # calc data before and after available data according to scaler
    before_trade = _scale_trade_via_trade_factor(do_before=True)
    after_trade = _scale_trade_via_trade_factor(do_before=False)

    # concatenate pieces
    trade = np.concatenate((before_trade, trade, after_trade), axis=0)

    return trade


def _get_net_indirect_trade_2001_2019(country_specific):
    df_indirect_imports, df_indirect_exports = load_indirect_trade_2001_2019(country_specific=country_specific)
    indirect_imports = get_np_from_df(df_indirect_imports, data_split_into_categories=False)
    indirect_exports = get_np_from_df(df_indirect_exports, data_split_into_categories=False)

    net_indirect_trade = indirect_imports - indirect_exports
    net_indirect_trade = net_indirect_trade.transpose()

    return net_indirect_trade


def _get_net_trade_1970_2021(country_specific):
    df_use = load_use_1970_2021(country_specific=country_specific)
    df_production = load_production(country_specific=country_specific)

    use_1970_2021 = get_np_from_df(df_use, data_split_into_categories=False)
    production_1900_2022 = get_np_from_df(df_production, data_split_into_categories=False)
    production_1970_2021 = production_1900_2022[:, 70:122]

    net_trade_1970_2021 = use_1970_2021 - production_1970_2021
    net_trade_1970_2021 = net_trade_1970_2021.transpose()

    return net_trade_1970_2021


def _get_net_scrap_trade_1971_2022(country_specific):
    df_scrap_imports, df_scrap_exports = load_scrap_trade_1971_2022(country_specific=country_specific)
    scrap_imports = get_np_from_df(df_scrap_imports, data_split_into_categories=False)
    scrap_exports = get_np_from_df(df_scrap_exports, data_split_into_categories=False)

    net_scrap_trade_1971_2022 = scrap_imports - scrap_exports  # TODO: what if different countries
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
    scrap_imports, scrap_exports = _get_imports_and_exports_from_net_trade(projected_scrap_trade)

    available_scrap = np.sum(available_scrap_by_category, axis=2)

    overload = np.maximum(scrap_exports-available_scrap, 0)
    overload = np.sum(overload, axis=1)
    global_scrap_imports = np.sum(scrap_imports, axis=1)
    factor = (global_scrap_imports - overload) / global_scrap_imports

    scrap_imports = np.einsum('trs,ts->trs', scrap_imports, factor)
    scrap_exports = np.minimum(scrap_exports, available_scrap)

    return scrap_imports, scrap_exports


def _get_trade_category_percentages(trade_data, category_axis):
    """
    Calculate the percentages of total trade along a category axis
    (e.g. Recycling with Construction & Development etc. or Use with Transport, Machinery etc.).
    :param trade_data:
    :param category_axis:
    :return:
    """
    trade_sum = trade_data.sum(axis=category_axis)
    trade_sum = np.expand_dims(trade_sum, axis=category_axis)
    category_share = np.divide(trade_data, trade_sum,
                            out=np.zeros_like(trade_data),
                            where=trade_sum!=0)
    return category_share


def _split_indirect_trade_into_use_categories(indirect_imports, indirect_exports, inflows, outflows):
    inflow_category_share = _get_trade_category_percentages(inflows, category_axis=2)
    indirect_imports = np.einsum('trs,trgs->trgs', indirect_imports, inflow_category_share)

    outflow_category_share = _get_trade_category_percentages(outflows, category_axis=2)
    indirect_exports = np.einsum('trs,trgs->trgs', indirect_exports, outflow_category_share)
    return indirect_imports, indirect_exports

def _split_scrap_trade_into_waste_categories(scrap_imports, scrap_exports, available_scrap_by_category):
    """
    Exports are split according to share of waste category in exporting country. Imports are split according
    to share of waste category of total exports.
    :param scrap_imports:
    :param scrap_exports:
    :param available_scrap_by_category:
    :return:
    """

    available_scrap_waste_share = _get_trade_category_percentages(available_scrap_by_category, category_axis=2)

    scrap_exports = np.einsum('trs,trws->trws', scrap_exports, available_scrap_waste_share)

    global_exports = np.sum(scrap_exports, axis=1)
    scrap_exports_waste_share = _get_trade_category_percentages(global_exports, category_axis=1)

    scrap_imports = np.einsum('trs,tws->trws', scrap_imports, scrap_exports_waste_share)

    return scrap_imports, scrap_exports



def balance_trade(trade):
    net_trade = trade.sum(axis=1)
    sum_trade = np.abs(trade).sum(axis=1)
    balancing_factor = net_trade / sum_trade
    balancing_factor = np.expand_dims(balancing_factor, axis=1)
    balanced_trade = trade * (1 - np.sign(trade) * balancing_factor)

    return balanced_trade


def _test():
    from src.model.simson_base_model import load_simson_base_model, \
        FABR_PID, USE_PID, BOF_PID, FORM_PID, EAF_PID, SCRAP_PID

    country_specific = False
    model = load_simson_base_model(country_specific=country_specific)
    demand = np.sum(model.FlowDict['F_' + str(FABR_PID) + '_' + str(USE_PID)].Values[:,0], axis=2)
    bof_production = model.FlowDict['F_' + str(BOF_PID) + '_' + str(FORM_PID)].Values[:,0]
    eaf_production = model.FlowDict['F_' + str(EAF_PID) + '_' + str(FORM_PID)].Values[:,0]
    production = bof_production + eaf_production
    available_scrap_by_category = np.sum(model.FlowDict['F_' + str(USE_PID) + '_' + str(SCRAP_PID)].Values[:,0], axis=2)


    imports, exports = get_trade(country_specific=country_specific,
                                 scaler=demand)
    scrap_imports, scrap_exports = get_scrap_trade(country_specific=country_specific,
                                                   scaler=production,
                                                   available_scrap_by_category=available_scrap_by_category)
    indirect_imports, indirect_exports = get_indirect_trade(country_specific=country_specific,
                                                            scaler=demand)
    trade = imports - exports
    scrap_trade = scrap_imports - scrap_exports
    indirect_trade = indirect_imports - indirect_exports

    print(f'Trade shape: {trade.shape}')
    print(f'Scrap trade shape: {scrap_trade.shape}')
    print(f'Indirect trade shape: {indirect_trade.shape}')

    # Check trade balance.
    # Years when original data was available are not considered for trade balance as trade was not always balanced then.
    trade = np.append(trade[:70], trade[122:], axis=0)
    scrap_trade = np.append(scrap_trade[:71], scrap_trade[123:], axis=0)
    indirect_trade = np.append(indirect_trade[:101], indirect_trade[120:], axis=0)
    trade_balance = trade.sum()
    scrap_trade_balance = scrap_trade.sum()
    indirect_trade_balance = indirect_trade.sum()

    if trade_balance < 0.001:
        print('Trade is loadable and balanced.')
    else:
        raise Exception('Trade is not balanced')
    if scrap_trade_balance < 0.001:
        print('Scrap trade is loadable and balanced.')
    else:
        raise Exception('Scrap trade is not balanced.')
    if indirect_trade_balance < 0.001:
        print('Indirect trade is loadable and balanced.')
    else:
        raise Exception('Indirect trade is not balanced.')


if __name__ == '__main__':
    _test()
