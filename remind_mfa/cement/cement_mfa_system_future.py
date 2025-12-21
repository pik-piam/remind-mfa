import numpy as np
import flodym as fd

from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.cement.cement_carbon_uptake_model import CementCarbonUptakeModel
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.trade import TradeSet


class StockDrivenCementMFASystem(CommonMFASystem):

    cfg: CementCfg

    def compute(self, stock_projection: fd.FlodymArray, historic_trade: TradeSet):
        """
        Perform all computations for the MFA system.
        """
        self.cement_ratio = (
            self.parameters["product_cement_content"] / self.parameters["product_density"]
        )

        self.compute_in_use_stock(stock_projection)
        self.compute_flows()
        self.compute_other_stocks()
        if self.cfg.model_switches.carbon_flow:
            CementCarbonUptakeModel(mfa=self).compute_carbon_flow()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_in_use_stock(self, cement_stock_projection: fd.FlodymArray):
        prm = self.parameters
        stk = self.stocks

        # transform historic cement stock into product stock
        stk["in_use"].stock = (
            cement_stock_projection
            * prm["product_material_split"]
            * prm["product_material_application_transform"]
            * prm["product_application_split"]
            / self.cement_ratio
        )

        lifetime_rel_std = 0.4
        add_assumption_doc(
            type="expert guess",
            value=lifetime_rel_std,
            name="Standard deviation of future use lifetime",
            description=f"The standard deviation of the future use lifetime is set to {int(lifetime_rel_std * 100)} percent of the mean.",
        )
        stk["in_use"].lifetime_model.set_prms(
            mean=prm["use_lifetime_mean"],
            std=lifetime_rel_std * prm["use_lifetime_mean"],
        )
        stk["in_use"].compute()

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks

        # go backwards from in-use stock
        flw["prod_product => use"][...] = stk["in_use"].inflow

        add_assumption_doc(
            type="ad-hoc fix",
            name="Regional product production is actually apparent consumption.",
            description=(
                "The concrete stock considers both cement production and trade. "
                "The concrete production is constructed by concrete stock. "
                "The regional concrete production does not consider trade, "
                "therefore, it is actually apparent consumption. "
                "With this fix, we do not have any regional production jumps "
                "between historical and future data, as trade is not yet modeled in the future."
                "This fix propagates through to cement and clinker production."
            ),
        )

        flw["prod_cement => prod_product"][...] = flw["prod_product => use"] * self.cement_ratio
        # cement losses are on top of the inflow of stock, but are relative to total cement production
        flw["prod_cement => sysenv"][...] = flw["prod_cement => prod_product"] * (
            prm["cement_losses"] / (1 - prm["cement_losses"])
        )
        # clinker production is based on cement production
        flw["prod_clinker => prod_cement"][...] = (
            flw["prod_cement => prod_product"] + flw["prod_cement => sysenv"]
        ) * prm["clinker_ratio"]
        # clinker losses (CKD) are on top of clinker production.
        flw["prod_clinker => sysenv"][...] = (
            flw["prod_clinker => prod_cement"] * prm["clinker_losses"]
        )

        # sysenv flows for mass balance
        flw["sysenv => prod_clinker"][...] = (
            flw["prod_clinker => prod_cement"] + flw["prod_clinker => sysenv"]
        )
        flw["sysenv => prod_cement"][...] = (
            flw["prod_cement => prod_product"] + flw["prod_cement => sysenv"]
        ) * (1 - prm["clinker_ratio"])
        flw["sysenv => prod_product"][...] = flw["prod_product => use"] * (1 - self.cement_ratio)

    def compute_other_stocks(self):
        flw = self.flows
        stk = self.stocks

        # eol
        flw["use => eol"][...] = stk["in_use"].outflow
        stk["eol"].inflow[...] = flw["use => eol"]
        stk["eol"].lifetime_model.set_prms(mean=np.inf)
        stk["eol"].compute()
        flw["eol => sysenv"][...] = stk["eol"].outflow
