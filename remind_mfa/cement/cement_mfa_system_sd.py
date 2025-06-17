import flodym as fd

from remind_mfa.common.assumptions_doc import add_assumption_doc


class StockDrivenSDcementMFASystem(fd.MFASystem):

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_in_use_stock()
        self.compute_flows()
        self.check_mass_balance()
        self.check_flows()

    def compute_in_use_stock(self, stock_projection: fd.FlodymArray):
        prm = self.parameters
        stk = self.stocks

        stk["in_use"].stock = prm["buildings_floorspace"] * prm["building_split"] * prm["concrete_building_mi"]
        stk["in_use"].lifetime_model.set_prms(
            mean=prm["future_use_lifetime_mean"],
            std=0.2 * prm["future_use_lifetime_mean"],
        )
        add_assumption_doc(
            type="expert guess",
            value=0.2,
            name="Standard deviation of future use lifetime",
            description="The standard deviation of the future use lifetime is set to 20 percent of the mean.",
        )
        stk["in_use"].compute()

    def compute_flows(self):
        flw = self.flows
        stk = self.stocks

        flw["sysenv => use"][...] = stk["historic_in_use"].inflow
        flw["use => sysenv"][...] = stk["historic_in_use"].outflow
