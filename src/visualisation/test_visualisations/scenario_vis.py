import matplotlib.pyplot as plt
import numpy as np
from src.tools.config import cfg
from src.economic_model.simson_econ_model import load_simson_econ_model
from src.read_data.load_data import load_gdp, load_pop, load_stocks
from src.tools.tools import get_np_from_df
from src.curve.predict_steel import predict
from src.model.load_dsms import load_dsms
from src.model.model_tools import get_dsm_data


def _test_dsm_scenarios_vis():
    dsms = load_dsms(country_specific=False)
    stocks, inflows, outflows = get_dsm_data(dsms)

    data = inflows
    data = np.sum(np.sum(data, axis=1), axis=1).transpose()
    for date in data:
        plt.plot(np.arange(1901, 2101), date[1:])
    plt.show()


def _test_stocks_scenario():
    df_stocks = load_stocks(country_specific=False)
    stocks = predict(df_stocks, country_specific=False)

    for i in range(5):
        stock = stocks[1:, :, :, i]
        stock = np.sum(stock, axis=1)
        stock = np.sum(stock, axis=1)
        plt.plot(np.arange(1901, 2101), stock)
    plt.legend(cfg.scenarios)
    plt.xlabel("Time (y)")
    plt.ylabel("Steel (t)")
    plt.title("In-use steel by scenario")
    plt.show()


def _test_data_scenario_vis():
    df_gdp = load_gdp('Koch-Leimbach', country_specific=False, per_capita=True)
    gdp = get_np_from_df(df_gdp, data_split_into_categories=True)
    df_pop = load_pop('KC-Lutz', country_specific=False)
    pop = get_np_from_df(df_pop, data_split_into_categories=True)

    for scenario_gdp in gdp[0]:
        plt.plot(np.arange(1901, 2101), scenario_gdp[1:])
    plt.legend(cfg.scenarios)
    plt.show()

    for scenario_pop in pop[0]:
        plt.plot(np.arange(1901, 2101), scenario_pop[1:])
    plt.legend(cfg.scenarios)
    plt.show()


def _test_scenario_vis():
    # model = load_simson_model(country_specific=False)
    model = load_simson_econ_model(country_specific=False)
    production = model.FlowDict['F_2_4'].Values
    production = np.sum(np.sum(production[:, 0, :, :, :], axis=1), axis=1)
    for i in range(5):
        plt.plot(np.arange(1901, 2101), production[1:, i])

    plt.legend(cfg.scenarios)
    plt.xlabel("Time (y)")
    plt.ylabel("Production (t)")
    plt.title("Total steel inflow of using phase")
    plt.show()


if __name__ == '__main__':
    _test_dsm_scenarios_vis()
    # _test_data_scenario_vis()
    # _test_stocks_scenario()
    # _test_scenario_vis()
