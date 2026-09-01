import numpy as np
import flodym as fd

from remind_mfa.common.data_blending import blend
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.steel.steel_config import SteelCfg


class SteelMFASystemHistoric(CommonMFASystem):

    cfg: SteelCfg

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.fill_trade()
        self.trade_set.balance(to="maximum")
        self.compute_flows()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        trd = self.trade_set

        aux = {
            "fabrication_to_good_market_total": fd.Parameter(dims=self.dims["h", "r"]),
            "recovered_scrap": fd.Parameter(dims=self.dims["h", "r"]),
        }

        # fmt: off
        flw["sysenv => forming"][...] = prm["production"]
        flw["forming => ip_market"][...] = prm["production"] * prm["forming_yield"][{'t': self.dims['h']}]
        flw["forming => sysenv"][...] = flw["sysenv => forming"] - flw["forming => ip_market"]

        self.cap_historical_net_exports_to_supply(trd["steel"], flw["forming => ip_market"])

        flw["ip_market => sysenv"][...] = trd["steel"].exports
        flw["sysenv => ip_market"][...] = trd["steel"].imports

        flw["ip_market => fabrication"][...] = flw["forming => ip_market"] + trd["steel"].net_imports

        # get approximate fabrication yield with consumption sector split
        # We don't know the good distribution yet, so we just calculate the total, and the flow later
        aux["fabrication_to_good_market_total"][...] = flw["ip_market => fabrication"] * prm["aggregate_fabrication_yield"][{'t': self.dims['h']}]
        flw["fabrication => sysenv"][...] = flw["ip_market => fabrication"] - aux["fabrication_to_good_market_total"]

        # indirect net exports are capped to not exceed available fabrication inflow, else use inflow goes negative
        self.cap_historical_net_exports_to_supply(trd["indirect"], aux["fabrication_to_good_market_total"])

        # Transfer to flows
        flw["sysenv => good_market"][...] = trd["indirect"].imports
        flw["good_market => sysenv"][...] = trd["indirect"].exports

        flw["good_market => use"][...] = self.get_historical_use_inflow_by_trade_adjusted_split(
            "indirect",
            aux["fabrication_to_good_market_total"],
            prm["sector_split"][{"t": self.dims["h"]}],
            ("g",),
        )

        # now we can get the good distribution
        flw["fabrication => good_market"][...] = flw["good_market => use"] - trd["indirect"].net_imports

        stk["historic_in_use"].inflow[...] = flw["good_market => use"]

        stk["historic_in_use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"][{"t": self.dims["h"]}],
            std=prm["lifetime_std"][{"t": self.dims["h"]}],
        )

        stk["historic_in_use"].compute()  # gives stocks and outflows corresponding to inflow

        flw["use => sysenv"][...] = stk["historic_in_use"].outflow
        aux["recovered_scrap"] = flw["use => sysenv"] * prm["recovery_rate"]
        trd["scrap"].exports[...] = trd["scrap"].exports.minimum(aux["recovered_scrap"])
        trd["scrap"].balance(to="minimum")
        # fmt: on
