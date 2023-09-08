import os
import pickle
from scipy.optimize import fsolve
from ODYM.odym.modules import ODYM_Classes as msc
from ODYM.odym.modules import dynamic_stock_model as dsm
import numpy as np
from src.model.simson_model import load_simson_model, ENV_PID, PROD_PID, FIN_PID, SCRAP_PID, USE_PID, RECYCLE_PID, \
    WASTE_PID
from src.tools.config import cfg
from src.read_data.load_data import load_lifetimes
from src.model.load_dsms import check_steel_stock_dsm
from src.model.simson_model import mass_balance_plausible
from src.economic_model.econ_model_tools import get_steel_prices, get_scrap_prices


def load_simson_econ_model(country_specific=False, recalculate=cfg.recalculate_data) -> msc.MFAsystem:
    file_name_end = 'countries' if country_specific else f'{cfg.region_data_source}_regions'
    file_name = f'main_economic_model_{file_name_end}.p'
    file_path = os.path.join(cfg.data_path, 'models', file_name)
    do_load_existing = os.path.exists(file_path) and not recalculate
    if do_load_existing:
        model = pickle.load(open(file_path, "rb"))
    else:
        model = create_economic_model(country_specific)
        pickle.dump(model, open(file_path, "wb"))
    return model


def create_economic_model(country_specific):
    years_to_adapt = np.arange(cfg.econ_base_year + 1, cfg.end_year + 1)
    n_years_to_adapt = len(years_to_adapt)

    # load data
    p_steel = get_steel_prices(n_years_to_adapt)
    p_scrap = get_scrap_prices(n_years_to_adapt)
    base_model = load_simson_model(country_specific=country_specific)

    a_recov = 1 / (((1 - cfg.initial_recovery_rate) / (1 - cfg.r_free_recov)) ** (
            1 / cfg.elasticity_scrap_recovery_rate) - 1)
    a_diss = 1 / (((1 - cfg.initial_scrap_share_production) / (1 - cfg.r_free_diss)) ** (
            1 / cfg.elasticity_dissassembly) - 1)

    # iterate through years
    for i, year in enumerate(years_to_adapt):
        year_idx = year - cfg.start_year
        previous_year_idx = year_idx - 1
        q_eol = _get_stock_values(base_model, SCRAP_PID)[previous_year_idx, 0, :]
        q_0_st = _get_flow_values(base_model, PROD_PID, FIN_PID)[year_idx, 0, :]
        q_0_sest = _get_flow_values(base_model, SCRAP_PID, PROD_PID)[year_idx, 0, :]
        s_0_se = q_0_sest / q_0_st
        r_0_recov = q_0_sest / q_eol

        _adapt_economic_model_one_year(model=base_model,
                                       year_index=year_idx,  # TODO: Implement better loop for year index
                                       p_st=p_steel[i],
                                       p_0_steel=p_steel[0],  # TODO: Implement base steel price as constant row
                                       p_0_scrap=p_scrap[0],  # TODO: same for scrap price, it's more accurate that way
                                       e_demand=cfg.elasticity_steel,
                                       e_recov=cfg.elasticity_scrap_recovery_rate,
                                       e_diss=cfg.elasticity_dissassembly,
                                       r_0_recov=r_0_recov,
                                       s_0_se=s_0_se,
                                       q_0_st=q_0_st,
                                       q_eol=q_eol,
                                       a_recov=a_recov,
                                       a_diss=a_diss)
        print(f'{year} calculated.')
        #  break  # TODO: DELETE
    if not mass_balance_plausible(base_model):
        raise RuntimeError('Mass Balance of economic model not plausible.')
    return base_model


def _get_flow_values(model, from_id, to_id):
    return model.FlowDict['F_' + str(from_id) + '_' + str(to_id)].Values


def _get_stock_values(model, p_id):
    return model.StockDict['S_' + str(p_id)].Values


def _get_stock_change_values(model, p_id):
    return model.StockDict['dS_' + str(p_id)].Values


def _calculate_stock_values_from_stock_change(model, p_id):
    stock_values = _get_stock_change_values(model, p_id)[:, 0, :].cumsum(axis=0)
    _get_stock_values(model, p_id)[:, 0, :] = stock_values


def _adapt_economic_model_one_year(model, year_index, p_st, p_0_steel, p_0_scrap, e_demand, e_recov, e_diss, r_0_recov,
                                   s_0_se, q_0_st, q_eol, a_recov, a_diss):
    q_st, q_sest, q_prst = _calc_steel_quantities(p_st, p_0_steel, p_0_scrap, e_demand, e_recov, e_diss, r_0_recov,
                                                  s_0_se, q_0_st, q_eol, a_diss, a_recov)
    _adapt_model_flows_one_year(model, year_index, q_st, q_sest, q_prst)

    return


def _adapt_model_flows_one_year(model, year_index, q_st, q_sest, q_prst):
    _get_flow_values(model, ENV_PID, PROD_PID)[year_index, 0, :] = q_prst
    _get_flow_values(model, SCRAP_PID, PROD_PID)[year_index, 0, :] = q_sest
    _get_flow_values(model, PROD_PID, FIN_PID)[year_index, 0, :] = q_st

    if cfg.include_trade:
        steel_trade_imports = _get_flow_values(model, ENV_PID, FIN_PID)[year_index, 0, :]
        steel_trade_exports = _get_flow_values(model, FIN_PID, ENV_PID)[year_index, 0, :]
        q_st += steel_trade_imports - steel_trade_exports

    old_inflow_using = _get_flow_values(model, FIN_PID, USE_PID)[year_index, 0, :, :]
    using_cat_percentages = old_inflow_using.transpose() / old_inflow_using.sum(axis=1)
    using_cat_percentages = using_cat_percentages.transpose()
    inflows_using = np.einsum('r,rg->rg', q_st, using_cat_percentages)
    fin_use_flow = _get_flow_values(model, FIN_PID, USE_PID)
    fin_use_flow[year_index, 0, :, :] = inflows_using
    mean, std_dev = load_lifetimes()
    in_use_stock = _get_stock_values(model, USE_PID)
    in_use_stock_change = _get_stock_change_values(model, USE_PID)
    use_recycle_flow = _get_flow_values(model, USE_PID, RECYCLE_PID)
    end_use_distribution = model.ParameterDict['End-Use_Distribution'].Values
    for region_idx in range(fin_use_flow.shape[2]):
        for good_idx in range(fin_use_flow.shape[3]):
            region_good_dsm = _create_dsm(fin_use_flow[:, 0, region_idx, good_idx], mean[good_idx], std_dev[good_idx])
            region_good_dsm.compute_s_c_inflow_driven()
            region_good_dsm.compute_o_c_from_s_c()
            outflows = region_good_dsm.compute_outflow_total()
            stock = region_good_dsm.compute_stock_total()
            stock_change = region_good_dsm.compute_stock_change()
            check_steel_stock_dsm(region_good_dsm)
            in_use_stock[:, 0, region_idx, good_idx] = stock
            in_use_stock_change[:, 0, region_idx, good_idx] = stock_change
            use_recycle_flow[:, 0, region_idx, good_idx, :] = np.einsum('t,w->tw',
                                                                        outflows,
                                                                        end_use_distribution[good_idx, :])

    recyling_inflow = np.sum(use_recycle_flow[:, 0, :, :, :], axis=2)
    recycling_waste_distribution = model.ParameterDict['Recycling-Waste_Distribution'].Values
    _get_flow_values(model, RECYCLE_PID, SCRAP_PID)[:, 0, :, :] = np.einsum('trw,w->trw',
                                                                            recyling_inflow,
                                                                            recycling_waste_distribution)
    _get_flow_values(model, RECYCLE_PID, WASTE_PID)[:, 0, :, :] = np.einsum('trw,w->trw',
                                                                            recyling_inflow,
                                                                            1 - recycling_waste_distribution)

    inflow_waste = np.sum(_get_flow_values(model, RECYCLE_PID, WASTE_PID)[:, 0, :, :], axis=2)
    _get_stock_change_values(model, WASTE_PID)[:, 0, :] = inflow_waste
    _calculate_stock_values_from_stock_change(model, WASTE_PID)

    inflow_usable_scrap = np.sum(_get_flow_values(model, RECYCLE_PID, SCRAP_PID)[:, 0, :, :], axis=2)
    recyclable = _get_flow_values(model, SCRAP_PID, PROD_PID)[:, 0, :]
    scrap_stock_change = inflow_usable_scrap - recyclable
    if cfg.include_trade:
        scrap_imports = _get_flow_values(model, ENV_PID, SCRAP_PID)[:, 0, :]
        scrap_exports = _get_flow_values(model, SCRAP_PID, ENV_PID)[:, 0, :]
        scrap_stock_change += scrap_imports - scrap_exports
    _get_stock_change_values(model, SCRAP_PID)[:, 0, :] = scrap_stock_change
    _calculate_stock_values_from_stock_change(model, SCRAP_PID)


def _create_dsm(inflow, lifetime, st_dev):
    time = np.array(range(cfg.n_years))
    steel_stock_dsm = dsm.DynamicStockModel(t=time,
                                            i=inflow,
                                            lt={'Type': 'Normal', 'Mean': [lifetime],
                                                'StdDev': [st_dev]})

    return steel_stock_dsm


def _calc_steel_quantities(p_st, p_0_steel, p_0_scrap, e_demand, e_recov, e_diss, r_0_recov,
                           s_0_se, q_0_st, q_eol, a_diss, a_recov):
    p_0_diss = p_0_steel - p_0_scrap
    p_sest = p_st
    # p_prst = p_st

    q_st = q_0_st * (p_st / p_0_steel) ** e_demand
    s_se = _solve_for_scrap_share_in_production(p_sest, q_st, q_eol, e_recov, r_0_recov, p_0_scrap, s_0_se, e_diss,
                                                p_0_diss, a_diss, a_recov)
    q_sest = q_st * s_se
    q_prst = q_st - q_sest
    # r_recov = q_sest / q_eol

    return q_st, q_sest, q_prst


def _solve_for_scrap_share_in_production(p_sest, q_st_array, q_eol_array, e_recov, r_0_recov, p_0_scrap, s_0_se, e_diss,
                                         p_0_diss,
                                         a_diss, a_recov):
    A = -(p_sest + p_0_scrap * a_recov + p_0_diss * a_diss)
    B_array = (1 + a_recov) * p_0_scrap / (1 - r_0_recov) ** (1 / e_recov)
    C_array = (1 + a_diss) * p_0_diss / (1 - s_0_se) ** (1 / e_diss)
    B = None
    C = None
    q_st = None
    q_eol = None

    def f(x):
        answer = A + (1 - x * q_st / q_eol) ** (1 / e_recov) * B + (1 - x) ** (1 / e_diss) * C
        return answer

    def scipy_find_s_se():
        s_se_candidates = fsolve(f, [0.5, x_upper_limit])
        s_se = None
        for s_se_candidate in s_se_candidates:
            if 0 <= s_se_candidate <= x_upper_limit:
                s_se = s_se_candidate
                break
        if s_se is None:
            raise RuntimeError('Mistake whilst calculating scrap share in production.')
        return s_se

    def manual_find_s_se():
        s_se_candidates = np.arange(0, x_upper_limit+0.0001, 0.0001) # check condition
        for s_se_candidate in s_se_candidates:
            if f(s_se_candidate) > 0:
                return s_se_candidate
        raise RuntimeError(f'Manual find s_se not found.{x_upper_limit} {q_st} {q_eol}')

    n_regions = len(q_eol_array)
    s_se_array = np.zeros(n_regions)
    for region_idx in range(n_regions):
        B = B_array[region_idx]
        C = C_array[region_idx]
        q_st = q_st_array[region_idx]
        q_eol = q_eol_array[region_idx]
        x_upper_limit = 1
        if q_st <= 0 or q_eol <= 0.001: # TODO CHeck condition
            s_se_array[region_idx] = 0
            continue
        elif q_st > q_eol:
            x_upper_limit = q_eol / q_st
        do_scipy_solve_for_x = False  # TODO : DECIDE !!!
        if do_scipy_solve_for_x:
            s_se = scipy_find_s_se()
        else:
            s_se = manual_find_s_se()
        s_se_array[region_idx] = s_se
    return s_se_array


def _test():
    load_simson_econ_model(country_specific=False, recalculate=True)


if __name__ == '__main__':
    _test()
