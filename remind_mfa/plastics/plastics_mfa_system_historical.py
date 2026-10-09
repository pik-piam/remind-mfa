import flodym as fd
import numpy as np

from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.common_mfa_system import CommonMFASystem


class PlasticsMFASystemHistorical(CommonMFASystem):

    cfg: PlasticsCfg

    def compute(self):
        """
        Perform all computations for the MFA system.
        """
        self.fill_trade()
        self.trade_set.balance(to="maximum")
        self.compute_flows()
        self.compute_historical_stock()
        self.check_mass_balance(raise_error=True)
        self.check_flows(raise_error=False)

    def compute_flows(self):
        prm = self.parameters
        flw = self.flows
        trd = self.trade_set

        flw["sysenv => polymerization"][...] = prm["production"]
        flw["polymerization => primary_market"][...] = flw["sysenv => polymerization"]

        # primary net exports are capped to not exceed domestic production, else manufacturing inflow goes negative
        self.cap_historical_net_exports_to_supply(
            trd["primary"], flw["polymerization => primary_market"]
        )

        flw["primary_market => manufacturing"][...] = (
            flw["polymerization => primary_market"] + trd["primary"].net_imports
        )
        flw["manufacturing => manufactured_products_market"][...] = flw[
            "primary_market => manufacturing"
        ]

        # manufactured products net exports (per end use and material) are capped to not exceed manufacturing supply
        # stop-over trade is allowed, but positive net imports of one end use cannot be balanced by re-exporting a different end use
        self.cap_historical_net_exports_to_supply(
            trd["manufactured_products"], flw["manufacturing => manufactured_products_market"]
        )

        # distribute the manufactured_products_market => use flow among the end use & material categories
        flw["manufactured_products_market => use"][...] = (
            self.get_historical_use_inflow_by_trade_adjusted_split(
                "manufactured_products",
                flw["manufacturing => manufactured_products_market"],
                prm["end_use_polymer_split"],
                ("u", "m"),
            )
        )

        flw["primary_market => sysenv"][...] = trd["primary"].exports
        flw["sysenv => primary_market"][...] = trd["primary"].imports
        flw["manufactured_products_market => sysenv"][...] = trd["manufactured_products"].exports
        flw["sysenv => manufactured_products_market"][...] = trd["manufactured_products"].imports

    def compute_historical_stock(self):
        self.stocks["use"].inflow[...] = self.flows["manufactured_products_market => use"]
        self.stocks["use"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"][{"t": self.dims["h"]}],
            std=self.parameters["lifetime_std"][{"t": self.dims["h"]}],
        )
        # We use a higher number of points for the lifetime model than the default because packaging lifetimes are < 1 year
        self.stocks["use"].lifetime_model.n_pts_per_interval = 10
        self.stocks["use"].compute()
        self.flows["use => sysenv"][...] += self.stocks["use"].outflow

        # get material split from historical stock inflow for use in the future MFA, which does not
        # carry the polymer type dimension 'p' (each material belongs to exactly one type).
        # Shares sum to 1 across all materials.
        with np.errstate(divide="ignore"):
            self.parameters["material_shares_use_inflow"] = fd.Parameter(
                dims=self.dims["h", "r", "m", "u"],
                values=(self.flows["manufactured_products_market => use"].maximum(0))
                .sum_over("p")
                .get_shares_over(("m",))
                .values,
            )
        # country-level (iso249) runs have (r, u) cells with zero inflow -> 0/0 = NaN shares; zero them
        self.parameters["material_shares_use_inflow"].apply(np.nan_to_num, inplace=True)
        # get global end use split from historical stock inflow
        self.parameters["global_end_use_shares_use_inflow"] = fd.Parameter(
            dims=self.dims["h", "u"],
            values=(self.flows["manufactured_products_market => use"].maximum(0))
            .sum_over(("m", "r", "p"))
            .get_shares_over(("u",))
            .values,
        )
