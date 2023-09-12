import os
import pickle
from scipy.optimize import newton
from ODYM.odym.modules import ODYM_Classes as msc
from ODYM.odym.modules import dynamic_stock_model as dsm
import numpy as np
from src.model.simson_model import load_simson_model, ENV_PID, PROD_PID, FIN_PID, SCRAP_PID, USE_PID, RECYCLE_PID, \
    WASTE_PID
from src.tools.config import cfg
from src.model.simson_model import create_model
from src.economic_model.econ_model_tools import get_steel_prices, get_base_scrap_price
from src.economic_model.load_econ_dsms import load_econ_dsms


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
    #  load data
    p_steel = get_steel_prices()
    p_0_scrap = get_base_scrap_price()
    base_model = load_simson_model(country_specific=country_specific)
    dsms = load_econ_dsms(country_specific=country_specific, p_st=p_steel, p_0_st=p_steel[0])
    scrap_share = _calc_scrap_share(base_model, dsms, country_specific, p_steel, p_0_scrap)
    econ_model = create_model(country_specific=country_specific, dsms=dsms, max_scrap_share_in_production=scrap_share)
    return econ_model


def _calc_scrap_share(base_model, dsms, country_specific, p_st, p_0_scrap):
    p_sest = p_st
    q_st = _calc_q_st(dsms)
    q_eol = _calc_q_eol(dsms, country_specific)
    e_recov = cfg.elasticity_scrap_recovery_rate
    p_0_steel = p_st[0]
    p_0_diss = p_0_steel - p_0_scrap  # TODO : Check formula, add exog(EAF)??
    e_diss = cfg.elasticity_dissassembly
    q_0_st = _get_flow_values(base_model, PROD_PID, FIN_PID)[cfg.econ_base_year - cfg.start_year + 1:, 0, :]
    q_0_sest = _get_flow_values(base_model, SCRAP_PID, PROD_PID)[cfg.econ_base_year - cfg.start_year + 1:, 0, :]
    s_0_se = q_0_sest / q_0_st
    r_0_recov = q_0_sest / q_eol
    a_recov = cfg.a_recov
    a_diss = cfg.a_diss

    alpha = -(p_sest + p_0_scrap * a_recov + p_0_diss * a_diss)
    beta = (1 + a_recov) * p_0_scrap / (1 - r_0_recov) ** (1 / e_recov)
    gamma = (1 + a_diss) * p_0_diss / (1 - s_0_se) ** (1 / e_diss)
    alpha = np.array([alpha] * beta.shape[1]).transpose()
    c = q_st / q_eol
    f_inverse = 1 / e_recov
    e_inverse = 1 / e_diss

    def f(x):
        return alpha + (1 - x * q_st / q_eol) ** (1 / e_recov) * beta + (1 - x) ** (1 / e_diss) * gamma

    def f_prime(x):
        return -beta * c * f_inverse * (1 - x * c) ** (f_inverse - 1) - gamma * e_inverse * (1 - x) ** (e_inverse - 1)

    def f_prime2(x):
        return beta * c ** 2 * f_inverse * (f_inverse - 1) * (1 - x * c) ** (f_inverse - 2) + gamma * e_inverse * (
                e_inverse - 1) * (1 - x) ** (e_inverse - 2)

    x_upper_limit = _calc_x_upper_limit(q_st, q_eol)

    s_se = newton(f, x_upper_limit / 2, fprime=f_prime, fprime2=f_prime2)


    s_se_relevant = (q_st <= 0) | (q_eol <= 0.001)
    s_se = s_se * s_se_relevant

    print('Check: ')
    print(s_se.shape)
    check = (s_se>=0) & (s_se<=x_upper_limit)
    for line in check:
        print(line)


    s_se = s_se.transpose()
    base_s_se = np.ones([s_se.shape[0], cfg.n_years]) * cfg.max_scrap_share_production
    base_s_se[:, cfg.econ_base_year - cfg.start_year + 1:] = s_se
    return base_s_se


def _calc_x_upper_limit(q_st, q_eol):
    q_st_bigger = q_st > q_eol
    x_upper_limit = q_st_bigger * q_eol / q_st
    ones = np.logical_not(q_st_bigger) * np.ones(q_st.shape)
    return x_upper_limit + ones


def _calc_q_st(dsms):
    q_st = np.array([[category_dsm.i for category_dsm in category_dsms] for category_dsms in dsms])
    return np.sum(q_st.transpose(), axis=1)[cfg.econ_base_year - cfg.start_year + 1:]


def _calc_q_eol(dsms, country_specific):
    interim_model = create_model(country_specific=country_specific, dsms=dsms)
    scrap_inflow = _get_flow_values(interim_model, RECYCLE_PID, SCRAP_PID)
    scrap_exports = _get_flow_values(interim_model, SCRAP_PID, ENV_PID)
    scrap_imports = _get_flow_values(interim_model, ENV_PID, SCRAP_PID)
    q_eol = np.sum(scrap_inflow, axis=3) + scrap_imports - scrap_exports
    return q_eol[cfg.econ_base_year - cfg.start_year + 1:, 0, :]


def _get_flow_values(model, from_id, to_id):
    return model.FlowDict['F_' + str(from_id) + '_' + str(to_id)].Values


def _create_dsm(inflow, lifetime, st_dev):
    time = np.array(range(cfg.n_years))
    steel_stock_dsm = dsm.DynamicStockModel(t=time,
                                            i=inflow,
                                            lt={'Type': 'Normal', 'Mean': [lifetime],
                                                'StdDev': [st_dev]})

    return steel_stock_dsm


def _test():
    load_simson_econ_model(country_specific=False, recalculate=True)


if __name__ == '__main__':
    _test()
