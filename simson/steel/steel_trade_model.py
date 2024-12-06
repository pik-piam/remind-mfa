from pydantic import BaseModel as PydanticBaseModel
from sodym import DimensionSet, Stock

from simson.common.trade import Trade
from simson.common.trade_predictors import predict_by_extrapolation


class SteelTradeModel(PydanticBaseModel):
    """A trade model for the steel sector storing the data and defining how trade is processed."""

    intermediate: Trade
    indirect: Trade
    scrap: Trade

    @classmethod
    def create(cls, trade_data: dict):
        """Create a new instance of the SteelTradeModel class."""
        intermediate = Trade(imports=trade_data['direct_imports'],
                             exports=trade_data['direct_exports'])
        indirect = Trade(imports=trade_data['indirect_imports'],
                         exports=trade_data['indirect_exports'])
        scrap = Trade(imports=trade_data['scrap_imports'],
                      exports=trade_data['scrap_exports'])

        return cls(intermediate=intermediate, indirect=indirect, scrap=scrap)

    @property
    def trades(self) -> list[Trade]:
        return [self.intermediate, self.indirect, self.scrap]

    def balance(self, to: str):
        for trade in self.trades:
            trade.balance(to=to)

    def predict(self, future_in_use_stock: Stock):
        product_demand = future_in_use_stock.inflow
        eol_products = future_in_use_stock.outflow

        intermediate = predict_by_extrapolation(self.intermediate, product_demand, 'Imports')
        indirect = predict_by_extrapolation(self.indirect, product_demand, 'Imports')
        scrap = predict_by_extrapolation(self.scrap, eol_products, 'Exports', adopt_scaler_dims=True)

        return SteelTradeModel(intermediate=intermediate,
                               indirect=indirect,
                               scrap=scrap)
