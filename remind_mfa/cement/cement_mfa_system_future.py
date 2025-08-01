import numpy as np
import flodym as fd

from remind_mfa.common.assumptions_doc import add_assumption_doc


class StockDrivenCementMFASystem(fd.MFASystem):

    def compute(self, stock_projection: fd.FlodymArray):
        """
        Perform all computations for the MFA system.
        """
        self.compute_in_use_stock(stock_projection)
        self.compute_flows()
        self.compute_other_stocks()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_in_use_stock(self, stock_projection: fd.FlodymArray):
        prm = self.parameters
        stk = self.stocks

        stk["in_use"].stock = stock_projection / prm["cement_ratio"]
        
        stk["in_use"].lifetime_model.set_prms(
            mean=prm["future_use_lifetime_mean"],
            std=0.4 * prm["future_use_lifetime_mean"],
        )
        add_assumption_doc(
            type="expert guess",
            value=0.4,
            name="Standard deviation of future use lifetime",
            description="The standard deviation of the future use lifetime is set to 20 percent of the mean.",
        )
        stk["in_use"].compute()

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks

        # go backwards from in-use stock
        flw["prod_concrete => use"][...] = stk["in_use"].inflow
        add_assumption_doc(
            type="ad-hoc fix",
            name="Regional concrete production is actually apparent consumption.",
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

        flw["prod_cement => prod_concrete"][...] = (
            flw["prod_concrete => use"] * prm["cement_ratio"]
        )
        flw["prod_clinker => prod_cement"][...] = (
            flw["prod_cement => prod_concrete"] * prm["clinker_ratio"]
        )
        flw["sysenv => prod_clinker"][...] = flw[
            "prod_clinker => prod_cement"
        ]

        # sysenv flows for mass balance
        flw["sysenv => prod_cement"][...] = flw["prod_cement => prod_concrete"] * (
            1 - prm["clinker_ratio"]
        )
        flw["sysenv => prod_concrete"][...] = flw["prod_concrete => use"] * (
            1 - prm["cement_ratio"]
        )

    def compute_other_stocks(self):
        flw = self.flows
        stk = self.stocks

        flw["use => eol"][...] = stk["in_use"].outflow
        stk["eol"].inflow[...] = flw["use => eol"]
        stk["eol"].outflow[...] = fd.FlodymArray(dims=self.dims["t", "r", "s"])
        stk["eol"].compute()
        flw["eol => sysenv"][...] = stk["eol"].outflow
