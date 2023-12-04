import numpy as np
from src.saturation_curve.pauliuk_prediction import predict_pauliuk
from src.saturation_curve.pehl_prediction import predict_pehl
from src.saturation_curve.duerrwaechter_prediction import predict_duerrwaechter
from src.read_data.load_data import load_gdp, load_stocks, load_pop
from src.tools.config import cfg
from src.tools.tools import get_np_from_df


def get_np_steel_stocks_with_prediction(country_specific, get_per_capita=False,
                                        include_gdp_and_pop_scenarios=cfg.include_gdp_and_pop_scenarios_in_prediction,
                                        strategy=cfg.curve_strategy, ):
    """
    Calculates In-use steel stock per capita data based on GDP pC using approach given in
    config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show saturation_curve for Germany.
    :return: Steel data for the years 1900-2100, so BOTH present and past using prediction
    approach given in config file.
    """
    if country_specific:
        raise RuntimeError('Prediction strategy not defined for country_specific level.')
        # TODO decide

    pop_source = 'KC-Lutz' if include_gdp_and_pop_scenarios else cfg.pop_data_source
    gdp_source = 'Koch-Leimbach' if include_gdp_and_pop_scenarios else cfg.gdp_data_source
    df_pop = load_pop(pop_source, country_specific=country_specific)
    pop = df_pop.to_numpy()
    pop = pop.transpose()

    df_gdp = load_gdp(gdp_source=gdp_source, country_specific=country_specific, per_capita=True)
    gdp = df_gdp.to_numpy()
    gdp = gdp.transpose()

    if include_gdp_and_pop_scenarios:
        pop = pop.reshape(pop.shape[0], int(pop.shape[1] / cfg.n_scenarios), cfg.n_scenarios)
        gdp = gdp.reshape(gdp.shape[0], int(gdp.shape[1] / cfg.n_scenarios), cfg.n_scenarios)

    df_stocks = load_stocks(country_specific=False, per_capita=True)
    stocks = get_np_from_df(df_stocks, data_split_into_categories=True)
    stocks = np.moveaxis(stocks, -1, 0)  # change into SIMSON index format 'trg'
    print(f'Stocks shape: {stocks.shape}')
    if strategy == "Pehl":
        stocks = predict_pehl(stocks, gdp)
    elif strategy == "Pauliuk":
        stocks = predict_pauliuk(stocks)
    elif strategy == "Duerrwaechter":
        stocks = predict_duerrwaechter(stocks, gdp)
    else:
        raise RuntimeError(f"Prediction strategy {strategy} is not defined. "
                           f"It needs to be either 'Pauliuk', 'Pehl' or 'Duerrwaechter'.")

    if len(stocks.shape)!=4:
        # scenario dimension is missing
        stock_orig_shape = stocks.shape
        stocks = np.expand_dims(stocks, axis=-1)
        stocks = np.broadcast_to(stocks, stock_orig_shape + (cfg.n_scenarios,))

    if not get_per_capita:
        pop = np.expand_dims(pop, axis=2)  # Include category axis in pop data.
        stocks = stocks * pop
    return stocks


def _test():
    """
    Calculates StockpC/GDPpC function based on approach given in config file (e.g. Pauliuk or Pehl).
    Optionally creates plot to show saturation_curve for Germany.
    :return:
    """
    stocks = get_np_steel_stocks_with_prediction(country_specific=False, get_per_capita=True,
                                                 include_gdp_and_pop_scenarios=False, strategy=cfg.curve_strategy)
    print(f'Predicted stocks shape: {stocks.shape}')
    # _visualise_stock_results(stocks)


def _visualise_stock_results(stocks):
    from matplotlib import pyplot as plt
    from src.read_data.load_data import load_region_names_list
    region_names = load_region_names_list()
    years = np.arange(cfg.start_year, cfg.end_year + 1)
    colors = ['lightgreen', 'orangered', 'dodgerblue', 'brown', 'greenyellow',
              'crimson', 'olive', 'mediumseagreen', 'black', 'mediumblue', 'orange', 'magenta']
    for i, stock in enumerate(stocks):
        plt.plot(years, stock, colors[i])
    plt.title(f'Steel stock pC development over time, {cfg.curve_strategy} prediction')
    plt.ylabel('Steel stocks per capita (t)')
    plt.xlabel('Time (y)')
    plt.axvline(x=2008, linestyle='--', color='grey')
    plt.legend(region_names)
    plt.show()


if __name__ == "__main__":
    _test()
