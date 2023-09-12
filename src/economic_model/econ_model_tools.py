import numpy as np
from src.tools.config import cfg
from src.read_data.load_data import load_steel_prices, load_scrap_prices


def get_steel_prices():
    df_steel_prices = load_steel_prices()
    n_years = cfg.end_year - cfg.econ_base_year
    base_year_price = df_steel_prices.loc['Steel Price', cfg.econ_base_year]
    end_year_price = base_year_price * (1 + cfg.percent_steel_price_change_2100 / 100)
    yearly_price_change = (end_year_price - base_year_price) / (n_years - 1)
    end_year_price += np.sign(cfg.percent_steel_price_change_2100)
    price_projection = np.arange(base_year_price, end_year_price, yearly_price_change)

    return price_projection


def get_base_scrap_price():
    df_scrap_prices = load_scrap_prices()
    base_year_scrap_price = df_scrap_prices.loc['Steel Price', cfg.econ_base_year]
    return base_year_scrap_price
