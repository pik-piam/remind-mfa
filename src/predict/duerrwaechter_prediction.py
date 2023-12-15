import numpy as np
from scipy.optimize import least_squares
from src.predict.prediction_tools import split_future_stocks_to_base_year_categories, \
    copy_stocks_across_scenarios
from src.tools.config import cfg


def predict_duerrwaechter(stocks, gdp_data):
    print(stocks.shape)
    print(gdp_data.shape)
    past_stocks_by_category = stocks.copy()
    stocks = np.sum(stocks, axis=2)

    gdp_data_future = gdp_data[109:]
    gdp_data_past = gdp_data[:109]  # up until 2009 all scenarios are the same
    if cfg.include_gdp_and_pop_scenarios_in_prediction:
        # gdp data is equal in the past for all 5 scenarios, for calculation of A+b we just need one
        gdp_data_past = gdp_data_past[:, :, 0]

    a, b = _calc_global_a_b(stocks, gdp_data_past)

    s_0 = stocks[-1]
    g_0 = gdp_data_past[-1]
    b_regions = -np.log(1 - (s_0 / a)) / g_0

    if cfg.include_gdp_and_pop_scenarios_in_prediction:
        gdp_data_future = np.moveaxis(gdp_data_future, -1, 0)
    future_stocks = _duerrwaechter_stock_curve(gdp_data_future, a, b_regions)
    if cfg.include_gdp_and_pop_scenarios_in_prediction:
        future_stocks = np.moveaxis(future_stocks, 0, -1)

    future_stocks = split_future_stocks_to_base_year_categories(past_stocks_by_category, future_stocks,
                                                                is_future_stocks_with_scenarios=cfg.include_gdp_and_pop_scenarios_in_prediction)
    if cfg.include_gdp_and_pop_scenarios_in_prediction:
        past_stocks_by_category = copy_stocks_across_scenarios(past_stocks_by_category)

    stocks = np.concatenate([past_stocks_by_category, future_stocks], axis=0)

    return stocks


def _calc_global_a_b(stocks, gdp, visualise=True):
    print(stocks.shape)
    print(gdp.shape)

    def f(params):
        return _duerrwaechter_stock_curve(gdp.flatten(), params[0], params[1]) - stocks.flatten()

    predicted_highest_stock_development = 0.1  # assume saturation level to be 10 % over stock at current highest gdp
    x_h = np.argmax(gdp.flatten())
    A_0 = stocks.flatten()[x_h] * (1 + predicted_highest_stock_development)
    b_0 = -np.log(predicted_highest_stock_development / (1 + predicted_highest_stock_development)) / x_h
    params = [A_0, b_0]

    result = least_squares(f, params).x

    a = result[0]
    b = result[1]

    if visualise:
        _test_plot_global_a_b(stocks, gdp, a, b)

    return a, b


def _test_plot_global_a_b(stocks, gdp, a, b):
    from matplotlib import pyplot as plt
    from src.read_data.load_data import load_region_names_list
    regions = load_region_names_list()

    for i, region in enumerate(regions):
        plt.plot(gdp[:, i], stocks[:, i], '.')

    test_gdp = np.arange(0, 60000, 100)
    test_stock = _duerrwaechter_stock_curve(test_gdp, a, b)
    test_a = np.ones_like(test_gdp) * a
    plt.plot(test_gdp, test_stock, '--')
    plt.plot(test_gdp, test_a)
    plt.xlabel('GDP ($ 2008)')
    plt.ylabel('Steel stocks per capita (t)')
    plt.title(f'Stocks over GDP with witted Duerrwächter curve, global a={a}')
    plt.legend(regions)
    plt.show()
    print(stocks.shape)
    print(gdp.shape)


def _duerrwaechter_stock_curve(gdp, a, b):
    return a * (1 - np.exp(-b * gdp))


if __name__ == '__main__':
    from src.predict.calc_steel_stocks import test

    test(strategy='Duerrwaechter', do_visualize=True)
