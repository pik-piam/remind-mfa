import flodym as fd
import numpy as np

from remind_mfa.cement.cement_carbon_uptake_model import CementCarbonUptakeModel
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.trade_extrapolation import TradeExtrapolator


class StockDrivenCementMFASystem(CommonMFASystem):

    cfg: CementCfg

    def compute(self, stock_projection: fd.FlodymArray, historical_trade: TradeSet):
        """
        Perform all computations for the MFA system.

        Args:
            stock_projection: In-use product stock (concrete and mortar mass), with or without
                the product material (m) and constituent (k) dimensions.
            historical_trade: Trade of the historical MFA, used for trade extrapolation.
        """
        self.compute_use_stock(stock_projection)
        self.compute_flows(historical_trade)
        if self.cfg.model_switches.carbonation:
            CementCarbonUptakeModel(mfa=self).compute_carbon_flow()
        self.check_mass_balance()
        self.check_flows()

    def adjust_inflow(self, inflow: fd.FlodymArray) -> fd.FlodymArray:
        """Blend and correct the product inflow (see parent class), then add the material (m)
        and constituent (k) splits missing in the product inflow.

        Args:
            inflow: Product inflow resulting from a StockDrivenDSM computation.

        Returns:
            Composition-resolved in-use stock inflow.
        """
        product_inflow = super().adjust_inflow(inflow)
        use_inflow = self.add_product_material_split(product_inflow, self.parameters)
        use_inflow = self.add_constituent_split(use_inflow)

        # sanity check
        summed_inflow = use_inflow.sum_to(product_inflow.dims.letters)
        assert np.allclose(
            summed_inflow.values, product_inflow.values, rtol=1e-6, atol=1e-3
        ), "Composition-resolved in-use inflow does not sum up to the product inflow."
        return use_inflow

    @staticmethod
    def add_product_material_split(
        arr: fd.FlodymArray, prm: dict[str, fd.FlodymArray]
    ) -> fd.FlodymArray:
        """Split a product mass array over product materials (m), if not already resolved.

        Args:
            arr: Product mass array (e.g. stock or flow), with or without m.
            prm: Parameters, containing product_material_split and cement_ratio.

        Returns:
            Array including the m dimension. Returned unchanged if m is already present.
        """
        if "m" in arr.dims:
            return arr
        # product_material_split is a split of cement mass; convert to product mass shares
        product_mass_split = (prm["product_material_split"] / prm["cement_ratio"]).get_shares_over(
            "m"
        )
        return arr * product_mass_split

    def add_constituent_split(self, arr: fd.FlodymArray) -> fd.FlodymArray:
        """Split a product mass array into cement and non-cement (k), if not already resolved.

        The split is derived from cement_ratio.

        Args:
            arr: Product mass array (e.g. stock or flow), with or without k.

        Returns:
            Array including the k dimension. Returned unchanged if k is already present.
        """
        if "k" in arr.dims:
            return arr
        cement_ratio = self.parameters["cement_ratio"]
        constituent_split = fd.FlodymArray(dims=cement_ratio.dims.append(self.dims["k"]))
        constituent_split[{"k": "cement"}] = cement_ratio
        constituent_split[{"k": "non-cement"}] = 1 - cement_ratio
        return arr * constituent_split

    def compute_flows(self, historical_trade: TradeSet):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        trd = self.trade_set

        # concrete reuse: a share of the in-use concrete outflow re-enters the stock,
        # capped by the concrete stock inflow; mortar not reused
        flw["use => reuse"][{"m": "concrete"}] = (
            stk["use"].outflow[{"m": "concrete"}] * prm["concrete_reuse_share"]
        ).minimum(stk["use"].inflow[{"m": "concrete"}])
        flw["reuse => use"][...] = flw["use => reuse"]

        # product production: covers the stock inflow not met by reuse
        flw["prod_product => use"][...] = stk["use"].inflow - flw["reuse => use"]
        flw["market_cement => prod_product"][...] = flw["prod_product => use"][{"k": "cement"}]
        flw["sysenv => prod_product"][...] = flw["prod_product => use"][{"k": "non-cement"}]
        flw["market_cement => sysenv"][...] = (
            flw["market_cement => prod_product"]
            * prm["cement_losses"]
            / (1 - prm["cement_losses"])  # construction losses are relative to total cement use
        )

        # use phase: the non-reused in-use outflow leaves the system boundary. When carbonation is
        # active, CementCarbonUptakeModel reroutes this outflow through the eol stock it injects.
        flw["use => sysenv"][...] = stk["use"].outflow - flw["use => reuse"]

        # cement trade
        total_cement_demand = flw["market_cement => prod_product"] + flw["market_cement => sysenv"]
        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["cement"],
            future_trade=trd["cement"],
            future_dom_demand=total_cement_demand,
            n_trend_years=self.parameters["n_trend_years"],
        )
        extrapolator.run()
        flw["market_cement => exports"][...] = trd["cement"].exports
        flw["imports => market_cement"][...] = trd["cement"].imports

        # cement production
        flw["prod_cement => market_cement"][...] = (
            flw["market_cement => prod_product"]
            + flw["market_cement => sysenv"]
            + trd["cement"].net_exports
        )
        flw["market_clinker => prod_cement"][...] = (
            flw["prod_cement => market_cement"] * prm["clinker_ratio"]
        )
        flw["sysenv => prod_cement"][...] = flw["prod_cement => market_cement"] * (
            1 - prm["clinker_ratio"]
        )

        # clinker trade
        self.cap_historical_net_imports_to_demand(
            trade=historical_trade["clinker"],
            demand=flw["market_clinker => prod_cement"],
        )
        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["clinker"],
            future_trade=trd["clinker"],
            future_dom_demand=flw["market_clinker => prod_cement"],
            n_trend_years=self.parameters["n_trend_years"],
        )
        extrapolator.run()
        flw["imports => market_clinker"][...] = trd["clinker"].imports
        flw["market_clinker => exports"][...] = trd["clinker"].exports

        # clinker production
        flw["prod_clinker => market_clinker"][...] = (
            flw["market_clinker => prod_cement"] + trd["clinker"].net_exports
        )
        # net cement kiln dust generation
        flw["prod_clinker => sysenv"][...] = (
            flw["prod_clinker => market_clinker"] * prm["clinker_losses"]
        )
        flw["sysenv => prod_clinker"][...] = (
            flw["prod_clinker => market_clinker"] + flw["prod_clinker => sysenv"]
        )

        # balance trade with sysenv
        flw["exports => sysenv"][...] = (
            flw["market_cement => exports"] + flw["market_clinker => exports"]
        )
        flw["sysenv => imports"][...] = (
            flw["imports => market_cement"] + flw["imports => market_clinker"]
        )
