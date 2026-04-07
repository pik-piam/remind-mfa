import logging
import flodym as fd
from typing import Optional

from remind_mfa.common.trade import TradeSet
from remind_mfa.common.common_config import CommonCfg


class CommonMFASystem(fd.MFASystem):

    cfg: CommonCfg
    trade_set: Optional[TradeSet] = None

    def correct_negative_inflow(self, stock_name: str, warn_small_negative: bool = True):
        """After a StockDrivenDSM computation, correct any negative inflows.
        Recomputes the stock as InflowDrivenDSM with the corrected inflow.
        As some small negative inflows may have their origin in numerical issues,
        the corresponding warning can be suppressed with warn_small_negative=FALSE.
        """
        stock = self.stocks[stock_name]
        min_inflow = stock.inflow.values.min()
        if min_inflow >= 0:
            return
        negative_regions = [r for r in self.dims["r"].items if stock.inflow[r].values.min() < 0]
        small_negative_threshold = 1e-6
        is_small = abs(min_inflow) <= small_negative_threshold
        if not is_small or warn_small_negative:
            logging.warning(
                f"In-use stock inflow <0 in regions {negative_regions}! Correcting negative inflow to 0."
            )
        corrected_inflow = stock.inflow.maximum(0)
        self.stocks[stock_name] = fd.InflowDrivenDSM(
            dims=stock.dims,
            lifetime_model=stock.lifetime_model,
            name=stock.name,
            process=stock.process,
        )
        self.stocks[stock_name].inflow[...] = corrected_inflow
        self.stocks[stock_name].compute()

    def fill_trade(self):
        """
        Fill trade from parameters named after the scheme [market_name]_imports and [market_name]_exports.
        """
        for name, trade in self.trade_set.markets.items():
            trade.imports[...] = self.parameters[f"{name}_imports"]
            trade.exports[...] = self.parameters[f"{name}_exports"]
