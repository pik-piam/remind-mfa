from scipy.optimize import least_squares
from math import e, log
import numpy as np
import pandas as pd
from src.read_data.read_REMIND_regions import get_REMIND_regions
from src.read_data.load_data import load_gdp, load_stocks, load_pop
from src.tools.config import cfg


def predict(df_stocks, country_specific):
    """
    Calculates In-use steel stock per capita data based on GDP pC using approach given in
    config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show curve for Germany.
    :return: Steel data for the years 1900-2100, so BOTH present and past using prediction
    approach given in config file.
    """
    if country_specific:
        raise RuntimeError('Prediction strategy not defined for country_specific level.')
    strategy = cfg.curve_strategy
    pop_source = 'KC-Lutz' if cfg.include_scenarios else cfg.pop_data_source
    gdp_source = 'Koch-Leimbach' if cfg.include_scenarios else cfg.gdp_data_source
    df_pop = load_pop(pop_source, country_specific=country_specific)
    pop = df_pop.to_numpy()
    pop = pop.reshape(int(pop.shape[0] / 5), 5, pop.shape[-1])

    df_gdp = load_gdp(gdp_source=gdp_source, country_specific=country_specific, per_capita=True)
    gdp = df_gdp.to_numpy()
    gdp = gdp.reshape(int(gdp.shape[0] / 5), 5, gdp.shape[-1])

    stocks = df_stocks.to_numpy()
    stocks = stocks.reshape(int(stocks.shape[0] / 4), 4, stocks.shape[-1])

    if strategy == "Pehl":
        stocks_per_capita = predict_pehl(stocks, gdp)
    elif strategy == "Pauliuk":
        stocks_per_capita = predict_pauliuk(stocks, region=None, category='None??')  # TODO: Implement

    stocks = np.einsum('trcs,rst->trcs', stocks_per_capita, pop)

    return stocks


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
    x_mid = ((np.log(a_sym / y_0 - 1) * scal).transpose() + x_0).transpose()
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


def get_stock_prediction_pauliuk_for_pauliuk(df_stock):
    df_regions = get_REMIND_regions()
    df_stock = df_stock.reset_index()
    df_stock = pd.merge(df_regions, df_stock, on='country')
    df_stock = df_stock.set_index(['country', 'category'])
    df_stock_new = df_stock.reindex(columns=list(range(1900, 2101)))
    for index, row in df_stock.iterrows():
        region = row['region']
        category = index[1]
        histdata = np.array(row[1:110])
        newdata = predict_pauliuk(histdata, region, category)
        df_stock_new.loc[index] = newdata

    return df_stock_new


def get_stock_prediction_pauliuk_for_mueller(df_stock):
    df_regions = get_REMIND_regions()
    df_stock = pd.merge(df_regions, df_stock, on='country')
    df_stock_new = df_stock.reindex(columns=list(range(1950, 2101)))
    for index, row in df_stock.iterrows():
        region = row['region']
        histdata = np.array(row[1:60])
        newdata = predict_pauliuk(histdata, region, category='None???')
        df_stock_new.loc[index] = newdata
    return df_stock_new


def predict_pauliuk(histdata, region, category):

    saturation_params = {
        'LAM': [1.5, 1.6, 10, 0.6, 13.3, 2100],
        'OAS': [1.5, 1.6, 10, 0.6, 13.7, 2150],
        'SSA': [1.5, 1.6, 10, 0.6, 13.7, 2150],
        'EUR': [1.3, 0.9, 10, 0.6, 12.8, 2030],
        'NEU': [1.3, 0.9, 10, 0.6, 12.8, 2030],
        'MEA': [1.5, 1.6, 10, 0.6, 13.7, 2100],
        'REF': [1.5, 0.9, 10, 0.6, 12.8, 2030],
        'CAZ': [1.5, 1.6, 9.5, 0.7, 13.3, 2020],
        'CHA': [1.5, 1.6, 10, 0.6, 13.7, 2050],
        'IND': [1.5, 1.6, 10, 0.6, 13.7, 2150],
        'JPN': [1, 0.9, 12, 0.8, 14.7, 2020],
        'USA': [1.5, 1.6, 9.5, 0.7, 13.3, 2020]}

    satlevel_index = cfg.categories_with_total.index(category)
    satlevel = saturation_params[region][satlevel_index]
    sattime = saturation_params[region][-1]
    t0 = 2008
    s0 = histdata[-1]

    # calculate gradient (a weighted average of the last four gradients is chosen to handle outliers)

    last = s0
    second = histdata[-2]
    third = histdata[-3]
    fourth = histdata[-4]
    fifth = histdata[-5]
    gradient = ((last - second) * 4 + (second - third) * 3 + (third - fourth) * 2 + (fourth - fifth) * 1) / 10

    if gradient < 0.00001:  # minimum value (there shouldn't be a negative gradient), value can be changed
        gradient = 0.00001
    if last < 0:
        s0 = 0

    # calculate parameters for sigmoid curve

    a = satlevel
    b = sattime - t0
    c = 0.99 * satlevel
    if c < s0 + gradient:
        # saturation is already reached and/or current gradient + current stock level is higher
        # than saturation
        c = (s0 + gradient) * 1.00001
        # new target saturation level is 0.002 % higher than current level,
        # will result in de facto constant stock level
        a = (s0 + gradient) * 1.00002
    d = gradient
    f = d + s0
    n = log(a / c - 1)
    m = log(a / f - 1)

    x = (m * b - n) / (m - n)
    y = (m - n) / (b - 1)

    # sigmoid prediction

    prediction = np.zeros(92)
    for i in range(92):
        prediction[i] = a / (1 + e ** (-y * (i + 1 - x)))

    return np.append(histdata, prediction)


def main():
    """
    Calculates StockpC/GDPpC function based on approach given in config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show curve for Germany.
    :return:
    """
    df_stocks = load_stocks('Mueller', False, True)
    predict(df_stocks=df_stocks, country_specific=False)


if __name__ == "__main__":
    main()
