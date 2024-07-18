from src.dsm.dynamic_stock_model import DynamicStockModel
from src.tools.config import cfg
from src.tools.tools import get_dsm_data
from src.dsm.predict import predict_stocks
from src.tools.visualize import visualize_future_production
from src.new_odym.named_dim_arrays import NamedDimArray


def load_dsms(mfa):

    production = NamedDimArray('production', ('t','r','g'), parent_alldims=mfa.dims).load_data()

    lifetimes = {"mean": NamedDimArray('lifetime_mean', ('g',), parent_alldims=mfa.dims).load_data(),
                 "std": NamedDimArray('lifetime_std', ('g',), parent_alldims=mfa.dims).load_data()}

    historic_dsms = load_historic_stocks(mfa, production, lifetimes)

    historic_stocks = get_dsm_data(historic_dsms, lambda dsm: dsm.stock)

    stocks = predict_stocks(mfa, historic_stocks)

    dsms = _calc_future_dsms(mfa, stocks, lifetimes)

    if cfg.do_visualize["future_production"]:
        visualize_future_production(dsms, production)

    return dsms


def load_historic_stocks(mfa, production, lifetimes):

    ## TODO: make loops independent of number and names of dimensions
    historic_stocks = [[historic_stock_from_production(mfa,
                                                       production[:, area_idx, cat_idx],
                                                       lifetimes["mean"][cat_idx],
                                                       lifetimes["std"][cat_idx])
            for cat_idx in range(mfa.dims['Good'].len)]
        for area_idx in range(mfa.dims['Region'].len)]
    # move time dimension to front
    return historic_stocks


def historic_stock_from_production(mfa, production, lifetime, st_dev):
    historic_dsm = DynamicStockModel(t=mfa.historic_years.items,
                                     inflow=production,
                                     lifetime={'Type': 'Normal',
                                               'Mean': [lifetime],
                                               'StdDev': [st_dev]})
    historic_dsm.compute_inflow_driven()
    return historic_dsm


def _calc_future_dsms(mfa, stocks, lifetimes):
    ## TODO: make loops independent of number and names of dimensions
    future_dsms = [[calc_dsm(mfa,
                             stocks[:, area_idx, cat_idx],
                             lifetimes["mean"][cat_idx],
                             lifetimes["std"][cat_idx])
            for cat_idx in range(mfa.dims['Good'].len)]
        for area_idx in range(mfa.dims['Region'].len)]
    return future_dsms


def calc_dsm(mfa, stock, lifetime_mean, lifetime_std):
    future_dsm = DynamicStockModel(t=mfa.years.items,
                                   stock=stock,
                                   lifetime={'Type': 'Normal',
                                             'Mean': [lifetime_mean],
                                             'StdDev': [lifetime_std]})
    future_dsm.compute_stock_driven()
    return future_dsm


if __name__ == '__main__':
    dsms = load_dsms()
    print(dsms)
