import numpy as np
from scipy.optimize import least_squares
from scipy.special import logit
import yaml
import statsmodels.api as sm
from math import e, log
import os
from src.tools.config import cfg


def predict(stock, pop, gdp, region):
    """
    Calculates In-use steel stock per capita data based on GDP pC using approach given in
    config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show curve for Germany.
    :return: Steel data for the years 1900-2100, so BOTH present and past using prediction
    approach given in config file.
    """

    strategy = cfg.curve_strategy
    if strategy == "Pehl":
        return predict_pehl(stock, pop, gdp)
    elif strategy == "Pauliuk":
        return predict_pauliuk(stock, region)

    return None


def predict_pehl(stock_data, pop_data, gdp_data):
    """
    Predicts steel based on approach by Michaja Pehl: assuming Sigmoid Saturation curve
    and fitting the curve to available data.
    TODO Approach from EDGE-Industry doesn't seem to be working the same for similar Python functions, UNUSABLE data!
    :param stock_data:
    :param pop_data:
    :param gdp_data:
    :return: Steel data for the years 1900-2100, so BOTH present and past.
    """
    # params are the parameters asym, xmid and scal in a list
    # make first guess of params via quantile and linear regression according to EDGEIndustry, Pehl
    asym_estimate = 1.1 * calc_quantile(stock_data, pop_data[:len(stock_data)], 0.99)
    x = []
    y = []
    for i, stock in enumerate(stock_data):
        if asym_estimate >= stock > 0:
            x_value = stock / asym_estimate
            # prepare adjustment
            if x_value == 0.0:
                x_value = 0.025
            if x_value == 1.0:
                x_value = 0.975
            x.append(x_value)
            y.append(gdp_data[i])
    x = np.array(x)
    if len(x) == 0:  # all data was smaller than 0, future is assumed to be zero
        return np.append(stock_data, np.zeros(92))
    y = np.array(y)
    x = logit(x)
    x = sm.add_constant(x)
    model = sm.OLS(y, x).fit()
    model.predict(x)
    coefficients = model.params
    x_mid_estimate = -coefficients[0] / coefficients[1]
    scal_estimate = 1 / coefficients[1]

    # optimize via non linear least squared regression
    def stock(params, gdp_pc):
        asym = params[0]
        x_mid = params[1]
        scal = params[2]
        return asym / (1 + np.exp((x_mid - gdp_pc) / scal))

    def curve(params, gdp_pc):
        result = np.zeros(len(gdp_pc), dtype='f4')
        for idx, date in enumerate(gdp_pc):
            result[idx] = stock(params, date)
        return result

    def func(params):
        return stock(params, gdp_data[:59]) - stock_data

    # params_estimate=[asym_estimate,x_mid_estimate,scal_estimate] 50000000
    params_estimate = [asym_estimate, x_mid_estimate, scal_estimate]
    final_params = least_squares(func, params_estimate).x

    future_gdp = gdp_data[-92:]
    future_steel = curve(final_params, future_gdp)
    return np.append(stock_data, future_steel)


def predict_pauliuk(histdata, region):
    """
    Predicts In-use steel stock per capita based on approach described by Pauliuk in the
    'Steel Scrap Age' Supplementary Info. Assumes Sigmoid saturation curve and predifined saturation
    time and level assumptions for each region.
    :param histdata:
    :param region:
    :return: Steel data for the years 1900-2100, so BOTH present and past.
    """
    saturation_params = {
        'LAM': [13.3, 2100],
        'OAS': [13.7, 2150],
        'SSA': [13.7, 2150],
        'EUR': [12.8, 2030],
        'NEU': [12.8, 2030],
        'MEA': [13.7, 2100],
        'REF': [12.8, 2030],
        'CAZ': [13.3, 2030],
        'CHA': [13.7, 2050],
        'IND': [13.7, 2150],
        'JPN': [14.7, 2020],
        'USA': [13.3, 2030]}

    satlevel = saturation_params[region][0]
    sattime = saturation_params[region][1]
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
    import src.read_data.read_mueller_stocks as mueller
    import src.read_data.read_UN_population as un
    import src.read_data.read_IMF_gdp as imf
    steel = mueller.normalize_mueller()['DEU']
    pop = un.load()['EUR']['DEU']
    gdp = imf.load()['EUR']['DEU']

    prediction = predict(steel, pop[50:], gdp[50:], 'EUR')

    print(prediction)

    """plt.plot(range(1950,2101),prediction)
    plt.title("Steel Stock pC Germany over Time")
    plt.show()

    plt.plot(gdp[50:], prediction,'b.')
    plt.title("Steel Stock pC Germany over GDP")
    plt.show()"""


if __name__ == "__main__":
    main()


# quantile functions from nudomarinero @ https://github.com/nudomarinero/wquantiles/blob/master/wquantiles.py
def quantile_1d(data, weights, quantile):
    """
    Compute the weighted quantile of a 1D numpy array.

    Parameters
    ----------
    data : ndarray
        Input array (one dimension).
    weights : ndarray
        Array with the weights of the same size of `data`.
    quantile : float
        Quantile to compute. It must have a value between 0 and 1.

    Returns
    -------
    quantile_1D : float
        The output value.
    """
    # Check the data
    if not isinstance(data, np.matrix):
        data = np.asarray(data)
    if not isinstance(weights, np.matrix):
        weights = np.asarray(weights)
    nd = data.ndim
    if nd != 1:
        raise TypeError("data must be a one dimensional array")
    ndw = weights.ndim
    if ndw != 1:
        raise TypeError("weights must be a one dimensional array")
    if data.shape != weights.shape:
        raise TypeError("the length of data and weights must be the same")
    if (quantile > 1.) or (quantile < 0.):
        raise ValueError("quantile must have a value between 0. and 1.")
    # Sort the data
    ind_sorted = np.argsort(data)
    sorted_data = data[ind_sorted]
    sorted_weights = weights[ind_sorted]
    # Compute the auxiliary arrays
    sn = np.cumsum(sorted_weights)
    # TODO: Check that the weights do not sum zero
    # assert Sn != 0, "The sum of the weights must not be zero"
    pn = (sn - 0.5 * sorted_weights) / sn[-1]
    # Get the value of the weighted median
    return np.interp(quantile, pn, sorted_data)


def calc_quantile(data, weights, quantile):
    """
    Weighted quantile of an array with respect to the last axis.

    Parameters
    ----------
    data : ndarray
        Input array.
    weights : ndarray
        Array with the weights. It must have the same size of the last
        axis of `data`.
    quantile : float
        Quantile to compute. It must have a value between 0 and 1.

    Returns
    -------
    quantile : float
        The output value.
    """
    # TODO: Allow to specify the axis
    nd = data.ndim
    if nd == 0:
        TypeError("data must have at least one dimension")
    elif nd == 1:
        return quantile_1d(data, weights, quantile)
    elif nd > 1:
        n = data.shape
        imr = data.reshape((np.prod(n[:-1]), n[-1]))
        result = np.apply_along_axis(quantile_1d, -1, imr, weights, quantile)
        return result.reshape(n[:-1])
