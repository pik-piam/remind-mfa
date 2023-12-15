import os
import pickle
from scipy.optimize import newton
import numpy as np
from src.odym_extension.SimDiGraph_MFAsystem import SimDiGraph_MFAsystem
from src.model.simson_base_model import create_model, ENV_PID, BOF_PID, EAF_PID, FORM_PID, FABR_PID, RECYCLE_PID, \
    USE_PID, SCRAP_PID
from src.tools.config import cfg
from src.economic_model.econ_model_tools import get_steel_prices, get_base_scrap_price
from src.economic_model.load_econ_dsms import load_econ_dsms


def load_simson_econ_model(recalculate=False, recalculate_dsms=False, country_specific=False) -> SimDiGraph_MFAsystem:
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
    scrap_share = _calc_scrap_share(dsms, country_specific, p_steel, p_0_scrap)
    econ_model, balance_message = create_model(country_specific=country_specific,
                                               dsms=dsms,
                                               scrap_share_in_production=scrap_share)
    print(balance_message)
    return econ_model


def _calc_scrap_share(dsms, country_specific, p_steel, p_0_scrap):
    interim_model, balance_message = create_model(country_specific=country_specific, dsms=dsms)
    q_st = _calc_q_st(interim_model)
    q_eol = _calc_q_eol(interim_model)
    p_0_steel = p_steel[0]
    p_0_diss = p_0_steel - p_0_scrap - cfg.exog_eaf_USD98
    e_recov = cfg.elasticity_scrap_recovery_rate
    e_diss = cfg.elasticity_dissassembly
    q_0_st, q_0_sest, s_0_se, r_0_recov = get_initial_values(interim_model, q_eol)
    a_scrap = _get_a_recov(r_0_recov)
    a_dis = _get_a_diss(s_0_se)

    q = q_st / q_eol

    alpha = _calc_alpha(p_steel, p_0_scrap, p_0_diss, a_scrap, a_dis)
    beta = _calc_beta_gamma(p_0_scrap, a_scrap, r_0_recov, e_recov)
    gamma = _calc_beta_gamma(p_0_diss, a_dis, s_0_se, e_diss)

    x_upper_limit = _calc_x_upper_limit(q_st, q_eol)

    scrap_share = _solve_for_scrap_share(alpha, beta, gamma, q, e_recov, e_diss, x_upper_limit)

    return scrap_share


def _solve_for_scrap_share(alpha, beta, gamma, q, e_recov, e_dis, x_upper_limit):
    def f(x):
        term_2 = beta * (1 - q * x) ** (1 / e_recov)
        term_3 = gamma * (1 - x) ** (1 / e_dis)
        return alpha + term_2 + term_3

    def f_prime(x):
        term_1 = beta * q * (1 / e_recov) * (1 - q * x) ** (1 / e_recov - 1)
        term_2 = gamma * (1 / e_dis) * (1 - x) ** (1 / e_dis - 1)
        result = - term_1 - term_2
        if not np.all(result > 0):
            raise RuntimeError('\nF_prime should be always positive in the chosen x intervall. \n'
                               'There has been an error.')
        return result

    x_0 = _calc_x_0(f, x_upper_limit)
    scrap_share = newton(f, x_0, fprime=f_prime)

    if np.any(scrap_share < 0) or np.any(scrap_share > 1):
        _raise_error_wrong_values('Final scrap share')

    return scrap_share


def _calc_x_0(f, x_upper_limit):
    factor = np.ones(x_upper_limit.shape) * 0.5
    test = f(x_upper_limit * factor)
    negative_check = test < 0
    while np.any(negative_check):
        factor[negative_check] += 1
        factor[negative_check] /= 2
        test = f(factor * x_upper_limit)
        negative_check = test < 0
    return factor * x_upper_limit


def _calc_alpha(p_steel, p_0_scrap, p_0_diss, a_scrap, a_dis):
    m = p_0_scrap * a_scrap
    n = p_0_diss * a_dis

    # expand p_steel across all regions
    p_steel = np.expand_dims(p_steel, axis=1)

    alpha = cfg.exog_eaf_USD98 - p_steel - m - n
    return alpha


def _calc_beta_gamma(p_0, a, values_0, e_values):
    dividend = p_0 * (1 + a)
    divisor = (1 - values_0) ** (1 / e_values)

    result = dividend / divisor
    if not np.all(result >= 0):
        raise RuntimeError('\nBoth beta and gamma need to be all positive, which is not the case. '
                           ''
                           '\nThere must have been some mistake in the data or when loading the values.')
    return result


def get_initial_values(interim_model, q_eol):
    q_0_bof = interim_model.get_flowV(BOF_PID, FORM_PID)[cfg.econ_start_index:, 0]
    q_0_eaf = interim_model.get_flowV(EAF_PID, FORM_PID)[cfg.econ_start_index:, 0]
    q_0_st = q_0_bof + q_0_eaf

    q_0_sest = interim_model.get_flowV(SCRAP_PID, RECYCLE_PID)[cfg.econ_start_index:, 0]
    s_0_se = q_0_sest / q_0_st
    r_0_recov = q_0_sest / q_eol

    if np.any(q_0_bof <= 0):
        _raise_error_wrong_values('Initial BOF production')

    if np.any(q_0_eaf <= 0):
        _raise_error_wrong_values('Initial EAF production')

    if np.any(q_0_st <= 0):
        _raise_error_wrong_values('Initial demand')
    if np.any(q_0_sest <= 0):
        _raise_error_wrong_values('Initial quantity of secondary steel in production')
    if np.any(q_eol <= 0):
        _raise_error_wrong_values('Initial quantity of end of life steel')
    if np.any(s_0_se < 0) or np.any(s_0_se > 1):
        _raise_error_wrong_values('Initial scrap share in production')
    if np.any(r_0_recov < 0) or np.any(r_0_recov > 1):
        _raise_error_wrong_values('Initial scrap recovery rate')

    return q_0_st, q_0_sest, s_0_se, r_0_recov


def _raise_error_wrong_values(data_type: str):
    error_message = f'{data_type} appears to have fault values. \n' \
                    f'\tPotential mistake in base or interim model.'
    raise RuntimeError(error_message)


def _get_a_recov(initial_recovery_rate):
    a_recov = 1 / (((1 - initial_recovery_rate) / (1 - cfg.r_free_recov)) ** (
            1 / cfg.elasticity_scrap_recovery_rate) - 1)
    if np.any(a_recov < 0):
        _warn_too_high_r_free('scrap recovery rate')
    return np.maximum(0, a_recov)  # a needs to be positive, rule out cases where r_free > r_0_recov


def _get_a_diss(initial_scrap_share_production):
    a_diss = 1 / (((1 - initial_scrap_share_production) / (1 - cfg.r_free_diss)) **
                  (1 / cfg.elasticity_dissassembly) - 1)
    if np.any(a_diss < 0):
        _warn_too_high_r_free('scrap share in production')
    return np.maximum(0, a_diss)  # a needs to be positive, rule out cases where r_free > s_0_se


def _warn_too_high_r_free(type: str):
    message = f'R_free was partly higher than initial {type}. Hence a of {type} was made positive, indirectly ' \
              f'changing r_free to be equal to the initial {type} in cases where it was greater.'
    raise RuntimeWarning(message)


def _calc_x_upper_limit(q_st, q_eol):
    x_upper_limit = np.divide(q_eol, q_st, out=np.zeros_like(q_eol), where=q_st != 0)
    x_upper_limit[x_upper_limit > 1] = 1
    return x_upper_limit


def _calc_q_st(interim_model):
    q_st = interim_model.get_flowV(FABR_PID, USE_PID)
    q_st = q_st[cfg.econ_start_index:, 0]
    q_st = np.sum(q_st, axis=2)
    return q_st


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


def _test():
    load_simson_econ_model(country_specific=False, recalculate_dsms=True, recalculate=True)


if __name__ == '__main__':
    _test()
