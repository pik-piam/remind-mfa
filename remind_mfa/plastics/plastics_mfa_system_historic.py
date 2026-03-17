import flodym as fd

from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.common_mfa_system import CommonMFASystem


class PlasticsMFASystemHistoric(CommonMFASystem):

    cfg: PlasticsCfg

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.fill_trade()
        self.compute_flows()
        self.compute_historic_stock()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        trd = self.trade_set

        flw["sysenv => fabrication"][...] = (
            prm["consumption"] * self.parameters["material_shares_in_goods"]
        )

        # exports of final goods cannot exceed plastics fabrication
        trd["final_his"].exports[...] = trd["final_his"].exports.minimum(
            flw["sysenv => fabrication"]
        )
        trd["final_his"].balance(to="minimum")

        flw["fabrication => good_market"][...] = flw["sysenv => fabrication"]
        flw["good_market => use"][...] = (
            flw["fabrication => good_market"] - trd["final_his"].exports + trd["final_his"].imports
        )
        flw["good_market => sysenv"][...] = trd["final_his"].exports
        flw["sysenv => good_market"][...] = trd["final_his"].imports

    def compute_historic_stock(self):
        self.stocks["in_use_historic"].inflow[...] = self.flows["good_market => use"]
        self.stocks["in_use_historic"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"][{"t": self.dims["h"]}],
            std=self.parameters["lifetime_std"],
        )
        # We use a higher number of points for the lifetime model than the default because packaging lifetimes are < 1 year
        self.stocks["in_use_historic"].lifetime_model.n_pts_per_interval = 10
        self.stocks["in_use_historic"].compute()
        self.flows["use => sysenv"][...] += self.stocks["in_use_historic"].outflow

        # get material split from historic stock inflow
        self.parameters["material_shares_use_inflow"] = fd.Parameter(
            dims=self.dims["h", "r", "m", "g"],
            values=(self.flows["good_market => use"]).get_shares_over(("m",)).values,
        )
        # get good split from historic stock inflow
        self.parameters["good_shares_use_inflow"] = fd.Parameter(
            dims=self.dims["r", "g"],
            values=(self.flows["good_market => use"])
            .sum_over(
                (
                    "h",
                    "m",
                )
            )
            .get_shares_over(("g",))
            .values,
        )
