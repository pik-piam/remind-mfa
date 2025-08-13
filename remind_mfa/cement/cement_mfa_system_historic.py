import flodym as fd

from remind_mfa.common.assumptions_doc import add_assumption_doc


class InflowDrivenHistoricCementMFASystem(fd.MFASystem):

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_in_use_stock()
        self.compute_flows()
        self.check_mass_balance()
        self.check_flows()

    def compute_in_use_stock(self):
        prm = self.parameters
        stk = self.stocks
        cement_consumption = (1 - prm["cement_losses"]) * (prm["cement_production"] - prm["cement_trade"])

        # in use
        stk["historic_cement_in_use"].inflow[...] = (
            cement_consumption * prm["stock_type_split"]
        )
        stk["historic_cement_in_use"].lifetime_model.set_prms(
            mean=prm["historic_use_lifetime_mean"],
            std=0.4 * prm["historic_use_lifetime_mean"],
        )
        add_assumption_doc(
            type="expert guess",
            value=0.4,
            name="Standard deviation of historic use lifetime",
            description="The standard deviation of the historic use lifetime is set to 20 percent of the mean.",
        )
        stk["historic_cement_in_use"].compute()

    def compute_flows(self):
        flw = self.flows
        stk = self.stocks

        flw["sysenv => use"][...] = stk["historic_cement_in_use"].inflow
        flw["use => sysenv"][...] = stk["historic_cement_in_use"].outflow
