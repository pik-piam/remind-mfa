import os
from math import e
import numpy as np
import pandas as pd
from scipy.optimize import newton
from src.tools.config import cfg
from src.tools.tools import get_np_from_df
from src.predict.prediction_tools import split_future_stocks_to_base_year_categories


def predict_pauliuk(stocks, do_subcategory_predictions=False):
    past_stocks_by_category = stocks.copy()
    saturation_params = _read_pauliuk_sat_level_times()
    t_0 = 2008
    t_s = saturation_params[:, -1]
    s_hat = saturation_params[:, :4]

    if not do_subcategory_predictions:
        s_hat = np.sum(s_hat, axis=1)
        stocks = np.sum(stocks, axis=2)
    s_0 = stocks[-1]

    # If 99% of chosen saturation level is lower than current level, choose saturation of 2% higher than
    # current level instead. This is necessary for the 'c,d' calculation logic.
    s_hat = np.where(s_hat * 0.99 < s_0, 1.02 * s_0, s_hat)
    c, d = _calc_cd_pauliuk(stocks, s_hat, s_0, t_s, t_0, do_subcategory_predictions)

    future_stocks = _calc_pauliuk_stock_curve(s_hat, s_0, t_0, c, d, do_subcategory_predictions)

    if np.any(np.iscomplex(future_stocks)):
        raise RuntimeError(
            'Something went wrong in calculation of future stocks during Pauliuk predict. '
            'An imaginary number arose.')

    if not do_subcategory_predictions:
        future_stocks = split_future_stocks_to_base_year_categories(past_stocks_by_category, future_stocks)

    stocks = np.concatenate([past_stocks_by_category, future_stocks], axis=0)

    return stocks


def _calc_pauliuk_stock_curve(s_hat, s_0, t_0, c, d, do_subcategory_predictions):
    cat_letter = 'g' if do_subcategory_predictions else ''

    def S(t):
        term_a = np.einsum(f'r{cat_letter},t->tr{cat_letter}', d, t)

        term_b = 1 - e ** term_a

        term_c = np.einsum(f'r{cat_letter},tr{cat_letter}->tr{cat_letter}', c, term_b)
        term_d = 1 + np.einsum(f'r{cat_letter},tr{cat_letter}->tr{cat_letter}', s_hat / s_0 - 1, e ** term_c)
        term_e = 1 / term_d
        result = np.einsum(f'r{cat_letter},tr{cat_letter}->tr{cat_letter}', s_hat, term_e)
        return result

    years = np.arange(t_0 + 1, cfg.end_year + 1)
    t = years - t_0
    return S(t)


def _calc_cd_pauliuk(stocks, S_hat, S_0, t_s, t_0, do_subcategory_predictions):
    l_divident = 1 / 0.99 - 1
    l_divisor = S_hat / S_0 - 1
    l = np.log(l_divident / l_divisor)

    gradient_t_0 = np.gradient(stocks, axis=0)[-1]
    gradient_t_0[gradient_t_0 <= 0] = 0.001  # gradient needs to be greater than zero to work with the stock curve.
    # Even Mueller data might have in specific subcategories a negative gradient because of different population
    # develpoment in the countries of a region that has countries with various country-category-splits.

    h_divident = gradient_t_0 * (S_hat / S_0) ** 2
    h_divisor = S_hat * (S_hat / S_0 - 1)
    h = h_divident / h_divisor
    m = l / h

    v = e ** (t_s - t_0)
    ln_v = t_s - t_0

    if do_subcategory_predictions:
        ln_v = np.expand_dims(ln_v, -1)
        v = np.expand_dims(v, -1)
    q = np.emath.logn(v, -m / ln_v)

    def f(d):
        return v ** d + m * d - 1

    def f_prime(d):
        return v ** d * np.log(v) + m

    d = newton(f, x0=2 * q, fprime=f_prime)

    c = h / d

    return c, d


def _read_pauliuk_sat_level_times():
    directory = os.path.join(cfg.data_path, 'original', 'Pauliuk')
    if cfg.region_data_source == 'REMIND':
        f_name = 'pauliuk_sat_levels_times_REMIND.csv'
    elif cfg.region_data_source == 'Pauliuk':
        f_name = 'pauliuk_sat_levels_times.csv'
    else:
        raise RuntimeError(
            f"Pauliuk stock predict not defined for region aggregation '{cfg.region_data_source}'. "
            f"It needs to be either 'REMIND' or 'Pauliuk'.")
    path = os.path.join(directory, f_name)
    df_sat_levels_times = pd.read_csv(path)
    df_sat_levels_times = df_sat_levels_times.set_index('region')
    df_sat_levels_times = df_sat_levels_times[sorted(df_sat_levels_times.columns)]
    sat_levels_times = get_np_from_df(df_sat_levels_times, data_split_into_categories=False)
    return sat_levels_times


if __name__ == "__main__":
    from src.predict.calc_steel_stocks import test

    test(strategy='Pauliuk', do_visualize=True)
