import os
import pickle
from sympy import symbols, solve
from matplotlib import pyplot as plt
import numpy as np
from src.model.simson_model import load_simson_model, ENV_PID, PROD_PID, FIN_PID, SCRAP_PID, USE_PID, RECYCLE_PID, WASTE_PID
from ODYM.odym.modules import ODYM_Classes as msc
from ODYM.odym.modules import dynamic_stock_model as dsm
from src.tools.config import cfg
from src.read_data.load_data import load_steel_prices, load_scrap_prices, load_lifetimes
from src.model.load_dsms import check_steel_stock_dsm


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
    n_years = len(years_to_adapt)

    # load data
    p_steel = _get_steel_prices(n_years)
    base_model = load_simson_model(country_specific=country_specific)
    df_scrap_prices = load_scrap_prices()
    q_0_st = _get_flow_values(base_model, PROD_PID, FIN_PID)[cfg.econ_base_year+1-cfg.start_year,0,:]


    # iterate through years
    for i, year in enumerate(years_to_adapt):
        year_index = year - cfg.start_year
        q_eol = _get_flow_values(base_model, RECYCLE_PID, SCRAP_PID)[year_index,0,:,:].sum(axis=1)
        _adapt_economic_model_one_year(model=base_model,
                                       year_index=year_index,  # TODO: Implement better loop for year index
                                       p_st=p_steel[i],
                                       p_0_steel=p_steel[0],
                                       p_0_scrap=df_scrap_prices.loc['Steel Price', cfg.econ_base_year],
                                       e_demand=cfg.elasticity_steel,
                                       e_recov=cfg.elasticity_scrap_recovery_rate,
                                       e_diss=cfg.elasticity_dissassembly,
                                       r_0_recov=cfg.initial_recovery_rate,
                                       s_0_se=cfg.initial_scrap_share_production,
                                       q_0_st=q_0_st,
                                       q_eol=q_eol)
        break  # TODO: DELETE


def _get_flow_values(model, from_id, to_id):
    return model.FlowDict['F_' + str(from_id) + '_' + str(to_id)].Values


def _adapt_economic_model_one_year(model, year_index, p_st, p_0_steel, p_0_scrap, e_demand, e_recov, e_diss, r_0_recov,
                                   s_0_se, q_0_st, q_eol):
    q_st, q_sest, q_prst =_calc_steel_quantities(p_st, p_0_steel, p_0_scrap, e_demand, e_recov, e_diss, r_0_recov,
                           s_0_se, q_0_st, q_eol)

    _adapt_model_flows_one_year(model, year_index, q_st, q_sest, q_prst)

    return


def _adapt_model_flows_one_year(model, year_index, q_st, q_sest, q_prst):
    _get_flow_values(model, ENV_PID, PROD_PID)[year_index, 0, :] = q_prst
    _get_flow_values(model, SCRAP_PID, PROD_PID)[year_index, 0, :] = q_sest
    _get_flow_values(model, PROD_PID, FIN_PID)[year_index, 0, :] = q_st


    if cfg.include_trade:
        steel_trade_imports = _get_flow_values(model, ENV_PID, FIN_PID)[year_index, 0, :]
        steel_trade_exports = _get_flow_values(model, FIN_PID, ENV_PID)[year_index, 0, :]
        q_st+= steel_trade_imports-steel_trade_exports


    old_inflow_using = _get_flow_values(model, FIN_PID, USE_PID)[year_index, 0, :, :]
    using_cat_percentages = old_inflow_using.transpose() / old_inflow_using.sum(axis = 1)
    using_cat_percentages = using_cat_percentages.transpose()
    inflows_using = np.einsum('r,rg->rg', q_st, using_cat_percentages)
    fin_use_flow = _get_flow_values(model, FIN_PID, USE_PID)
    fin_use_flow[year_index, 0, :, :] = inflows_using
    mean, std_dev = load_lifetimes()
    for region_idx, region_inflow in inflows_using:
        for cat_idx, cat_inflow in enumerate(region_inflow):
            dsm = _create_dsm(cat_inflow, mean[cat_idx], std_dev[cat_idx])
            Stock_by_cohort = dsm.compute_s_c_inflow_driven()
            O_C = dsm.compute_o_c_from_s_c()
            S = dsm.compute_stock_total()
            DS = dsm.compute_stock_change()
            check_steel_stock_dsm(dsm)

def _create_dsm(inflow, lifetime, st_dev):
    time = np.array(range(cfg.n_years))
    steel_stock_dsm = dsm.DynamicStockModel(t=time,
                                            i=inflow,
                                            lt={'Type': 'Normal', 'Mean': [lifetime],
                                                'StdDev': [st_dev]})

    return steel_stock_dsm


def _calc_steel_quantities(p_st, p_0_steel, p_0_scrap, e_demand, e_recov, e_diss, r_0_recov,
                                   s_0_se, q_0_st, q_eol):
    p_0_diss = p_0_steel - p_0_scrap
    p_sest = p_st
    p_prst = p_st

    q_st = q_0_st * (p_st / p_0_steel) ** e_demand
    s_se = _solve_for_scrap_share_in_production(p_sest, q_st, q_eol, e_recov, r_0_recov, p_0_scrap, s_0_se, e_diss,
                                                p_0_diss)
    q_sest = q_st * s_se
    q_prst = q_st - q_sest
    # r_recov = q_sest / q_eol

    return q_st, q_sest, q_prst


def _solve_for_scrap_share_in_production(p_sest, q_st, q_eol, e_recov, r_0_recov, p_0_scrap, s_0_se, e_diss, p_0_diss):
    def f(x, region_idx):
        a = -p_sest + ((1 - (x * q_st[region_idx]) / q_eol[region_idx]) / (1 - r_0_recov)) ** (1 / e_recov) * p_0_scrap + (
                    (1 - x) / (1 - s_0_se)) ** (1 / e_diss) * (p_0_diss)

        return a

    """plt.rcParams["figure.figsize"] = [7.50, 3.50]
    plt.rcParams["figure.autolayout"] = True
    x = np.linspace(-1, 1, 1000)

    plt.plot(x, f(x), color='red')

    plt.show()"""
    # TODO : too easy, change
    all_regions_s_se = np.zeros(len(q_eol))
    for region_idx, q_eol_ind in enumerate(q_eol):
        for s_se in np.arange(0,1,0.00001):
            if np.abs(f(s_se, region_idx))<0.1:
                all_regions_s_se[region_idx] = s_se
                break

    return all_regions_s_se
    x = symbols('x')
    expr = -p_sest + ( ( 1 - (x * q_st[0]) / q_eol[0] ) / (1 - r_0_recov) ) ** (1 / e_recov) * p_0_scrap + ( (1 - x) / (1 - s_0_se) ) ** (1 / e_diss) * (p_0_diss)


    s_se = solve(expr)

    print(s_se)
    print(f(s_se[0]))
    print(f(s_se[1]))

    return s_se


def _get_steel_prices(n_years):
    df_steel_prices = load_steel_prices()
    base_year_steel_price = df_steel_prices.loc['Steel Price', cfg.econ_base_year]
    end_year_steel_price = base_year_steel_price * (1 + cfg.percent_steel_price_change_2100 / 100)
    yearly_steel_price_change = (end_year_steel_price - base_year_steel_price) / (n_years - 1)
    end_year_steel_price += np.sign(cfg.percent_steel_price_change_2100)  # for the np arange function
    steel_prices = np.arange(base_year_steel_price, end_year_steel_price, yearly_steel_price_change)

    return steel_prices


def _test():
    model = create_economic_model(country_specific=False)


if __name__ == '__main__':
    _test()
