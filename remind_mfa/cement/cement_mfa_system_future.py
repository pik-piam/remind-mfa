import flodym as fd
import numpy as np

from remind_mfa.cement.cement_carbon_uptake_model import CementCarbonUptakeModel
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.trade_extrapolation import TradeExtrapolator
from remind_mfa.common.assumptions_doc import add_assumption_doc


class StockDrivenCementMFASystem(CommonMFASystem):

    cfg: CementCfg

    def compute(self, stock_projection: fd.FlodymArray, historical_trade: TradeSet):
        """
        Perform all computations for the MFA system.

        Args:
            stock_projection: In-use product stock (concrete and mortar mass), with or without
                the construction material (m) and constituent (k) dimensions.
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
        use_inflow = self.add_construction_material_split(product_inflow, self.parameters)
        use_inflow = self.add_constituent_split(use_inflow)

        # sanity check
        summed_inflow = use_inflow.sum_to(product_inflow.dims.letters)
        assert np.allclose(
            summed_inflow.values, product_inflow.values, rtol=1e-6, atol=1e-3
        ), "Composition-resolved in-use inflow does not sum up to the product inflow."
        return use_inflow

    @staticmethod
    def add_construction_material_split(
        arr: fd.FlodymArray, prm: dict[str, fd.FlodymArray]
    ) -> fd.FlodymArray:
        """Split a product mass array over construction materials (m), if not already resolved.

        Args:
            arr: Product mass array (e.g. stock or flow), with or without m.
            prm: Parameters, containing construction_material_split and cement_ratio.

        Returns:
            Array including the m dimension. Returned unchanged if m is already present.
        """
        if "m" in arr.dims:
            return arr
        # construction_material_split is a split of cement mass; convert to product mass shares
        product_mass_split = (
            prm["construction_material_split"] / prm["cement_ratio"]
        ).get_shares_over("m")
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
        return arr * self.constituent_split()

    def constituent_split(self) -> fd.FlodymArray:
        """Split of newly produced product mass into cement and non-cement (k), from
        cement_ratio."""
        cement_ratio = self.parameters["cement_ratio"]
        constituent_split = fd.FlodymArray(dims=cement_ratio.dims.append(self.dims["k"]))
        constituent_split[{"k": "Cement"}] = cement_ratio
        constituent_split[{"k": "Non-Cement"}] = 1 - cement_ratio
        return constituent_split

    def compute_flows(self, historical_trade: TradeSet):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        trd = self.trade_set

        # hibernation: a share of the in-use outflow remains in place and is not demolished
        flw["use => hibernating"][...] = self.compute_hibernation(stk["use"].outflow)
        flw["use => eol_management"][...] = stk["use"].outflow - flw["use => hibernating"]

        # reuse: a share of the demolished construction material may re-enter the stock,
        # capped by the stock inflow.
        add_assumption_doc(
            type="model assumption",
            name="Cement content of reused material",
            description=(
                "Reused concrete and mortar are assigned the cement ratio of new construction in"
                " the year of reuse instead of the cement content of the demolished material."
                " This leads to negligible errors in stock and outflow if cement ratio changes."
            ),
        )
        reuse = (flw["use => eol_management"].sum_over("k") * prm["reuse_share"]).minimum(
            stk["use"].inflow.sum_over("k")
        )
        flw["eol_management => reuse"][...] = reuse * self.constituent_split()
        flw["reuse => use"][...] = flw["eol_management => reuse"]

        # construction: covers the stock inflow not met by reuse
        flw["construction => use"][...] = stk["use"].inflow - flw["reuse => use"]
        flw["cement_market => construction"][...] = flw["construction => use"][{"k": "Cement"}]
        flw["sysenv => construction"][...] = flw["construction => use"][{"k": "Non-Cement"}]
        flw["cement_market => sysenv"][...] = (
            flw["cement_market => construction"]
            * prm["cement_losses"]
            / (1 - prm["cement_losses"])  # construction losses are relative to total cement use
        )

        # disposal: the non-reused demolished material accumulates in the eol waste stock
        flw["eol_management => eol_waste"][...] = (
            flw["use => eol_management"] - flw["eol_management => reuse"]
        )
        stk["eol_waste"].inflow[...] = flw["eol_management => eol_waste"]
        stk["eol_waste"].compute()

        # cement trade
        total_cement_demand = flw["cement_market => construction"] + flw["cement_market => sysenv"]
        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["cement"],
            future_trade=trd["cement"],
            future_dom_demand=total_cement_demand,
            trade_factor=prm["trade_factor"],
        )
        extrapolator.run()
        flw["cement_market => exports"][...] = trd["cement"].exports
        flw["imports => cement_market"][...] = trd["cement"].imports

        # cement production
        flw["cement_production => cement_market"][...] = (
            flw["cement_market => construction"]
            + flw["cement_market => sysenv"]
            + trd["cement"].net_exports
        )
        flw["clinker_market => cement_production"][...] = (
            flw["cement_production => cement_market"] * prm["clinker_ratio"]
        )
        flw["sysenv => cement_production"][...] = flw["cement_production => cement_market"] * (
            1 - prm["clinker_ratio"]
        )

        # clinker trade
        self.cap_historical_net_imports_to_demand(
            trade=historical_trade["clinker"],
            demand=flw["clinker_market => cement_production"],
        )
        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["clinker"],
            future_trade=trd["clinker"],
            future_dom_demand=flw["clinker_market => cement_production"],
            trade_factor=prm["trade_factor"],
        )
        extrapolator.run()
        flw["imports => clinker_market"][...] = trd["clinker"].imports
        flw["clinker_market => exports"][...] = trd["clinker"].exports

        # clinker production
        flw["clinker_production => clinker_market"][...] = (
            flw["clinker_market => cement_production"] + trd["clinker"].net_exports
        )
        # net cement kiln dust generation
        flw["clinker_production => sysenv"][...] = (
            flw["clinker_production => clinker_market"] * prm["clinker_losses"]
        )
        flw["sysenv => clinker_production"][...] = (
            flw["clinker_production => clinker_market"] + flw["clinker_production => sysenv"]
        )

        # balance trade with sysenv
        flw["exports => sysenv"][...] = (
            flw["cement_market => exports"] + flw["clinker_market => exports"]
        )
        flw["sysenv => imports"][...] = (
            flw["imports => cement_market"] + flw["imports => clinker_market"]
        )
