import flodym as fd

from remind_mfa.plastics.plastics_config import PlasticsCfg


class PlasticsMFASystemHistoric(fd.MFASystem):

    cfg: PlasticsCfg

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_historic_stock()
        self.compute_trade()
        # will throw an error because flows are empty
        # self.check_mass_balance()
        # self.check_flows(no_error=True)

    def compute_historic_stock(self):
        self.stocks["in_use_historic"].inflow[...] = self.parameters["consumption"]
        self.stocks["in_use_historic"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"], std=self.parameters["lifetime_std"]
        )
        self.stocks["in_use_historic"].compute()

    def compute_trade(self):

        for name, trade in self.trade_set.markets.items():
            if name.endswith("_his"):
                trade.imports[...] = self.parameters[f"{name}_imports"]
                trade.exports[...] = self.parameters[f"{name}_exports"]
        self.trade_set.balance(to="maximum")
