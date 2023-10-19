import numpy as np
from src.tools.config import cfg
from src.read_data.load_data import load_steel_prices, load_scrap_prices
from src.model.model_tools import calc_change_timeline


def get_steel_prices():
    df_steel_prices = load_steel_prices()
    base_year_price = df_steel_prices.loc['Steel Price', cfg.econ_base_year]
    price_change_timeline = calc_change_timeline(cfg.price_change_factor, cfg.econ_base_year,
                                                     get_timeline_from_baseyear=True)
    return base_year_price * price_change_timeline


def get_base_scrap_price():
    df_scrap_prices = load_scrap_prices()
    base_year_scrap_price = df_scrap_prices.loc['Steel Price', cfg.econ_base_year]
    return base_year_scrap_price


def _test():
    steel_prices = get_steel_prices()
    scrap_prices = get_base_scrap_price()
    print(steel_prices)
    print(steel_prices.shape)
    print(scrap_prices)


if __name__=='__main__':
    _test()
