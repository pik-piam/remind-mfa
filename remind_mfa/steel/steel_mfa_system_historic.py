import sys
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

        trd["steel"].exports[...] = trd["steel"].exports.minimum(flw["forming => ip_market"])
        trd["steel"].balance(to="minimum")

        flw["ip_market => sysenv"][...] = trd["steel"].exports
        flw["sysenv => ip_market"][...] = trd["steel"].imports

        flw["ip_market => fabrication"][...] = flw["forming => ip_market"] + trd["steel"].net_imports

        # get approximate fabrication yield with consumption sector split
        # We don't know the good distribution yet, so we just calculate the total, and the flow later
        aux["fabrication_to_good_market_total"][...] = flw["ip_market => fabrication"] * prm["aggregate_fabrication_yield"][{'t': self.dims['h']}]
        flw["fabrication => sysenv"][...] = flw["ip_market => fabrication"] - aux["fabrication_to_good_market_total"]

        self.scale_indirect_trade_to_fabrication(aux["fabrication_to_good_market_total"])

        # Transfer to flows
        flw["sysenv => good_market"][...] = trd["indirect"].imports
        flw["good_market => sysenv"][...] = trd["indirect"].exports

        flw["good_market => use"][...] = self.get_use_inflow_by_trade_adjusted_sector_split(aux["fabrication_to_good_market_total"])

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

    def scale_indirect_trade_to_fabrication(self, fabrication_to_good_market_total: fd.FlodymArray):
        """Recalculate indirect trade according to available inflow from fabrication:
        Exports are scaled down such that their sum does not exceed the fabrication
        """
        trd = self.trade_set
        exports_total = trd["indirect"].exports.sum_over(("g",))
        export_factor = exports_total.minimum(
            fabrication_to_good_market_total
        ) / exports_total.maximum(sys.float_info.epsilon)
        trd["indirect"].exports[...] = trd["indirect"].exports * export_factor
        trd["indirect"].balance(to="minimum")

    def get_use_inflow_by_trade_adjusted_sector_split(
        self, fabrication_to_good_market_total: fd.FlodymArray
    ) -> fd.FlodymArray:
        """Distribute the good_market => use flow among the good categories
        Where possible, this is done by the sector split parameter.
        However, the indirect trade may be larger then the flow for a single good category.
        The other good's inflow to the in-use stock must be reduced by these excess imports
        """
        # fmt: off
        total_use_inflow = fabrication_to_good_market_total + self.trade_set["indirect"].net_imports
        use_inflow_target = total_use_inflow * self.parameters["sector_split"][{"t": self.dims["h"]}]
        min_imports = self.trade_set["indirect"].net_imports.maximum(0)
        # imports exceeding the target values determined by the sector split for each good
        imports_excess_total = (min_imports - use_inflow_target).maximum(0).sum_over("g")
        # remainder of the target values not covered by imports, which should be covered by domestic fabrication
        fabrication_domestic_excess = (use_inflow_target - min_imports).maximum(0)
        # total of this remainder
        fabrication_domestic_excess_total = fabrication_domestic_excess.sum_over("g")
        # scale down such that the sum of the domestic fabrication is reduced by the sum of the excess imports
        fabrication_domestic = fabrication_domestic_excess * (fabrication_domestic_excess_total - imports_excess_total) / fabrication_domestic_excess_total.maximum(sys.float_info.epsilon)
        # fmt: on
        return min_imports + fabrication_domestic
