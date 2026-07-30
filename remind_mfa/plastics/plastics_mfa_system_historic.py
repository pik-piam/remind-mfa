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
        self.trade_set.balance(to="maximum")
        self.compute_flows()
        self.compute_historic_stock()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        trd = self.trade_set

        flw["sysenv => polymerization"][...] = prm["production"]
        flw["polymerization => primary_market"][...] = flw["sysenv => polymerization"]
        flw["primary_market => fabrication"][...] = (
            flw["polymerization => primary_market"] + trd["primary_his"].net_imports
        )
        flw["fabrication => good_market"][...] = flw["primary_market => fabrication"]

        # # exports of final goods cannot exceed plastics fabrication
        # trd["final_his"].exports[...] = trd["final_his"].exports.minimum(
        #     flw["sysenv => fabrication"]
        # )
        # trd["final_his"].balance(to="minimum")

        flw["good_market => use"][...] = (
            flw["fabrication => good_market"] + trd["final_his"].net_imports
        ) * prm["sector_polymer_split"]
        
        flw["primary_market => sysenv"][...] = trd["primary_his"].exports
        flw["sysenv => primary_market"][...] = trd["primary_his"].imports
        flw["good_market => sysenv"][...] = trd["final_his"].exports
        flw["sysenv => good_market"][...] = trd["final_his"].imports

    def compute_historic_stock(self):
        self.stocks["in_use_historic"].inflow[...] = self.flows["good_market => use"]
        self.stocks["in_use_historic"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"][{"t": self.dims["h"]}],
            std=self.parameters["lifetime_std"][{"t": self.dims["h"]}],
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
            dims=self.dims["h", "r", "g"],
            values=(self.flows["good_market => use"])
            .sum_over(("m",))
            .get_shares_over(("g",))
            .values,
        )
        # get global good split from historic stock inflow
        self.parameters["global_good_shares_use_inflow"] = fd.Parameter(
            dims=self.dims["h", "g"],
            values=(self.flows["good_market => use"])
            .sum_over(("m", "r"))
            .get_shares_over(("g",))
            .values,
        )
