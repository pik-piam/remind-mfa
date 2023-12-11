import matplotlib.pyplot as plt
import numpy as np
from src.tools.config import cfg
from src.economic_model.simson_econ_model import load_simson_econ_model
from src.read_data.load_data import load_gdp, load_pop, load_stocks
from src.tools.tools import get_np_from_df
from src.predict.calc_steel_stocks import get_np_steel_stocks_with_prediction
from src.model.load_dsms import load_dsms
from src.model.model_tools import get_dsm_data


def _test_dsm_scenarios_vis():
    dsms = load_dsms(country_specific=False)
    stocks, inflows, outflows = get_dsm_data(dsms)

    data = inflows
    data = np.sum(np.sum(data, axis=1), axis=1).transpose()
    for date in data:
        plt.plot(np.arange(1901, 2101), date[1:])
    plt.legend(cfg.scenarios)
    plt.show()


def _test_stocks_scenario():
    df_stocks = load_stocks(country_specific=False)
    stocks = get_np_steel_stocks_with_prediction(df_stocks, country_specific=False)

    for i in range(5):
        stock = stocks[1:, :, :, i]
        stock = np.sum(stock, axis=1)
        # stock = stock[:,-1] select just US instead of sum above
        stock = np.sum(stock, axis=1)
        plt.plot(np.arange(1901, 2101), stock)
    plt.legend(cfg.scenarios)
    plt.xlabel("Time (y)")
    plt.ylabel("Steel (t)")
    plt.title("In-use steel stock by scenario")
    plt.show()


def _test_stocks_per_capita_scenario():
    df_stocks = load_stocks(country_specific=False, per_capita=True)
    stocks = get_np_steel_stocks_with_prediction(df_stocks, country_specific=False)

    df_pop = load_pop('KC-Lutz', country_specific=False)
    regions = list(df_pop.index.get_level_values(0).unique())
    df_pop = df_pop.sort_index()
    pop = df_pop.to_numpy()
    pop = pop.reshape(int(pop.shape[0] / 5), 5, pop.shape[-1])
    pop = np.moveaxis(pop, 2, 0)
    stocks = np.sum(stocks, axis=2)
    stocks_per_capita = stocks / pop
    stocks_per_capita1 = stocks_per_capita[1:]
    # stocks_per_capita2 = np.sum(stocks_per_capita1, axis=1)/12
    stocks_per_capita2 = stocks_per_capita1[:, -1, :]  # USA

    for stock_per_capita in stocks_per_capita2.transpose():
        plt.plot(np.arange(1901, 2101), stock_per_capita)
    plt.legend(cfg.scenarios)
    plt.xlabel("Time (y)")
    plt.ylabel("Steel (t)")
    plt.title("In-use steel stock per capita by scenario: USA")
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


def _test_gdp_scenarios():
    df_gdp = load_gdp('Koch-Leimbach', country_specific=False, per_capita=True)
    regions = list(df_gdp.index.get_level_values(0).unique())
    df_gdp = df_gdp.sort_index()
    gdp = df_gdp.to_numpy()
    gdp = gdp.reshape(int(gdp.shape[0] / 5), 5, gdp.shape[-1])

    for r, region_gdp in enumerate(gdp):
        for scenario_gdp in region_gdp:
            plt.plot(np.arange(1900, 2101), scenario_gdp)
        plt.legend(cfg.scenarios)
        plt.xlabel("Time (y)")
        plt.ylabel("GDPpC ($)")
        plt.title(f"GDPpC of region: {regions[r]}")
        plt.show()


def _test_pop_scenarios():
    df_pop = load_pop('KC-Lutz', country_specific=False)
    regions = list(df_pop.index.get_level_values(0).unique())
    df_pop = df_pop.sort_index()
    pop = df_pop.to_numpy()
    pop = pop.reshape(int(pop.shape[0] / 5), 5, pop.shape[-1])

    for r, region_pop in enumerate(pop):
        for scenario_pop in region_pop:
            plt.plot(np.arange(1900, 2101), scenario_pop)
        plt.legend(cfg.scenarios)
        plt.xlabel("Time (y)")
        plt.ylabel("Population")
        plt.title(f"Population of region: {regions[r]}")
        plt.show()


if __name__ == '__main__':
    # _test_dsm_scenarios_vis()
    # _test_data_scenario_vis()
    # _test_stocks_scenario()
    # _test_stocks_per_capita_scenario()
    # _test_scenario_vis()
    _test_gdp_scenarios()
    # _test_pop_scenarios()
