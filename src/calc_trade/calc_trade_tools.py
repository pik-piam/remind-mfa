import numpy as np
from src.tools.config import cfg


def get_trade_category_percentages(trade_data, category_axis):
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
                               where=trade_sum != 0)
    return category_share


def expand_trade_to_past_and_future(trade, scaler, first_available_year, last_available_year):
    def _scale_trade_via_trade_factor(do_before):
        if do_before:
            scaler_data = scaler[:start_idx]
            trade_factor = trade[0] / scaler[start_idx]
        else:
            scaler_data = scaler[end_idx + 1:]
            trade_factor = trade[-1] / scaler[end_idx]
        new_trade_data = np.einsum('trs,rs->trs', scaler_data, trade_factor)
        new_trade_data = balance_trade(new_trade_data)

        return new_trade_data

    # broadcast trade to five scenarios
    trade = np.expand_dims(trade, axis=2)
    trade = np.broadcast_to(trade, trade.shape[:2] + (len(cfg.scenarios),))

    # get start and end idx
    start_idx = first_available_year - cfg.start_year
    end_idx = last_available_year - cfg.start_year

    # calc data before and after available data according to scaler
    before_trade = _scale_trade_via_trade_factor(do_before=True)
    after_trade = _scale_trade_via_trade_factor(do_before=False)

    # concatenate pieces
    trade = np.concatenate((before_trade, trade, after_trade), axis=0)

    return trade


def get_imports_and_exports_from_net_trade(net_trade):
    imports = np.maximum(net_trade, 0)
    exports = np.minimum(net_trade, 0)
    exports[exports < 0] *= -1
    return imports, exports


def balance_trade(trade):
    net_trade = trade.sum(axis=1)
    sum_trade = np.abs(trade).sum(axis=1)
    balancing_factor = net_trade / sum_trade
    balancing_factor = np.expand_dims(balancing_factor, axis=1)
    balanced_trade = trade * (1 - np.sign(trade) * balancing_factor)

    return balanced_trade


def get_trade_test_data(country_specific):
    from src.model.simson_base_model import load_simson_base_model, \
        FABR_PID, USE_PID, BOF_PID, FORM_PID, EAF_PID, SCRAP_PID
    model = load_simson_base_model(country_specific=country_specific, recalculate=False)
    demand = np.sum(model.FlowDict['F_' + str(FABR_PID) + '_' + str(USE_PID)].Values[:, 0], axis=2)
    bof_production = model.FlowDict['F_' + str(BOF_PID) + '_' + str(FORM_PID)].Values[:, 0]
    eaf_production = model.FlowDict['F_' + str(EAF_PID) + '_' + str(FORM_PID)].Values[:, 0]
    production = bof_production + eaf_production
    available_scrap_by_category = np.sum(model.FlowDict['F_' + str(USE_PID) + '_' + str(SCRAP_PID)].Values[:, 0],
                                         axis=2)

    return production, demand, available_scrap_by_category
