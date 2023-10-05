import os
import pickle
from scipy.optimize import newton
import warnings
import numpy as np
from ODYM.odym.modules import ODYM_Classes as msc
from ODYM.odym.modules import dynamic_stock_model as dsm
from src.model.simson_model import load_simson_model, ENV_PID, PROD_PID, FIN_PID, RECYCLE_PID, USE_PID, EOL_PID, \
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
    dsms = load_econ_dsms(country_specific=country_specific, p_st=p_steel, p_0_st=p_steel[0])
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        scrap_share = _calc_scrap_share(dsms, country_specific, p_steel, p_0_scrap)
    econ_model, balance_message = create_model(country_specific=country_specific, dsms=dsms, scrap_share_in_production=scrap_share)
    print(balance_message)
    return econ_model


def _calc_scrap_share(dsms, country_specific, p_st, p_0_scrap):
    interim_model, balance_message = create_model(country_specific=country_specific, dsms=dsms)
    p_sest = p_st
    q_st = _calc_q_st(dsms)
    q_eol = _calc_q_eol(interim_model)
    e_recov = cfg.elasticity_scrap_recovery_rate
    p_0_steel = p_st[0]
    p_0_diss = p_0_steel - p_0_scrap - cfg.exog_eaf_USD98
    e_diss = cfg.elasticity_dissassembly
    q_0_st = _get_flow_values(interim_model, PROD_PID, FIN_PID)[cfg.econ_start_index:, 0, :]
    q_0_sest = _get_flow_values(interim_model, RECYCLE_PID, PROD_PID)[cfg.econ_start_index:, 0, :]
    s_0_se = q_0_sest / q_0_st
    r_0_recov = q_0_sest / q_eol
    a_recov = cfg.a_recov
    a_diss = cfg.a_diss

    alpha = -(p_sest - cfg.exog_eaf_USD98 + p_0_scrap * a_recov + p_0_diss * a_diss)
    beta = (1 + a_recov) * p_0_scrap / (1 - r_0_recov) ** (1 / e_recov)
    gamma = (1 + a_diss) * p_0_diss / (1 - s_0_se) ** (1 / e_diss)
    alpha = np.array([alpha] * beta.shape[1]).transpose()
    alpha = np.repeat(alpha[:, :, np.newaxis], gamma.shape[-1], axis=2)
    c = q_st / q_eol
    f_inverse = 1 / e_recov
    e_inverse = 1 / e_diss

    def f(x):
        return alpha + (1 - x * c) ** f_inverse * beta + (1 - x) ** e_inverse * gamma

    def f_prime(x):
        return -beta * c * f_inverse * (1 - x * c) ** (f_inverse - 1) - gamma * e_inverse * (1 - x) ** (e_inverse - 1)

    x_upper_limit = _calc_x_upper_limit(q_st, q_eol)
    s_se = x_upper_limit.copy()
    s_se[s_0_se == 1] = 1
    s_se[q_eol == 0] = 0

    s_se_mask = (q_eol > 0) & (q_st > 0) & (s_0_se < 1) & (r_0_recov < 0.9998)
    x_0 = _calc_x_0(f, x_upper_limit, s_se_mask)
    root = newton(f, x_0, fprime=f_prime)
    s_se[s_se_mask] = root[s_se_mask]

    _check_scrap_share_calculation(s_se, x_upper_limit, s_se_mask)

    return s_se


def _check_scrap_share_calculation(s_se, x_upper_limit, s_se_mask):
    check = ((s_se >= 0) & (s_se <= x_upper_limit)) | np.logical_not(s_se_mask)
    if not np.all(check):
        raise RuntimeError(
            f'Calculation of scrap share in production failed. '
            f'{((s_se >= 0) & (s_se <= x_upper_limit)) | np.logical_not(s_se_mask)}')


def _calc_x_0(f, x_upper_limit, s_se_mask):
    factor = np.ones(x_upper_limit.shape) * 0.5
    test = f(x_upper_limit * factor)
    negative_check = test < 0
    while np.any(negative_check):
        factor[negative_check] += 1
        factor[negative_check] /= 2
        test = f(x_upper_limit * factor)
        negative_check = (test < 0) & s_se_mask
    return x_upper_limit * factor


def _calc_x_upper_limit(q_st, q_eol):
    x_upper_limit = np.divide(q_eol, q_st, out=np.zeros_like(q_eol), where=q_st != 0)
    x_upper_limit[x_upper_limit > 1] = 1
    return x_upper_limit


def _calc_q_st(dsms):
    inflows = np.array(
        [[[scenario_dsm.i for scenario_dsm in category_dsm] for category_dsm in region_dsm] for region_dsm in dsms])
    q_st = np.moveaxis(inflows, -1, 0)
    q_st = np.sum(q_st, axis=2)
    return q_st[cfg.econ_start_index:]


def _calc_q_eol(interim_model):
    scrap_inflow = _get_flow_values(interim_model, USE_PID, EOL_PID)
    scrap_exports = _get_flow_values(interim_model, EOL_PID, ENV_PID)
    scrap_imports = _get_flow_values(interim_model, ENV_PID, EOL_PID)
    q_eol = np.sum(scrap_inflow, axis=3) + scrap_imports - scrap_exports
    q_eol = np.sum(q_eol, axis=3)
    return q_eol[cfg.econ_start_index:, 0, :]


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
