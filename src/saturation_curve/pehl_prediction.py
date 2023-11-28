import numpy as np
from scipy.optimize import least_squares


def predict_pehl(stock_data, gdp_data):
    stock_data = stock_data[:, :, :109]
    gdp_data_future = gdp_data[:, :, 109:]
    gdp_data = gdp_data[:, 0, :109]  # up until 2009 all scenarios are the same

    initial_params = _calc_initial_params(stock_data, gdp_data)
    x_0 = gdp_data[:, 108]
    y_0 = stock_data[:, :, 108]
    params = _calc_individual_params(initial_params, stock_data, x_0, y_0)
    params = np.repeat(params[:, :, :, np.newaxis], 5, axis=3)
    gdp_data_future = np.repeat(gdp_data_future[:, np.newaxis, :, :], 4, axis=1)
    gdp_data_future = np.moveaxis(gdp_data_future, -1, 0)
    new_stocks = _pehl_stock_curve(params, gdp_data_future)

    stock_data = np.moveaxis(stock_data, 2, 0)
    stock_data = np.repeat(stock_data[:, :, :, np.newaxis], 5, axis=3)
    stocks = np.append(stock_data, new_stocks, axis=0)

    return stocks


def _calc_individual_params(general_params, stock_data, x_0, y_0):
    initial_a_sym = general_params[0] * 1.1
    high_stock = np.quantile(stock_data, 0.99, axis=2) * 1.1
    a_sym = np.maximum(initial_a_sym, high_stock)
    scal = np.tile(general_params[2], a_sym.shape[0]).reshape(a_sym.shape)
    x_mid = ((np.log(a_sym / y_0 - 1) * scal).transpose() + x_0).transpose() * 0.99
    # make sure saturation_curve starts definitely higher than current stock
    final_params = np.array([a_sym, x_mid, scal])

    return final_params


def _calc_initial_params(stock_data, gdp_data):
    def func(params, gdp, stocks):
        return _pehl_stock_curve(params, gdp) - stocks

    high_stock = np.quantile(stock_data, 0.99, axis=(0, 2))
    low_stock = np.quantile(stock_data, 0.01, axis=(0, 2))
    high_gdp = np.quantile(gdp_data, 0.99)
    low_gdp = np.quantile(gdp_data, 0.01)
    a_sym_estimate = 1.1 * high_stock
    x_mid_estimate = np.array((high_gdp - low_gdp) / 2).repeat(4)
    scal_estimate = (high_gdp - low_gdp) / (high_stock - low_stock)
    param_estimate = np.array([a_sym_estimate, x_mid_estimate, scal_estimate])
    final_params = np.array(
        [least_squares(func, param_estimate[:, i], args=(gdp_data.flatten(), stock_data[:, i, :].flatten())).x for i in
         range(4)])  # scenario doesn't matter as all are the same until the beginning of the century

    return final_params.transpose()


def _pehl_stock_curve(params, gdp_pc):
    asym = params[0]
    x_mid = params[1]
    scal = params[2]

    return asym / (1 + np.exp((x_mid - gdp_pc) / scal))


def _pehl_prime(params, gdp_pc):
    a_sym = params[0]
    x_mid = params[1]
    scal = params[2]
    x = np.exp((x_mid - gdp_pc) / scal)
    pehl_prime = a_sym * x / (scal * (1 + x))
    return pehl_prime