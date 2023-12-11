import os
import pickle
from scipy.optimize import newton
import warnings
import numpy as np
from ODYM.odym.modules import ODYM_Classes as msc
from ODYM.odym.modules import dynamic_stock_model as dsm
from src.model.simson_base_model import create_model, ENV_PID, BOF_PID, EAF_PID, FORM_PID, FABR_PID, RECYCLE_PID, \
    USE_PID, SCRAP_PID
from src.tools.config import cfg
from src.economic_model.econ_model_tools import get_steel_prices, get_base_scrap_price
from src.economic_model.load_econ_dsms import load_econ_dsms


def load_simson_econ_model(recalculate, recalculate_dsms, country_specific=False) -> msc.MFAsystem:
    file_name_end = 'countries' if country_specific else f'{cfg.region_data_source}_regions'
    file_name = f'main_economic_model_{file_name_end}.p'
    file_path = os.path.join(cfg.data_path, 'models', file_name)
    do_load_existing = os.path.exists(file_path) and not recalculate
    if do_load_existing:
        model = pickle.load(open(file_path, "rb"))
    else:
        model = create_economic_model(country_specific, recalculate_dsms)
        pickle.dump(model, open(file_path, "wb"))
    return model


def create_economic_model(country_specific, recalculate_dsms):
    #  load data
    p_steel = get_steel_prices()
    p_0_scrap = get_base_scrap_price()
    dsms = load_econ_dsms(country_specific=country_specific, p_st=p_steel, p_0_st=p_steel[0],
                          recalculate=recalculate_dsms)
    with warnings.catch_warnings():
        # TODO really necessary? -> check what's the problem
        warnings.simplefilter('ignore')
        scrap_share = _calc_scrap_share(dsms, country_specific, p_steel, p_0_scrap)
    econ_model, balance_message = create_model(country_specific=country_specific,
                                               dsms=dsms,
                                               scrap_share_in_production=scrap_share)
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
    q_0_bof = interim_model.get_flowV(BOF_PID, FORM_PID)[cfg.econ_start_index:, 0]
    q_0_eaf = interim_model.get_flowV(EAF_PID, FORM_PID)[cfg.econ_start_index:, 0]
    q_0_st = q_0_bof + q_0_eaf
    q_0_sest = interim_model.get_flowV(SCRAP_PID, RECYCLE_PID)[cfg.econ_start_index:, 0]
    s_0_se = q_0_sest / q_0_st
    r_0_recov = q_0_sest / q_eol
    a_recov = _get_a_recov(r_0_recov)
    a_diss = _get_a_diss(s_0_se)

    alpha_prep = p_sest - cfg.exog_eaf_USD98
    alpha = -(np.expand_dims(alpha_prep, axis=1) + p_0_scrap * a_recov + p_0_diss * a_diss)
    beta = (1 + a_recov) * p_0_scrap / (1 - r_0_recov) ** (1 / e_recov)
    gamma = (1 + a_diss) * p_0_diss / (1 - s_0_se) ** (1 / e_diss)

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


def _get_a_recov(initial_recovery_rate):
    a_recov = 1 / (((1 - initial_recovery_rate) / (1 - cfg.r_free_recov)) ** (
            1 / cfg.elasticity_scrap_recovery_rate) - 1)
    return np.maximum(0, a_recov)  # a needs to be positive, rule out cases where r_free > r_0_recov


def _get_a_diss(initial_scrap_share_production):
    a_diss = 1 / (((1 - initial_scrap_share_production) / (1 - cfg.r_free_diss)) **
                  (1 / cfg.elasticity_dissassembly) - 1)
    return np.maximum(0, a_diss)  # a needs to be positive, rule out cases where r_free > s_0_se
    # TODO check for both a's if not rather make r_free always at least as small as initial rate


def _check_scrap_share_calculation(s_se, x_upper_limit, s_se_mask):
    check = ((s_se >= 0) & (s_se <= x_upper_limit)) | np.logical_not(s_se_mask)
    if not np.all(check):
        raise RuntimeError(
            f'Calculation of scrap share in production failed. '
            f'{check}')


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
    form_scrap_inflow = interim_model.get_flowV(FORM_PID, SCRAP_PID)
    fabr_scrap_inflow = interim_model.get_flowV(FABR_PID, SCRAP_PID)
    eol_scrap_inflow = interim_model.get_flowV(USE_PID, SCRAP_PID)
    scrap_exports = interim_model.get_flowV(SCRAP_PID, ENV_PID)
    scrap_imports = interim_model.get_flowV(ENV_PID, SCRAP_PID)

    scrap_inflow = np.sum(eol_scrap_inflow, axis=3) + form_scrap_inflow + fabr_scrap_inflow
    q_eol = scrap_inflow + scrap_imports - scrap_exports
    q_eol = np.sum(q_eol, axis=3)
    return q_eol[cfg.econ_start_index:, 0]


def _create_dsm(inflow, lifetime, st_dev):
    time = np.array(range(cfg.n_years))
    steel_stock_dsm = dsm.DynamicStockModel(t=time,
                                            i=inflow,
                                            lt={'Type': 'Normal', 'Mean': [lifetime],
                                                'StdDev': [st_dev]})

    return steel_stock_dsm


def _test():
    load_simson_econ_model(country_specific=False, recalculate_dsms=False, recalculate=True)


if __name__ == '__main__':
    _test()
