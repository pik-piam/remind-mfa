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
        self.calc_sector_split()
        self.compute_flows()
        self.compute_in_use_stock()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        trd = self.trade_set

        aux = {
            "aggregate_fabrication_yield": self.get_new_array(dim_letters=("h", "r")),
            "fabrication_to_good_market_total": self.get_new_array(dim_letters=("h", "r")),
        }

        # fmt: off
        flw["sysenv => forming"][...] = prm["production"]
        flw["forming => ip_market"][...] = prm["production"] * prm["forming_yield"][{'t': self.dims['h']}]
        flw["forming => sysenv"][...] = flw["sysenv => forming"] - flw["forming => ip_market"]

        flw["ip_market => sysenv"][...] = trd["steel"].exports
        flw["sysenv => ip_market"][...] = trd["steel"].imports

        flw["ip_market => fabrication"][...] = flw["forming => ip_market"] + trd["steel"].net_imports

        # get approximate fabrication yield with consumption sector split
        aux["aggregate_fabrication_yield"][...] = (prm["fabrication_yield"][{'t': self.dims['h']}] * prm["sector_split"]).sum_over("g")
        # We don't know the good distribution yet, so we just calculate the total, and the flow later
        aux["fabrication_to_good_market_total"][...] = flw["ip_market => fabrication"] * aux["aggregate_fabrication_yield"]
        flw["fabrication => sysenv"][...] = flw["ip_market => fabrication"] - aux["fabrication_to_good_market_total"]

        self.scale_indirect_trade_to_fabrication(aux["fabrication_to_good_market_total"])

        # Transfer to flows
        flw["sysenv => good_market"][...] = trd["indirect"].imports
        flw["good_market => sysenv"][...] = trd["indirect"].exports

        flw["good_market => use"][...] = self.get_use_inflow_by_trade_adjusted_sector_split(aux["fabrication_to_good_market_total"])

        # now we can get the good distribution
        flw["fabrication => good_market"][...] = flw["good_market => use"] - trd["indirect"].net_imports
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
        use_inflow_target = total_use_inflow * self.parameters["sector_split"]
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

    def calc_sector_split(self) -> fd.FlodymArray:
        """Blend over GDP per capita between typical sector splits for low and high GDP per capita regions."""
        target_dims = self.dims["h", "r", "g"]
        self.parameters["sector_split"] = fd.Parameter(dims=target_dims, name="sector_split")
        sector_split_1 = fd.Parameter(dims=target_dims)
        sector_split_2 = fd.Parameter(dims=target_dims)
        log_gdppc = self.parameters["gdppc"][{"t": self.dims["h"]}].apply(np.log)
        log_gdppc_low = self.parameters["secsplit_gdppc_low"].apply(np.log)
        log_gdppc_high = self.parameters["secsplit_gdppc_high"].apply(np.log)
        add_assumption_doc(
            type="expert guess",
            name="medium sector split",
            description=(
                "Demand sector split for medium GDP per capita, to account for higher construction "
                "share in medium GDP. Roughly based on given source, but adapted."
            ),
            source="https://steel.gov.in/sites/default/files/2025-03/GSI%20Report.pdf",
        )
        log_gddpc_medium = (log_gdppc_low + log_gdppc_high) / 2

        sector_split_1[...] = blend(
            target_dims=target_dims,
            y_lower=self.parameters["sector_split_low"],
            y_upper=self.parameters["sector_split_medium"],
            x=log_gdppc,
            x_lower=log_gdppc_low,
            x_upper=log_gddpc_medium,
            type="poly_mix",
        )

        sector_split_2[...] = blend(
            target_dims=target_dims,
            y_lower=self.parameters["sector_split_medium"],
            y_upper=self.parameters["sector_split_high"],
            x=log_gdppc,
            x_lower=log_gddpc_medium,
            x_upper=log_gdppc_high,
            type="poly_mix",
        )

        mask = log_gdppc.cast_values_to(target_dims) < log_gddpc_medium.cast_values_to(target_dims)
        self.parameters["sector_split"].values = np.where(
            mask, sector_split_1.values, sector_split_2.values
        )
        return

    def compute_in_use_stock(self):
        flw = self.flows
        stk = self.stocks
        prm = self.parameters
        flw = self.flows

        stk["historic_in_use"].inflow[...] = flw["good_market => use"]

        stk["historic_in_use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"][{"t": self.dims["h"]}],
            std=prm["lifetime_std"][{"t": self.dims["h"]}],
        )

        stk["historic_in_use"].compute()  # gives stocks and outflows corresponding to inflow

        flw["use => sysenv"][...] += stk["historic_in_use"].outflow
