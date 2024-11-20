import sys

from sodym.trade import Trade
from sodym import Parameter
from sodym.dimensions import DimensionSet
from simson.common.data_transformations import extrapolate_to_future
from pydantic import BaseModel as PydanticBaseModel

class SteelTradeModel(PydanticBaseModel):
    """A trade model for the steel sector storing the data and defining how trade is processed."""

    dims : DimensionSet
    intermediate : Trade
    indirect : Trade
    scrap : Trade

    @classmethod
    def create(cls, dims: DimensionSet, trade_data: dict):
        """Create a new instance of the SteelTradeModel class."""
        intermediate = Trade(imports=trade_data['direct_imports'],
                             exports=trade_data['direct_exports'],
                             balancer=Trade.balance_by_extrenum)
        indirect = Trade(imports=trade_data['indirect_imports'],
                         exports=trade_data['indirect_exports'],
                         balancer = Trade.balance_by_extrenum)
        scrap = Trade(imports=trade_data['scrap_imports'],
                      exports=trade_data['scrap_exports'],
                      balancer=Trade.balance_by_extrenum)

        return cls(dims=dims, intermediate=intermediate, indirect=indirect,scrap=scrap)

    @property
    def trades(self) -> list[Trade]:
        return [self.intermediate, self.indirect, self.scrap]

    def balance_historic_trade(self):
        for trade in self.trades:
            trade.balance(by='maximum')

    def balance_future_trade(self):
        for trade in self.trades:
            trade.balance()

    def predict(self, future_in_use_stock):
        for trade in self.trades:
            assert 'h' in trade.imports.dims.letters and 'h' in trade.exports.dims.letters, \
                "Trade data must have a historic time dimension."

        # predict different kinds of trade

        product_demand = future_in_use_stock.inflow
        eol_products = future_in_use_stock.outflow

        return SteelTradeModel(dims=self.dims,
                               intermediate=self.predict_intermediate_trade(product_demand),
                               indirect=self.predict_indirect_trade(product_demand),
                               scrap=self.predict_scrap_trade(eol_products))

    def predict_indirect_trade(self, product_demand):
        new_dims = self.indirect.imports.dims.replace('h', self.dims['t'])
        new_indirect_trade = Trade(dims=new_dims,
                                   imports=Parameter(name=self.indirect.imports.name, dims=new_dims),
                                   exports=Parameter(name=self.indirect.exports.name, dims=new_dims),
                                   balancer=Trade.balance_by_scaling)

        new_indirect_trade.imports[...] = extrapolate_to_future(
            historic_values=self.indirect.imports,
            scale_by=product_demand)

        global_indirect_imports = new_indirect_trade.imports.sum_nda_over(sum_over_dims='r')
        new_indirect_trade.exports[...] = extrapolate_to_future(
            historic_values=self.indirect.exports,
            scale_by=global_indirect_imports)

        return new_indirect_trade

    def predict_intermediate_trade(self, product_demand):
        new_dims = self.intermediate.imports.dims.replace('h', self.dims['t'])
        new_intermediate_trade = Trade(dims=new_dims,
                                       imports=Parameter(name=self.intermediate.imports.name, dims=new_dims),
                                       exports=Parameter(name=self.intermediate.exports.name, dims=new_dims),
                                       balancer = Trade.balance_by_scaling)


        total_product_demand = product_demand.sum_nda_over(sum_over_dims='g')
        new_intermediate_trade.imports[...] = extrapolate_to_future(
            historic_values=self.intermediate.imports,
            scale_by=total_product_demand)

        global_direct_imports = new_intermediate_trade.imports.sum_nda_over(sum_over_dims='r')
        new_intermediate_trade.exports[...] = extrapolate_to_future(
            historic_values=self.intermediate.exports,
            scale_by=global_direct_imports)

        return new_intermediate_trade

    def predict_scrap_trade(self, eol_products):
        new_dims = self.scrap.imports.dims.replace('h', self.dims['t'])
        new_dims = new_dims.expand_by([self.dims['g']])

        new_scrap_trade = Trade(dims=new_dims,
                                imports=Parameter(name=self.scrap.imports.name, dims=new_dims),
                                exports=Parameter(name=self.scrap.exports.name, dims=new_dims),
                                balancer=Trade.balance_by_scaling)

        total_eol_products = eol_products.sum_nda_over(sum_over_dims='g')
        total_scrap_exports = extrapolate_to_future(
            historic_values=self.scrap.exports,
            scale_by=total_eol_products)

        new_scrap_trade.exports[...] = total_scrap_exports * eol_products.get_shares_over('g')

        global_scrap_exports = total_scrap_exports.sum_nda_over(sum_over_dims='r')
        total_scrap_imports = extrapolate_to_future(
            historic_values=self.scrap.imports,
            scale_by=global_scrap_exports)

        global_scrap_exports = new_scrap_trade.exports.sum_nda_over(sum_over_dims='r')

        new_scrap_trade.imports[...] = total_scrap_imports * global_scrap_exports.get_shares_over('g')

        return new_scrap_trade