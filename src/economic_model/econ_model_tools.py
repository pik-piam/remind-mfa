import numpy as np
from src.tools.config import cfg
from src.read_data.load_data import load_steel_prices, load_scrap_prices


def get_steel_prices():
    df_steel_prices = load_steel_prices()
    return _calc_price_projection_linear(df_steel_prices, cfg.percent_steel_price_change_2100)


def get_scrap_prices():
    df_scrap_prices = load_scrap_prices()
    return _calc_price_projection_linear(df_scrap_prices, cfg.percent_scrap_price_change_2100)


def _calc_price_projection_linear(df_prices, percent_price_change_2100):
    n_years = cfg.end_year - cfg.econ_base_year
    base_year_price = df_prices.loc['Steel Price', cfg.econ_base_year]
    end_year_price = base_year_price * (1 + cfg.percent_scrap_price_change_2100 / 100)
    yearly_price_change = (end_year_price - base_year_price) / (n_years - 1)
    end_year_price += np.sign(percent_price_change_2100)
    price_projection = np.arange(base_year_price, end_year_price, yearly_price_change)

    return price_projection
