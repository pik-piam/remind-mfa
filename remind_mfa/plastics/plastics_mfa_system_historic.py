from typing import Optional
import flodym as fd
import numpy as np

from remind_mfa.common.trade import TradeSet
from remind_mfa.common.custom_data_reader import CustomDataReader
from remind_mfa.common.trade_extrapolation import predict_by_extrapolation
from remind_mfa.common.stock_extrapolation import StockExtrapolation
from remind_mfa.common.common_cfg import PlasticsCfg
from remind_mfa.common.data_transformations import Bound, BoundList


class PlasticsMFASystemHistoric(fd.MFASystem):

    cfg: Optional[PlasticsCfg] = None
    trade_set: TradeSet

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_historic_stock()
        self.compute_trade()
        # will throw an error because flows are empty
        # self.check_mass_balance()
        # self.check_flows(no_error=True)

    def compute_historic_stock(self):
        self.stocks["in_use_historic"].inflow[...] = self.parameters["production"]
        self.stocks["in_use_historic"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"], std=self.parameters["lifetime_std"]
        )
        self.stocks["in_use_historic"].compute()

    def compute_trade(self):

        for name, trade in self.trade_set.markets.items():
            if name.endswith("_his"):
                trade.imports[...] = self.parameters[f"{name}_imports"]
                trade.exports[...] = self.parameters[f"{name}_exports"]
        self.trade_set.balance(to="maximum")
