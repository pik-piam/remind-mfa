from typing import Dict
import flodym as fd

from simson.common.trade import Trade, TradeSet
from simson.common.trade_predictors import predict_by_extrapolation


def make_historic_trade(parameters: Dict[str, fd.FlodymArray]) -> TradeSet :
    """
    Create a trade module that stores and calculates the trade flows between regions and sectors.
    """
    stage_names = [
        'intermediate',
        'indirect',
        'scrap',
    ]
    stages = {s: Trade(
        imports=parameters[f'{s}_imports'],
        exports=parameters[f'{s}_exports'],
        ) for s in stage_names}
    historic_trade = TradeSet(stages=stages)
    historic_trade.balance(to='maximum')
    return historic_trade


def make_future_trade(historic_trade: Trade, future_in_use_stock: fd.Stock):
    product_demand = future_in_use_stock.inflow
    eol_products = future_in_use_stock.outflow

    intermediate = predict_by_extrapolation(historic_trade['intermediate'], product_demand, 'imports')
    indirect = predict_by_extrapolation(historic_trade['indirect'], product_demand, 'imports')
    scrap = predict_by_extrapolation(historic_trade['scrap'], eol_products, 'exports', adopt_scaler_dims=True)

    future_trade = TradeSet(stages={
        'intermediate': intermediate,
        'indirect': indirect,
        'scrap': scrap,
        })
    future_trade.balance()
    return future_trade
