import sys

from sodym.trade import ScalingBalancedTrade, MinMaxBalancedTrade
from sodym import Parameter
from simson.common.data_transformations import extrapolate_to_future
from pydantic import BaseModel as PydanticBaseModel

class SteelTradeModel():
    """A trade model for the steel sector storing the data and defining how trade is processed."""

    def __init__(self, dims, trade_data):
        self.historic_trade = {}
        self.future_trade = {}
        self.dims = dims

        self.historic_trade['Intermediate'] = MinMaxBalancedTrade(dims=dims,
                                                imports=trade_data['direct_imports'],
                                                exports=trade_data['direct_exports'])
        self.historic_trade['Indirect'] = MinMaxBalancedTrade(dims=dims,
                                            imports=trade_data['indirect_imports'],
                                            exports=trade_data['indirect_exports'])
        self.historic_trade['Scrap'] = MinMaxBalancedTrade(dims=dims,
                                            imports=trade_data['scrap_imports'],
                                            exports=trade_data['scrap_exports'])

    def balance_historic_trade(self):
        for trade in self.historic_trade.values():
            trade.balance(by='maximum')

    def balance_future_trade(self):
        for name, trade in self.future_trade.items():
            trade.balance()

    def predict(self, future_in_use_stock):
        for trade in self.historic_trade.values():
            assert 'h' in trade.imports.dims.letters and 'h' in trade.exports.dims.letters, \
                "Trade data must have a historic time dimension."

        # establish future trade as a ScalingBalancedTrade

        for name, trade in self.historic_trade.items():
            new_dims = trade.imports.dims.replace('h', self.dims['t'])
            if 'Scrap' == name:
                new_dims = new_dims.expand_by([self.dims['g']])
            self.future_trade[name] =  ScalingBalancedTrade(dims=self.dims,
                                                            imports=Parameter(name=name, dims=new_dims),
                                                            exports=Parameter(name=name, dims=new_dims))

        # predict different kinds of trade

        product_demand = future_in_use_stock.inflow
        eol_products = future_in_use_stock.outflow

        self.predict_indirect_trade(product_demand)
        self.predict_intermediate_trade(product_demand)
        self.predict_scrap_trade(eol_products)

    def predict_indirect_trade(self, product_demand):

        self.future_trade['Indirect']['Imports'][...] = extrapolate_to_future(
            historic_values=self.historic_trade['Indirect']['Imports'],
            scale_by=product_demand)

        global_indirect_imports = self.future_trade['Indirect']['Imports'].sum_nda_over(sum_over_dims='r')
        self.future_trade['Indirect']['Exports'][...] = extrapolate_to_future(
            historic_values=self.historic_trade['Indirect']['Exports'],
            scale_by=global_indirect_imports)

    def predict_intermediate_trade(self, product_demand):

        total_product_demand = product_demand.sum_nda_over(sum_over_dims='g')
        self.future_trade['Intermediate']['Imports'][...] = extrapolate_to_future(
            historic_values=self.historic_trade['Intermediate']['Imports'],
            scale_by=total_product_demand)

        global_direct_imports = self.future_trade['Intermediate']['Imports'].sum_nda_over(sum_over_dims='r')
        self.future_trade['Intermediate']['Exports'][...] = extrapolate_to_future(
            historic_values=self.historic_trade['Intermediate']['Exports'],
            scale_by=global_direct_imports)

    def predict_scrap_trade(self, eol_products):
        total_eol_products = eol_products.sum_nda_over(sum_over_dims='g')
        total_scrap_exports = extrapolate_to_future(
            historic_values=self.historic_trade['Scrap']['Exports'],
            scale_by=total_eol_products)  # shouldn't this be total _collected_ scrap?

        self.future_trade['Scrap']['Exports'][...] = total_scrap_exports * eol_products.get_shares_over('g')

        global_scrap_exports = total_scrap_exports.sum_nda_over(sum_over_dims='r')
        total_scrap_imports = extrapolate_to_future(
            historic_values=self.historic_trade['Scrap']['Imports'],
            scale_by=global_scrap_exports)

        global_scrap_exports = self.future_trade['Scrap']['Exports'].sum_nda_over(sum_over_dims='r')

        self.future_trade['Scrap']['Imports'][...] = total_scrap_imports * global_scrap_exports.get_shares_over('g')