import logging
import sys
import flodym as fd
import numpy as np

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

        # primary exports cannot exceed domestic production, else fabrication inflow goes negative
        self.scale_trade_exports_to_supply("primary_his", flw["polymerization => primary_market"])

        flw["primary_market => fabrication"][...] = (
            flw["polymerization => primary_market"] + trd["primary_his"].net_imports
        )
        flw["fabrication => good_market"][...] = flw["primary_market => fabrication"]

        # final-goods exports cannot exceed fabrication output, else use inflow goes negative
        self.scale_trade_exports_to_supply("final_his", flw["fabrication => good_market"])

        flw["good_market => use"][...] = (
            flw["fabrication => good_market"] + trd["final_his"].net_imports
        ) * prm["sector_polymer_split"]

        flw["primary_market => sysenv"][...] = trd["primary_his"].exports
        flw["sysenv => primary_market"][...] = trd["primary_his"].imports
        flw["good_market => sysenv"][...] = trd["final_his"].exports
        flw["sysenv => good_market"][...] = trd["final_his"].imports

    def scale_trade_exports_to_supply(self, trade_name: str, supply: fd.FlodymArray):
        """Cap a historic trade's exports at the available domestic supply so downstream
        flows cannot go negative when historic export data exceeds domestic production,
        then re-balance globally. 
        Warns with the region/polymer coordinates where exports had to be reduced.
        """
        trd = self.trade_set
        exports = trd[trade_name].exports
        exports_total = trd[trade_name].exports.sum_to(supply.dims.letters)
        export_factor = exports_total.minimum(supply) / exports_total.maximum(sys.float_info.epsilon)
        capped = exports * export_factor
        excess = exports - capped  # > 0 where exports exceeded supply
        if (excess.values > 0.0).any():
            coords = excess.items_where(lambda x: x > 0.0)  # rows over excess.dims
            h_idx = excess.dims.letters.index("h")
            r_idx = excess.dims.letters.index("r")
            p_idx = excess.dims.letters.index("p")
            # collapse other dims -> plastic types and years affected per region
            by_region = {}
            for row in coords:
                types, years = by_region.setdefault(str(row[r_idx]), (set(), set()))
                types.add(str(row[p_idx]))
                years.add(int(row[h_idx]))
            detail = "\n".join(
                f"    {region}: {', '.join(sorted(types))}; "
                f"{', '.join(str(y) for y in sorted(years))}"
                for region, (types, years) in sorted(by_region.items())
            )
            supply_agg = supply.sum_to(("h", "r"))
            excess_agg = excess.sum_to(("h", "r"))
            export_agg = exports.sum_to(("h", "r"))
            export_factor_max = np.max((excess_agg / export_agg).values)
            excess_share_max = np.max((excess_agg / supply_agg).values)
            logging.warning(
                f"'{trade_name}': historic exports exceed available domestic supply; "
                f"scaled down {len(coords)} entries:\n{detail}"
                f"\nMaximum downscaling factor of total exports within a year and region: {export_factor_max:.2f}"
                f"\nMaximum share of excess of total supply within a year: {excess_share_max:.2f}"
            )
        trd[trade_name].exports[...] = capped
        trd[trade_name].balance(to="minimum")

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
