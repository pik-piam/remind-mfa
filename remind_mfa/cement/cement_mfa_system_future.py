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
        self.check_flows(no_error=True)

    def compute_in_use_stock(self, stock_projection: fd.FlodymArray):
        prm = self.parameters
        stk = self.stocks

        stk["in_use"].stock = stock_projection
        stk["in_use"].lifetime_model.set_prms(
            mean=prm["future_use_lifetime_mean"],
            std=0.3 * prm["future_use_lifetime_mean"],
        )
        add_assumption_doc(
            type="expert guess",
            value=0.3,
            name="Standard deviation of future use lifetime",
            description="The standard deviation of the future use lifetime is set to 30 percent of the mean.",
        )
        stk["in_use"].compute()

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        stk = self.stocks

        # go backwards from in-use stock
        flw["concrete_production => use"][...] = stk["in_use"].inflow
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

        flw["cement_grinding => concrete_production"][...] = (
            flw["concrete_production => use"] * prm["cement_ratio"]
        )
        flw["clinker_production => cement_grinding"][...] = (
            flw["cement_grinding => concrete_production"] * prm["clinker_ratio"]
        )
        flw["raw_meal_preparation => clinker_production"][...] = flw[
            "clinker_production => cement_grinding"
        ]

        # sysenv flows for mass balance
        flw["sysenv => raw_meal_preparation"][...] = flw[
            "raw_meal_preparation => clinker_production"
        ]
        flw["sysenv => clinker_production"][...] = fd.FlodymArray(dims=self.dims["t", "r"])
        flw["sysenv => cement_grinding"][...] = flw["cement_grinding => concrete_production"] * (
            1 - prm["clinker_ratio"]
        )
        flw["sysenv => concrete_production"][...] = flw["concrete_production => use"] * (
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
