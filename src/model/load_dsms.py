from src.odym_extension.SimsonDynamicStockModel import SimsonDynamicStockModel
from src.tools.config import cfg
from src.tools.tools import get_dsm_data
from src.predict.predict import predict_stocks
from src.read_data.load_data import load_data
from src.visualisation.visualize import visualize_future_production


def load_dsms():

    production = load_data('production')

    lifetimes = {"mean": load_data('lifetime_mean'),
                 "std": load_data('lifetime_std')}

    historic_dsms = load_historic_stocks(production, lifetimes)

    historic_stocks = get_dsm_data(historic_dsms, lambda dsm: dsm.s)

    stocks  = predict_stocks(historic_stocks)

    dsms = _calc_future_dsms(stocks, lifetimes)

    if cfg.do_visualize["future_production"]:
        visualize_future_production(dsms, production)

    return dsms


def load_historic_stocks(production, lifetimes):

    historic_stocks = [[historic_stock_from_production(production[:, area_idx, cat_idx],
                                                       lifetimes["mean"][cat_idx],
                                                       lifetimes["std"][cat_idx])
            for cat_idx in range(cfg.n_use_categories)]
        for area_idx in range(cfg.n_regions)]
    # move time dimension to front
    return historic_stocks


def historic_stock_from_production(production, lifetime, st_dev):
    historic_dsm = SimsonDynamicStockModel(t=cfg.historic_years,
                                           i=production,
                                           lt={'Type': 'Normal',
                                               'Mean': [lifetime],
                                               'StdDev': [st_dev]})
    historic_dsm.compute_all_inflow_driven()
    return historic_dsm


def _calc_future_dsms(stocks, lifetimes):
    future_dsms = [[calc_dsm(stocks[:, area_idx, cat_idx],
                             lifetimes["mean"][cat_idx],
                             lifetimes["std"][cat_idx])
            for cat_idx in range(cfg.n_use_categories)]
        for area_idx in range(cfg.n_regions)]
    return future_dsms


def calc_dsm(stock, lifetime_mean, lifetime_std):
    future_dsm = SimsonDynamicStockModel(t=cfg.years,
                                         s=stock,
                                         lt={'Type': 'Normal',
                                             'Mean': [lifetime_mean],
                                             'StdDev': [lifetime_std]})
    future_dsm.compute_all_stock_driven()
    return future_dsm


if __name__ == '__main__':
    dsms = load_dsms()
    print(dsms)
