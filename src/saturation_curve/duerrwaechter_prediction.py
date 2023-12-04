import numpy as np
from scipy.optimize import least_squares, curve_fit
import statsmodels.api as sm


def predict_duerrwaechter(stocks, gdp_data, do_subcategory_predictions=True):
    stocks = np.sum(stocks, axis=2) # TODO Decide
    gdp_data_future = gdp_data[109:]
    gdp_data_past = gdp_data[:109]  # up until 2009 all scenarios are the same

    A,b= _calc_initial_Ab(stocks, gdp_data_past)

    S_0 = stocks[-1]
    g_0 = gdp_data_past[-1]
    b_regions = -np.log(1-(S_0/A))/g_0

    stocks_future = _duerrwaechter_stock_curve(gdp_data_future, A, b_regions)
    final_stocks = np.append(stocks, stocks_future, axis=0)

    _test_vis_3_(final_stocks, gdp_data)

    A_regions = S_0 / (1 - np.exp(-b * g_0))
    stocks_future = _duerrwaechter_stock_curve(gdp_data_future, A_regions, b)
    final_stocks = np.append(stocks, stocks_future, axis=0)

    _test_vis_3_(final_stocks, gdp_data)

    # _test_vis_2(stocks, gdp_data_past, A, b)
    return stocks


def _calc_initial_Ab(stocks, gdp):
    def f(params):
        return _duerrwaechter_stock_curve(gdp.flatten(), params[0], params[1]) - stocks.flatten()
    fl_stocks = stocks.flatten()
    fl_gdp = gdp.flatten()
    predicted_highest_stock_development = 0.1  # assume saturation level to be 10 % over stock at current highest gdp
    x_h = np.argmax(fl_gdp)
    A_0 = fl_stocks[x_h] * (1 + predicted_highest_stock_development)
    b_0 = -np.log(predicted_highest_stock_development/(1+predicted_highest_stock_development))/x_h
    print(f'A_0={A_0}, b_0={b_0}')
    params = [A_0, b_0]
    result = least_squares(f, params).x
    A = result[0]
    b = result[1]

    return A, b

    # TODO decide whether to use weights

    x = np.max(gdp)

    weights = gdp.flatten()

    sigma = np.diag(1/weights**6)
    print(gdp.shape)
    print(sigma.shape)

    x = gdp.flatten()
    y = stocks.flatten()
    p0 = inital_A, initial_b
    popt2, pcov2 = curve_fit(_duerrwaechter_stock_curve, x, y, p0, sigma=sigma)
    A2 = popt2[0]
    b2 = popt2[1]

    return A, b, A2, b2


def _duerrwaechter_stock_curve(gdp, A, b):
    return A * (1 - np.exp(-b * gdp))


def _test():
    from src.model.calc_steel_stocks import get_np_steel_stocks_with_prediction

    stocks = get_np_steel_stocks_with_prediction(country_specific=False, strategy='Duerrwaechter')


def _test_vis_3_(stocks, gdp):
    from src.read_data.load_data import load_region_names_list
    from matplotlib import pyplot as plt
    regions = load_region_names_list()

    for i, region in enumerate(regions):
        if i==3:
            break
        x = gdp[:,i]
        #x = np.arange(1900,2101)
        plt.plot(x, stocks[:,i])
    plt.legend(regions)
    plt.xlabel('GDPpC ($ 2008)')
    plt.ylabel('Steel stocks pC (t)')
    plt.title('Stocks over GDP with fitted curve A*(1-exp(-bx))')
    plt.show()



def _test_vis_2(stocks, gdp_data_past, A, b):
    from matplotlib import pyplot as plt
    from src.read_data.load_data import load_region_names_list
    regions = load_region_names_list()

    print(f'A={A}, b={b}')
    for i, region in enumerate(regions):
        plt.plot(gdp_data_past[:, i], stocks[:, i], '.')

    allgdp = np.arange(0, 1.5 * np.max(gdp_data_past), 100)
    asymtote = np.ones(len(allgdp)) * A
    allstock = _duerrwaechter_stock_curve(allgdp, A, b)
    plt.legend(regions)
    plt.plot(allgdp, allstock, '--')
    plt.plot(allgdp, asymtote, '--')
    plt.xlabel('GDPpC (2008 $)')
    plt.ylabel('Steel stocks pC (t)')
    plt.text(20000, A-1, f'A={A}')
    plt.title('Stocks over GDP with fitted curve A*(1-exp(-bx))')
    plt.show()

def _test_vis_1():
    from src.read_data.load_data import load_stocks, load_gdp, load_region_names_list
    from src.tools.tools import get_np_from_df
    from matplotlib import pyplot as plt
    df_stocks = load_stocks(country_specific=False, per_capita=True)
    stocks = get_np_from_df(df_stocks, data_split_into_categories=True)
    stocks = np.moveaxis(stocks, -1, 0)  # change into SIMSON index format 'trg'
    df_gdp = load_gdp(country_specific=False, per_capita=True)
    gdp = df_gdp.to_numpy()
    gdp = gdp.transpose()
    regions = load_region_names_list()


    stocks = np.sum(stocks, axis=2)
    future_gdp = gdp[109:]
    years = np.arange(2009,2101)
    print('SSA GDP 2005-2015')
    print(gdp[105:115,-2])
    for i, region in enumerate(regions):
        plt.plot(years, future_gdp[:,i], '.')
    plt.legend(regions)
    plt.title('Future GDPpC development over time')
    plt.show()
    gdp = gdp[:109]
    for i, region in enumerate(regions):
        plt.plot(gdp[:,i], stocks[:,i], '.')
    plt.legend(regions)
    plt.title('Past SteelStockPC over GDPpC')
    plt.show()


def _test3():
    import pandas as pd
    import statsmodels.formula.api as smf

    x0, A, gamma = 12, 3, 5

    n = 200
    x = np.linspace(1, 20, n)
    yexact = A * gamma ** 2 / (gamma ** 2 + (x - x0) ** 2)

    # Add some noise with a sigma of 0.5 apart from a particularly noisy region
    # near x0 where sigma is 3
    sigma = np.ones(n) * 0.5
    sigma[np.abs(x - x0 + 1) < 1] = 3
    noise = np.random.randn(n) * sigma
    y = yexact + noise


    # create DataFrame
    df = pd.DataFrame({'hours': [1, 1, 2, 2, 2, 3, 4, 4, 4, 5, 5, 5, 6, 6, 7, 8],
                       'score': [48, 78, 72, 70, 66, 92, 93, 75, 75, 80, 95, 97,
                                 90, 96, 99, 99]})
    y = df['score']
    X = df['hours']
    X = sm.add_constant(X)
    fit = sm.OLS(y, X).fit()
    wt = 1 / smf.ols('fit.resid.abs() ~ fit.fittedvalues', data=df).fit().fittedvalues ** 2

    # fit weighted least squares regression model
    fit_wls = sm.WLS(y, X, weights=wt).fit()
    a = sm.WLS(y,X, weights=8)

    # view summary of weighted least squares regression model
    print(fit_wls.summary())


if __name__=='__main__':
    _test()