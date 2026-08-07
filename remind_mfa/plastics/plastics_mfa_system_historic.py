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
        self.cap_net_exports_to_supply("primary_his", flw["polymerization => primary_market"])

        flw["primary_market => fabrication"][...] = (
            flw["polymerization => primary_market"] + trd["primary_his"].net_imports
        )
        flw["fabrication => good_market"][...] = flw["primary_market => fabrication"]

        # final-goods net exports cannot exceed fabrication output, else use inflow goes negative
        self.cap_net_exports_to_supply("final_his", flw["fabrication => good_market"])

        flw["good_market => use"][...] = self.get_use_inflow_by_trade_adjusted_sector_polymer_split(flw["fabrication => good_market"])

        flw["primary_market => sysenv"][...] = trd["primary_his"].exports
        flw["sysenv => primary_market"][...] = trd["primary_his"].imports
        flw["good_market => sysenv"][...] = trd["final_his"].exports
        flw["sysenv => good_market"][...] = trd["final_his"].imports

    def cap_net_exports_to_supply(self, trade_name: str, supply: fd.FlodymArray):
        """Cap a historic trade's *net* exports at the available domestic supply so downstream
        flows cannot go negative when historic net exports exceed domestic production, then
        re-balance globally. Gross exports may still exceed supply where they are covered by
        imports (stop-over / re-export trade), since fabrication inflow = supply + imports -
        exports only requires exports - imports <= supply.

        ``balance`` re-inflates the opposite (import) side and thereby partially reintroduces
        the violation, so the cap and balance are iterated to convergence.
        Warns with the region/polymer coordinates where net exports had to be reduced.
        """
        trd = self.trade_set
        tolerance = 100 * self._absolute_float_precision
        for iteration in range(50):
            exports = trd[trade_name].exports
            exports_total = trd[trade_name].exports.sum_to(supply.dims.letters)
            imports_total = trd[trade_name].imports.sum_to(supply.dims.letters)
            # net exports (exports - imports) may not exceed domestic supply
            net_export_excess = (exports_total - imports_total - supply).maximum(0)  # (h, r, p)
            if not (net_export_excess.values > tolerance).any():
                break
            if iteration == 0:
                coords = net_export_excess.items_where(lambda x: x > tolerance)  # rows (h, r, p)
                h_idx = net_export_excess.dims.letters.index("h")
                r_idx = net_export_excess.dims.letters.index("r")
                p_idx = net_export_excess.dims.letters.index("p")
                # plastic types and years affected per region
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
                eps = sys.float_info.epsilon
                net_exports = (exports_total - imports_total).maximum(0)
                excess_agg = net_export_excess.sum_to(("h", "r"))
                net_export_agg = net_exports.sum_to(("h", "r"))
                max_reduction = np.max((excess_agg / net_export_agg.maximum(eps)).values)
                logging.warning(
                    f"'{trade_name}': historic net exports exceed available domestic supply; "
                    f"scaled down {len(coords)} entries:\n{detail}"
                    f"\nNet exports reduced by up to {max_reduction:.0%} in a single region and year "
                    f"to cap them at domestic supply."
                )
            # reduce exports to min(exports, supply + imports); factor in [0, 1]
            export_factor = (exports_total - net_export_excess) / exports_total.maximum(
                sys.float_info.epsilon
            )
            trd[trade_name].exports[...] = exports * export_factor
            trd[trade_name].balance(to="minimum")
        else:
            logging.warning(f"'{trade_name}': net-export cap did not converge after 50 iterations.")

    def get_use_inflow_by_trade_adjusted_sector_polymer_split(
        self, fabrication_to_good_market_total: fd.FlodymArray
    ) -> fd.FlodymArray:
        """Distribute the good_market => use flow among the good & material categories
        Where possible, this is done by the sector polymer split parameter.
        However, the final trade may be larger then the flow for a single good & material category.
        The other good & material categories' inflow to the in-use stock must be reduced by these excess imports
        """
        # fmt: off
        total_use_inflow = fabrication_to_good_market_total + self.trade_set["final_his"].net_imports
        use_inflow_target = total_use_inflow * self.parameters["sector_polymer_split"]
        min_imports = self.trade_set["final_his"].net_imports.maximum(0)
        # imports exceeding the target values determined by the sector split for each good and material
        imports_excess_total = (min_imports - use_inflow_target).maximum(0).sum_over(("g", "m"))
        # remainder of the target values not covered by imports, which should be covered by domestic fabrication
        fabrication_domestic_excess = (use_inflow_target - min_imports).maximum(0)
        # total of this remainder
        fabrication_domestic_excess_total = fabrication_domestic_excess.sum_over(("g", "m"))
        # scale down such that the sum of the domestic fabrication is reduced by the sum of the excess imports
        # i.e. domestic fabrication for those good & material categories where the target consumption exceeds imports
        # is reduced by the factor that imports exceed the target consumption for the other good & material categories
        fabrication_domestic = fabrication_domestic_excess * (fabrication_domestic_excess_total - imports_excess_total) / fabrication_domestic_excess_total.maximum(sys.float_info.epsilon)
        # fmt: on
        return min_imports + fabrication_domestic

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
            values=(self.flows["good_market => use"].maximum(0))
            .sum_over(("p",))
            .get_shares_over(("m",))
            .values,
        )
        # get global good split from historic stock inflow
        self.parameters["global_good_shares_use_inflow"] = fd.Parameter(
            dims=self.dims["h", "g"],
            values=(self.flows["good_market => use"].maximum(0))
            .sum_over(("m", "r", "p"))
            .get_shares_over(("g",))
            .values,
        )
