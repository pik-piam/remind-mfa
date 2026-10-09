import numpy as np
import flodym as fd

from remind_mfa.common.data_blending import blend
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.steel.steel_config import SteelCfg


class SteelMFASystemHistorical(CommonMFASystem):

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
            "manufacturing_to_manufactured_products_market_total": fd.Parameter(
                dims=self.dims["h", "r"]
            ),
            "recovered_scrap": fd.Parameter(dims=self.dims["h", "r"]),
        }

        # fmt: off
        flw["sysenv => forming"][...] = prm["steel_production"]
        flw["forming => steel_market"][...] = prm["steel_production"] * prm["forming_yield"][{'t': self.dims['h']}]
        flw["forming => sysenv"][...] = flw["sysenv => forming"] - flw["forming => steel_market"]

        self.cap_historical_net_exports_to_supply(trd["steel"], flw["forming => steel_market"])

        flw["steel_market => sysenv"][...] = trd["steel"].exports
        flw["sysenv => steel_market"][...] = trd["steel"].imports

        flw["steel_market => manufacturing"][...] = flw["forming => steel_market"] + trd["steel"].net_imports

        # get approximate manufacturing yield with consumption end-use split
        # We don't know the end use distribution yet, so we just calculate the total, and the flow later
        aux["manufacturing_to_manufactured_products_market_total"][...] = flw["steel_market => manufacturing"] * prm["aggregate_manufacturing_yield"][{'t': self.dims['h']}]
        flw["manufacturing => sysenv"][...] = flw["steel_market => manufacturing"] - aux["manufacturing_to_manufactured_products_market_total"]

        # manufactured_products net exports are capped to not exceed available manufacturing inflow, else use inflow goes negative
        self.cap_historical_net_exports_to_supply(trd["manufactured_products"], aux["manufacturing_to_manufactured_products_market_total"])

        # Transfer to flows
        flw["sysenv => manufactured_products_market"][...] = trd["manufactured_products"].imports
        flw["manufactured_products_market => sysenv"][...] = trd["manufactured_products"].exports

        flw["manufactured_products_market => use"][...] = self.get_historical_use_inflow_by_trade_adjusted_split(
            "manufactured_products",
            aux["manufacturing_to_manufactured_products_market_total"],
            prm["end_use_split"][{"t": self.dims["h"]}],
            ("u",),
        )

        # now we can get the end use distribution
        flw["manufacturing => manufactured_products_market"][...] = flw["manufactured_products_market => use"] - trd["manufactured_products"].net_imports

        stk["use"].inflow[...] = flw["manufactured_products_market => use"]

        stk["use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"][{"t": self.dims["h"]}],
            std=prm["lifetime_std"][{"t": self.dims["h"]}],
        )

        stk["use"].compute()  # gives stocks and outflows corresponding to inflow

        flw["use => sysenv"][...] = stk["use"].outflow
        aux["recovered_scrap"] = flw["use => sysenv"] * prm["recovery_rate"]
        trd["scrap"].exports[...] = trd["scrap"].exports.minimum(aux["recovered_scrap"])
        trd["scrap"].balance(to="minimum")
        # fmt: on
