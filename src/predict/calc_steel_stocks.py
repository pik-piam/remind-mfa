import numpy as np
from src.predict.pauliuk_prediction import predict_pauliuk
from src.predict.pehl_prediction import predict_pehl
from src.predict.duerrwaechter_prediction import predict_duerrwaechter
from src.read_data.load_data import load_gdp, load_stocks, load_pop
from src.tools.config import cfg
from src.tools.tools import get_np_from_df
from src.predict.prediction_tools import visualise_stock_results, copy_stocks_across_scenarios


def get_np_steel_stocks_with_prediction(country_specific, get_per_capita=False,
                                        include_gdp_and_pop_scenarios=cfg.include_gdp_and_pop_scenarios_in_prediction,
                                        strategy=cfg.curve_strategy):
    """
    Calculates In-use steel stock per capita data based on GDP pC using approach given in
    config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show predict for Germany.
    :return: Steel data for the years 1900-2100, so BOTH present and past using predict
    approach given in config file.
    """
    if country_specific:
        raise RuntimeError('Prediction strategy not defined for country_specific level.')

    pop = get_np_pop_data(country_specific, include_gdp_and_pop_scenarios)
    gdp = _get_np_gdp_data(country_specific, include_gdp_and_pop_scenarios)
    stocks = _get_np_old_stocks_data(country_specific)

    if strategy == "Pehl":
        stocks = predict_pehl(stocks, gdp)
    elif strategy == "Pauliuk":
        stocks = predict_pauliuk(stocks)
    elif strategy == "Duerrwaechter":
        stocks = predict_duerrwaechter(stocks, gdp)
    else:
        raise RuntimeError(f"Prediction strategy {strategy} is not defined. "
                           f"It needs to be either 'Pauliuk', 'Pehl' or 'Duerrwaechter'.")

    if len(stocks.shape) != 4:
        # scenario dimension is missing
        stocks = copy_stocks_across_scenarios(stocks)

    if not get_per_capita:
        stock_dims = 'trcs'
        pop_dims = 'tr'
        if include_gdp_and_pop_scenarios:
            pop_dims += 's'
        stocks = np.einsum(f'{stock_dims},{pop_dims}->{stock_dims}', stocks, pop)
    return stocks


def _get_np_old_stocks_data(country_specific):
    df_stocks = load_stocks(country_specific=country_specific, per_capita=True)
    stocks = get_np_from_df(df_stocks, data_split_into_categories=True)
    stocks = np.moveaxis(stocks, -1, 0)  # change into SIMSON index format 'trg - time, region, good'
    return stocks


def get_np_pop_data(country_specific, include_gdp_and_pop_scenarios):
    pop_source = 'KC-Lutz' if include_gdp_and_pop_scenarios else cfg.pop_data_source
    df_pop = load_pop(pop_source, country_specific=country_specific)
    pop = df_pop.to_numpy()
    pop = pop.transpose()
    if include_gdp_and_pop_scenarios:
        pop = _reshape_scenario_data(pop)
    return pop


def _get_np_gdp_data(country_specific, include_gdp_and_pop_scenarios, per_capita=True):
    gdp_source = 'Koch-Leimbach' if include_gdp_and_pop_scenarios else cfg.gdp_data_source
    df_gdp = load_gdp(gdp_source=gdp_source, country_specific=country_specific, per_capita=per_capita)
    gdp = df_gdp.to_numpy()
    gdp = gdp.transpose()

    if include_gdp_and_pop_scenarios:
        gdp = _reshape_scenario_data(gdp)

    return gdp


def _reshape_scenario_data(data):
    n_regions = int(data.shape[1] / cfg.n_scenarios)
    return data.reshape(data.shape[0], n_regions, cfg.n_scenarios)


def test(strategy=cfg.curve_strategy, do_visualize=True):
    """
    Calculates StockpC/GDPpC function based on approach given in config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show predict for Germany.
    :return:
    """
    stocks = get_np_steel_stocks_with_prediction(country_specific=False, get_per_capita=True, strategy=strategy)
    print(f'Predicted stocks shape: {stocks.shape}')
    if do_visualize:
        visualise_stock_results(stocks, curve_strategy=strategy)


if __name__ == "__main__":
    test()
