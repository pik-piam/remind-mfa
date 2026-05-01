import numpy as np
import flodym as fd

from remind_mfa.cement.cement_carbon_uptake_model import CementCarbonUptakeModel
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.trade_extrapolation import TradeExtrapolator


class StockDrivenCementMFASystem(CommonMFASystem):

    cfg: CementCfg

    def compute(self, stock_projection: fd.FlodymArray, historic_trade: TradeSet, **kwargs):
        """
        Perform all computations for the MFA system.
        """
        self.compute_in_use_stock(stock_projection, **kwargs)
        self.compute_flows(historic_trade)
        self.compute_other_stocks()
        if self.cfg.model_switches.carbonation:
            CementCarbonUptakeModel(mfa=self).compute_carbon_flow()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_in_use_stock(
        self, stock_projection: fd.FlodymArray, stock_is_cement: bool = True, **kwargs
    ):
        prm = self.parameters
        stk = self.stocks

        if stock_is_cement:
            # Input is cement stock (t, r, s): apply material split and convert to total product mass.
            product_stock = stock_projection * prm["product_material_split"] / prm["cement_ratio"]
        else:
            # Input is already product mass (t, r, s, m): just add k dim.
            product_stock = stock_projection
        stk["in_use"].stock = self.add_constituent_split(product_stock, prm)

        stk["in_use"].lifetime_model.set_prms(
            mean=prm["lifetime_mean"],
            std=prm["lifetime_std"],
        )
        stk["in_use"].compute()

        # TODO add this back in once no more negative flows
        # self.correct_negative_inflow("in_use", warn_small_negative=False)

    def add_constituent_split(
        self, product_stock: fd.FlodymArray, prm: dict[str, fd.FlodymArray]
    ) -> fd.FlodymArray:
        """Add the Material Constituent (k) dimension to a product stock (t, r, s, m).

        Splits into cement and non-cement using cement_ratio.
        Returns an array with dim_letters (t, r, s, m, k).
        """
        k_dim = fd.Dimension(
            name="Material Constituent", letter="k",
            items=["cement", "non-cement"], dtype=str,
        )
        constituent_dims = product_stock.dims.append(k_dim)
        constituent_stock = fd.FlodymArray(dims=constituent_dims)
        constituent_stock[{"k": "cement"}] = product_stock * prm["cement_ratio"]
        constituent_stock[{"k": "non-cement"}] = product_stock * (1 - prm["cement_ratio"])
        return constituent_stock
    
    def compute_flows(self, historic_trade: TradeSet):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        trd = self.trade_set

        # product production
        flw["prod_product => use"][...] = stk["in_use"].inflow
        flw["market_cement => prod_product"][...] = flw["prod_product => use"][{"k": "cement"}]
        flw["sysenv => prod_product"][...] = flw["prod_product => use"][{"k": "non-cement"}]

        # cement trade
        extrapolator = TradeExtrapolator(
            historic_trade=historic_trade["cement"],
            future_trade=trd["cement"],
            future_dom_demand=flw["market_cement => prod_product"].maximum(
                0
            ),  # TODO remove this once no more negative flows
        )
        extrapolator.run()
        flw["market_cement => exports"][...] = trd["cement"].exports
        flw["imports => market_cement"][...] = trd["cement"].imports

        # cement production
        flw["prod_cement => market_cement"][...] = (
            flw["market_cement => prod_product"] + trd["cement"].net_exports
        )
        flw["prod_cement => sysenv"][...] = (
            flw["prod_cement => market_cement"]
            * prm["cement_losses"]
            / (1 - prm["cement_losses"])  # losses are relative to total production
        )
        flw["market_clinker => prod_cement"][...] = (
            flw["prod_cement => market_cement"] + flw["prod_cement => sysenv"]
        ) * prm["clinker_ratio"]
        flw["sysenv => prod_cement"][...] = (
            flw["prod_cement => market_cement"] + flw["prod_cement => sysenv"]
        ) * (1 - prm["clinker_ratio"])

        # clinker trade
        extrapolator = TradeExtrapolator(
            historic_trade=historic_trade["clinker"],
            future_trade=trd["clinker"],
            future_dom_demand=flw["market_clinker => prod_cement"].maximum(
                0
            ),  # TODO remove this once no more negative flows
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

    def compute_other_stocks(self):
        flw = self.flows
        stk = self.stocks

        # eol
        flw["use => eol"][...] = stk["in_use"].outflow
        stk["eol"].inflow[...] = flw["use => eol"]
        stk["eol"].lifetime_model.set_prms(mean=np.inf)
        stk["eol"].compute()
        flw["eol => sysenv"][...] = stk["eol"].outflow
