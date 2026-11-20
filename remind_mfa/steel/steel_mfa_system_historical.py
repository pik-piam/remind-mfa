from typing import ClassVar

import numpy as np
import flodym as fd

from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.steel.steel_config import SteelCfg


class SteelMFASystemHistorical(CommonMFASystem):

    cfg: SteelCfg

    max_scrap_share: ClassVar[float] = 0.7
    """Maximum share of scrap in the metallic input to steel production."""

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
        }

        # fmt: off
        flw["forming => steel_market"][...] = prm["steel_production"] * prm["forming_yield"][{'t': self.dims['h']}]
        flw["forming => sysenv"][...] = prm["steel_production"] * prm["forming_loss_rate"][{"t": self.dims["h"]}]
        flw["forming => scrap_pool"][...] = prm["steel_production"] - flw["forming => steel_market"] - flw["forming => sysenv"]

        self.cap_historical_net_exports_to_supply(trd["steel"], flw["forming => steel_market"])

        flw["steel_market => sysenv"][...] = trd["steel"].exports
        flw["sysenv => steel_market"][...] = trd["steel"].imports

        flw["steel_market => manufacturing"][...] = flw["forming => steel_market"] + trd["steel"].net_imports

        # get approximate manufacturing yield with consumption end-use split
        # We don't know the end use distribution yet, so we just calculate the total, and the flow later
        aux["manufacturing_to_manufactured_products_market_total"][...] = flw["steel_market => manufacturing"] * prm["aggregate_manufacturing_yield"][{'t': self.dims['h']}]
        manufacturing_scrap = flw["steel_market => manufacturing"] - aux["manufacturing_to_manufactured_products_market_total"]
        flw["manufacturing => scrap_pool"][...] = manufacturing_scrap * (1 - prm["manufacturing_losses"][{"t": self.dims["h"]}])
        flw["manufacturing => sysenv"][...] = manufacturing_scrap * prm["manufacturing_losses"][{"t": self.dims["h"]}]

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

        flw["use => scrap_market"][...] = stk["use"].outflow * (1 - prm["hibernation_share"]) * prm["recovery_rate"][{"t": self.dims["h"]}]
        flw["use => sysenv"][...] = stk["use"].outflow - flw["use => scrap_market"]

        trd["scrap"].exports[...] = trd["scrap"].exports.minimum(flw["use => scrap_market"])
        trd["scrap"].balance(to="minimum")
        flw["scrap_market => sysenv"][...] = trd["scrap"].exports
        flw["sysenv => scrap_market"][...] = trd["scrap"].imports
        flw["scrap_market => scrap_pool"][...] = flw["use => scrap_market"] + trd["scrap"].net_imports
        # fmt: on

        self.compute_steel_production()

    def compute_steel_production(self):
        """Compute the scrap-based and ore-based steel production from the available scrap.

        As in the future system, the scrap input is the available scrap (scrap from the scrap
        market and new scrap from forming and manufacturing), up to `max_scrap_share` of the
        metallic input of both production routes. The rest is excess scrap. The ore-based route
        supplies the remaining metallic input.
        """
        add_assumption_doc(
            type="expert guess",
            name="historical maximum scrap share",
            value=str(self.max_scrap_share),
            description=(
                "Maximum share of scrap in the metallic input to steel production in historical "
                "years. Available scrap beyond it becomes excess scrap. The resulting scrap share "
                "is the starting point of the scenario parameter max_scrap_share, and this value "
                "where a region has no steel production."
            ),
        )
        prm = self.parameters
        flw = self.flows

        # fmt: off
        available_scrap = flw["scrap_market => scrap_pool"] + flw["forming => scrap_pool"] + flw["manufacturing => scrap_pool"]
        metallic_input = prm["steel_production"] / (1 - prm["steel_production_loss_rate"])
        flw["scrap_pool => steel_production_scrap_based"][...] = available_scrap.minimum(metallic_input * self.max_scrap_share)
        flw["scrap_pool => sysenv"][...] = available_scrap - flw["scrap_pool => steel_production_scrap_based"]
        flw["sysenv => steel_production_ore_based"][...] = metallic_input - flw["scrap_pool => steel_production_scrap_based"]

        flw["steel_production_scrap_based => forming"][...] = flw["scrap_pool => steel_production_scrap_based"] * (1 - prm["steel_production_loss_rate"])
        flw["steel_production_scrap_based => sysenv"][...] = flw["scrap_pool => steel_production_scrap_based"] * prm["steel_production_loss_rate"]
        flw["steel_production_ore_based => forming"][...] = flw["sysenv => steel_production_ore_based"] * (1 - prm["steel_production_loss_rate"])
        flw["steel_production_ore_based => sysenv"][...] = flw["sysenv => steel_production_ore_based"] * prm["steel_production_loss_rate"]
        # fmt: on

    def scrap_share(self) -> fd.Parameter:
        """Share of scrap in the metallic input to steel production, per historical year and
        region.

        Where a region has no steel production in a year, the share is `max_scrap_share`.

        Returns:
            fd.Parameter: Scrap share over historical time and region.
        """
        scrap_input = self.flows["scrap_pool => steel_production_scrap_based"]
        metallic_input = scrap_input + self.flows["sysenv => steel_production_ore_based"]

        dims = self.dims["h", "r"]
        share = fd.Parameter(dims=dims, name="max_scrap_share")
        share[...] = self.max_scrap_share
        np.divide(
            scrap_input.cast_values_to(dims),
            metallic_input.cast_values_to(dims),
            out=share.values,
            where=metallic_input.cast_values_to(dims) > 0,
        )
        return share
