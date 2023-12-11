import numpy as np
from src.tools.config import cfg
from matplotlib import pyplot as plt
from src.read_data.load_data import load_region_names_list


def copy_stocks_across_scenarios(stocks):
    stock_orig_shape = stocks.shape
    stocks = np.expand_dims(stocks, axis=-1)
    stocks = np.broadcast_to(stocks, stock_orig_shape + (cfg.n_scenarios,))
    return stocks


def split_future_stocks_to_base_year_categories(past_stocks_by_category, future_stocks, is_future_stocks_with_scenarios=False):
    # Summarised category data needs to split into categoriy data according to 2008 shares.
    stocks_base_year = past_stocks_by_category[-1]
    base_year_category_pctgs = stocks_base_year / np.expand_dims(np.sum(stocks_base_year, axis=-1), axis=1)
    pos_scenario_idx = 's' if is_future_stocks_with_scenarios else ''
    einsum_op = f'tr{pos_scenario_idx},rg->trg{pos_scenario_idx}'
    future_stocks = np.einsum(f'tr{pos_scenario_idx},rg->trg{pos_scenario_idx}', future_stocks, base_year_category_pctgs)
    return future_stocks


def visualise_stock_results(stocks, is_category_data=True, curve_strategy=cfg.curve_strategy):
    if is_category_data:
        stocks = np.sum(stocks, axis=2)

    region_names = load_region_names_list()
    years = np.arange(cfg.start_year, cfg.end_year + 1)
    colors = ['lightgreen', 'orangered', 'dodgerblue', 'brown', 'greenyellow',
              'crimson', 'olive', 'mediumseagreen', 'black', 'mediumblue', 'orange', 'magenta']
    for i, region in enumerate(region_names):
        # only SSP2 is chosen
        plt.plot(years, stocks[:,i,1], colors[i])
    plt.title(f'Steel stock pC development over time, {curve_strategy} prediction')
    plt.ylabel('Steel stocks per capita (t)')
    plt.xlabel('Time (y)')
    plt.axvline(x=2008, linestyle='--', color='grey')
    plt.legend(region_names)
    plt.show()