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
        aux["recovered_scrap"] = self.recovered_scrap()
        trd["scrap"].exports[...] = trd["scrap"].exports.minimum(aux["recovered_scrap"])
        trd["scrap"].balance(to="minimum")
        # fmt: on

    def recovered_scrap(self) -> fd.FlodymArray:
        """End-of-life scrap after hibernation and recovery, before trade."""
        prm = self.parameters
        return (
            self.flows["use => sysenv"]
            * (1 - prm["hibernation_share"])
            * prm["recovery_rate"][{"t": self.dims["h"]}]
        )

    def scrap_share(self, max_share: float) -> fd.Parameter:
        """Share of scrap in the metallic input to steel production, per historical year and
        region.

        This system has no scrap flows, so the scrap input is computed as the future system
        computes it: the available scrap (recovered end-of-life
        scrap, scrap net imports, and new scrap from forming and manufacturing), up to
        ``max_share`` of the metallic input of both production routes. Where a region has no
        steel production in a year, the share is ``max_share``.

        Args:
            max_share (float): Maximum share of scrap in the metallic input.

        Returns:
            fd.Parameter: Scrap share over historical time and region.
        """
        prm = self.parameters
        flw = self.flows
        historical = {"t": self.dims["h"]}
        assert self.trade_set is not None, "The historical steel system needs a trade set."

        forming_scrap = (
            flw["forming => sysenv"] - flw["sysenv => forming"] * prm["forming_loss_rate"][historical]
        )
        manufacturing_scrap = flw["manufacturing => sysenv"] * (
            1 - prm["manufacturing_losses"][historical]
        )
        available_scrap = (
            self.recovered_scrap().sum_over(("u",))
            + self.trade_set["scrap"].net_imports
            + forming_scrap
            + manufacturing_scrap
        )
        metallic_input = flw["sysenv => forming"] / (1 - prm["steel_production_loss_rate"])
        scrap_input = available_scrap.minimum(metallic_input * max_share)

        dims = self.dims["h", "r"]
        share = fd.Parameter(dims=dims, name="max_scrap_share")
        share[...] = max_share
        np.divide(
            scrap_input.cast_values_to(dims),
            metallic_input.cast_values_to(dims),
            out=share.values,
            where=metallic_input.cast_values_to(dims) > 0,
        )
        return share
