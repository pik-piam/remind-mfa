import flodym as fd

from remind_mfa.plastics.plastics_config import PlasticsCfg


class PlasticsMFASystemHistoric(fd.MFASystem):

    cfg: PlasticsCfg

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.compute_trade()
        self.compute_flows()
        self.compute_historic_stock()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_trade(self):

        for name, trade in self.trade_set.markets.items():
            if name.endswith("_his"):
                trade.imports[...] = self.parameters[f"{name}_imports"]
                trade.exports[...] = self.parameters[f"{name}_exports"]
        self.trade_set.balance(to="minimum")

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        trd = self.trade_set

        flw["sysenv => fabrication"][...] = prm["consumption"] * self.parameters["material_shares_in_goods"]* self.parameters["carbon_content_materials"]
        flw["good_market => use"][...] = trd["final_his"].imports * self.parameters["carbon_content_materials"]
        flw["fabrication => good_market"][...] = trd["final_his"].exports * self.parameters["carbon_content_materials"]
        flw["sysenv => good_market"][...] = flw["good_market => use"]
        flw["good_market => sysenv"][...] = flw["fabrication => good_market"]

        flw["fabrication => use"][...] = flw["sysenv => fabrication"] - flw["fabrication => good_market"]

    def compute_historic_stock(self):
        self.stocks["in_use_historic"].inflow[...] = self.flows["good_market => use"] + self.flows["fabrication => use"]
        self.stocks["in_use_historic"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"], std=self.parameters["lifetime_std"]
        )
        self.stocks["in_use_historic"].compute()
        self.flows["use => sysenv"][...] += self.stocks["in_use_historic"].outflow
