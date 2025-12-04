import flodym as fd
from typing import Optional

from remind_mfa.common.trade import TradeSet
from remind_mfa.common.common_config import CommonCfg


class CommonMFASystem(fd.MFASystem):

    cfg: CommonCfg
    trade_set: Optional[TradeSet] = None

    def fill_trade(self):
        """
        Fill trade from parameters named after the scheme [market_name]_imports and [market_name]_exports.
        """
        for name, trade in self.trade_set.markets.items():
            trade.imports[...] = self.parameters[f"{name}_imports"]
            trade.exports[...] = self.parameters[f"{name}_exports"]
