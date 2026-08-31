import flodym as fd
import numpy as np
import logging
import sys

from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.trade import TradeSet, Trade
from remind_mfa.common.trade_extrapolation import TradeExtrapolator
from remind_mfa.plastics.plastics_config import PlasticsCfg


class PlasticsMFASystemFuture(CommonMFASystem):

    cfg: PlasticsCfg

    def compute(self, stock_projection: fd.FlodymArray, historic_trade: TradeSet):
        """
        Perform all computations for the MFA system.
        """
        self.compute_stock(stock_projection)
        self.compute_waste_trade()
        self.compute_flows(historic_trade)
        self.compute_other_stocks()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_waste_trade(self):
        # waste trade is extrapolated as a scenario parameter, therefore it is not filled in the historic MFA system

        self.trade_set["waste"].imports[...] = (
            self.parameters[f"waste_his_imports"] * self.parameters["carbon_content_materials"]
        )
        self.trade_set["waste"].exports[...] = (
            self.parameters[f"waste_his_exports"] * self.parameters["carbon_content_materials"]
        )
        self.trade_set.balance(to="maximum")

    def compute_stock(self, stock_projection: fd.FlodymArray):
        self.stocks["in_use_dsm"].stock[...] = stock_projection
        self.stocks["in_use_dsm"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"],
            std=self.parameters["lifetime_std"],
        )
        # We use a higher number of points for the lifetime model than the default because packaging lifetimes are < 1 year
        self.stocks["in_use_dsm"].lifetime_model.n_pts_per_interval = 10
        self.stocks["in_use_dsm"].compute()
        self.correct_negative_inflow("in_use_dsm")

        # We use an auxiliary stock for the prediction step to save dimensions and computation time
        # Therefore, we have to transfer the result to the higher-dimensional stock in the MFA system
        split = (
            self.parameters["material_shares_use_inflow"]
            * self.parameters["carbon_content_materials"]
        )
        self.stocks["in_use"].stock[...] = self.stocks["in_use_dsm"].stock * split
        self.stocks["in_use"].inflow[...] = self.stocks["in_use_dsm"].inflow * split
        self.stocks["in_use"].outflow[...] = self.stocks["in_use_dsm"].outflow * split

    def compute_flows(self, historic_trade: TradeSet):

        # abbreviations for better readability
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        trd = self.trade_set

        aux = {
            "net_other_polymerization_input": self.get_new_array(dim_letters=("t", "e", "r")),
            "upstream_losses": self.get_new_array(dim_letters=("t", "e", "r")),
            "total_polymerization_feed": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "total_primary_HVC": self.get_new_array(dim_letters=("t", "e", "r")),
            "total_waste_collected": self.get_new_array(dim_letters=("t", "e", "r", "p", "m")),
            "reclmech_loss": self.get_new_array(dim_letters=("t", "e", "r", "p", "m")),
            "HVC_c_content": self.get_new_array(dim_letters=("t", "e", "r")),
            "HVC_ratio_nonc_to_c": self.get_new_array(dim_letters=("t", "r")),
        }

        # fmt: off

        # EoL flows are computed first, starting from the stock outflow, since recycling flows are needed for the trade extrapolation
        flw["use => eol"][...] = stk["in_use"].outflow
        flw["eol => collected"][...] = flw["use => eol"] * prm["collection_rate"]

        # exports of plastic waste cannot exceed collected eol plastics
        trd["waste"].exports[...] = trd["waste"].exports.minimum(flw["eol => collected"])
        trd["waste"].balance(to="minimum")

        flw["waste_market => collected"][...] = trd["waste"].imports
        flw["collected => waste_market"][...] = trd["waste"].exports
        flw["imports => waste_market"][...] = flw["waste_market => collected"]
        flw["waste_market => exports"][...] = flw["collected => waste_market"]

        aux["total_waste_collected"][...] = flw["eol => collected"] + flw["waste_market => collected"] - flw["collected => waste_market"]
        flw["collected => reclmech"][...] = aux["total_waste_collected"] * prm["mechanical_recycling_rate"]
        flw["collected => reclmech"][{"m": ("Rubbers","PET fibre", "Polyamide fibre", "Other fibre")}] = 0.0 # TODO remove once recycling rates are resolved by material
        flw["reclmech => primary_market"][...] = flw["collected => reclmech"] * prm["mechanical_recycling_yield"]
        aux["reclmech_loss"][...] = flw["collected => reclmech"] - flw["reclmech => primary_market"]
        flw["reclmech => uncontrolled"][...] = aux["reclmech_loss"] * prm["reclmech_loss_uncontrolled_rate"]
        flw["reclmech => incineration"][...] = aux["reclmech_loss"] - flw["reclmech => uncontrolled"]

        flw["collected => reclchem"][...] = aux["total_waste_collected"] * prm["chemical_recycling_rate"]

        flw["collected => landfill"][...] = aux["total_waste_collected"] * prm["landfill_rate"]

        flw["collected => incineration"][...] = (
            aux["total_waste_collected"]
            - flw["collected => reclmech"]
            - flw["collected => reclchem"]
            - flw["collected => landfill"]
        )
        flw["incineration => emission"][...] = flw["collected => incineration"] + flw["reclmech => incineration"]

        flw["eol => mismanaged"][...] = flw["use => eol"] - flw["eol => collected"]
        flw["mismanaged => uncontrolled"][...] = flw["eol => mismanaged"]

        # now trades and production flows are computed starting from the stock inflow
        flw["good_market => use"][...] = stk["in_use"].inflow

        extrapolator = TradeExtrapolator(
            historic_trade=historic_trade["final_his"],
            future_trade=self.trade_set["final"],
            future_dom_demand=stk["in_use"].inflow,
        )
        extrapolator.run()

        flw["good_market => exports"][...] = (
            trd["final"].exports * self.parameters["carbon_content_materials"]
        )
        flw["imports => good_market"][...] = (
            trd["final"].imports * self.parameters["carbon_content_materials"]
        )
        flw["fabrication => good_market"][...] = flw["good_market => use"] - flw["imports => good_market"] + flw["good_market => exports"]

        # a material's net imports above its fabrication demand would make its primary production
        # negative; reassign that excess to the other materials of the same polymer type (headroom),
        # keeping the trade's material split
        flw["primary_market => fabrication"][...] = flw["fabrication => good_market"]
        self._redistribute_primary_import_excess_within_type(
            historic_trade["primary_his"], flw["primary_market => fabrication"]
        )

        extrapolator = TradeExtrapolator(
            historic_trade=historic_trade["primary_his"],
            future_trade=self.trade_set["primary"],
            future_dom_demand=flw["primary_market => fabrication"],
        )
        extrapolator.run()
        # net exports of plastics should be at least the secondary production from mechanical recycling minus domestic plastics demand.
        self._adjust_primary_trade_for_secondary_excess(flw, trd)

        flw["primary_market => exports"][...] = (
            trd["primary"].exports * self.parameters["carbon_content_materials"]
        )
        flw["imports => primary_market"][...] = (
            trd["primary"].imports * self.parameters["carbon_content_materials"]
        )

        flw["polymerization => primary_market"][...] = (
            flw["primary_market => fabrication"]
            - flw["imports => primary_market"]
            + flw["primary_market => exports"]
            - flw["reclmech => primary_market"]
        )

        aux["total_polymerization_feed"][...] = flw["polymerization => primary_market"] / prm["polymerization_yield"]
        flw["HVC_input => polymerization"][...] = aux["total_polymerization_feed"].sum_to(("t", "r", "m")) * prm["HVC_input_ratio"]
        flw["C4_input => polymerization"][...] = aux["total_polymerization_feed"].sum_to(("t", "r", "m")) * prm["C4_input_ratio"]
        aux["net_other_polymerization_input"] = aux["total_polymerization_feed"] - flw["HVC_input => polymerization"] - flw["C4_input => polymerization"] # this is all input to polymerization that is not total HVC or C4 input - can be positive because of other reactants or negative because of upstream losses (e.g. for production of styrene from ethylene and benzene)
        flw["other_reactants => polymerization"][...] = aux["net_other_polymerization_input"].maximum(0) # the positive part is counted as other reactants input
        aux["upstream_losses"][...] = - aux["net_other_polymerization_input"].minimum(0) # the negative part is counted as upstream losses
        flw["polymerization => losses"][...] = aux["total_polymerization_feed"] - flw["polymerization => primary_market"] + aux["upstream_losses"]
        flw["losses => sysenv"][...] = flw["polymerization => losses"]
        aux["HVC_c_content"][...] = flw["HVC_input => polymerization"] / flw["HVC_input => polymerization"].sum_to(("t", "r"))

        # chemical recycling
        flw["reclchem => HVC_input"][...] = flw["collected => reclchem"].sum_to(("t", "r")) * aux["HVC_c_content"] * prm["chemical_recycling_yield"] # TODO: differentiate yield by element instead of using C content of HVC!
        flw["reclchem => emission"][...] = flw["collected => reclchem"] - flw["reclchem => HVC_input"]
        aux["total_primary_HVC"][...] = flw["HVC_input => polymerization"] - flw["reclchem => HVC_input"]

        # carbon cycles via bio daccu feedstocks
        flw["feeddaccu => HVC_input"][...] = aux["total_primary_HVC"] * prm["daccu_production_rate"]
        flw["feedbio => HVC_input"][...] = aux["total_primary_HVC"] * prm["bio_production_rate"]

        # captured emissions and ccu feedstocks
        # non-C atmosphere & captured has no meaning & is equivalent to sysenv
        flw["emission => captured"][...] = (flw["incineration => emission"] + flw["reclchem => emission"]) * prm["emission_capture_rate"]
        flw["emission => atmosphere"][...] = flw["incineration => emission"] + flw["reclchem => emission"] - flw["emission => captured"]
        flw["captured => feedccu"][...] = flw["emission => captured"]
        # non-C of CCU HVC production has to be calculated based on the same ratio as in overall HVC production
        aux["HVC_ratio_nonc_to_c"][...] = aux["total_primary_HVC"]["Other Elements"] / aux["total_primary_HVC"]["C"]
        flw["feedccu => HVC_input"]["C"] = flw["captured => feedccu"]["C"]
        flw["feedccu => HVC_input"]["Other Elements"] = flw["feedccu => HVC_input"]["C"] * aux["HVC_ratio_nonc_to_c"]
        flw["feedfoss => HVC_input"][...] = (
            aux["total_primary_HVC"]
            - flw["feeddaccu => HVC_input"]
            - flw["feedbio => HVC_input"]
            - flw["feedccu => HVC_input"]
        )

        flw["sysenv => C4_input"][...] = flw["C4_input => polymerization"]
        flw["sysenv => other_reactants"][...] = flw["other_reactants => polymerization"]
        flw["sysenv => feedfoss"][...] = flw["feedfoss => HVC_input"]
        flw["atmosphere => feedbio"][...] = flw["feedbio => HVC_input"]
        flw["atmosphere => feeddaccu"][...] = flw["feeddaccu => HVC_input"]
        flw["sysenv => feedccu"][...] = flw["feedccu => HVC_input"] - flw["captured => feedccu"]
        flw["sysenv => imports"][...] = flw["imports => good_market"] + flw["imports => primary_market"] + flw["imports => waste_market"]
        flw["exports => sysenv"][...] = flw["good_market => exports"] + flw["primary_market => exports"] + flw["waste_market => exports"]

        # fmt: on

    def _redistribute_primary_import_excess_within_type(
        self, historic_trade: Trade, demand: fd.FlodymArray
    ):
        """Keep the historic primary trade's material split, but move the *excess* net imports of any
        material (the part above its fabrication demand) onto the other materials of the same polymer
        type that have headroom, so backward-computed production per material cannot go negative.
        """
        eps = sys.float_info.epsilon
        tolerance = 100 * self._absolute_float_precision
        demand = demand[{"t": self.dims["h"]}].sum_over("e").maximum(0)  # (h, r, p, m)

        imp = historic_trade.imports  # (h, r, p, m)
        net = historic_trade.net_imports

        excess = (net - demand).maximum(0)  # (h, r, p, m)
        headroom = (demand - net).maximum(0)  # (h, r, p, m)
        excess_type = excess.sum_over("m")  # (h, r, p)
        headroom_type = headroom.sum_over("m")  # (h, r, p)

        fill = headroom * (excess_type / headroom_type.maximum(eps)).minimum(1)  # (h, r, p, m)
        historic_trade.imports[...] = imp - excess + fill  # exports unchanged

        # warn where the type's excess could not be fully reassigned (net imports capped at demand)
        residual = (excess_type - headroom_type).maximum(0)  # (h, r, p)
        if (residual.values > tolerance).any():
            coords = residual.items_where(lambda x: x > tolerance)  # rows (h, r, p)
            h_idx = residual.dims.letters.index("h")
            r_idx = residual.dims.letters.index("r")
            p_idx = residual.dims.letters.index("p")
            # polymer types and years affected per region
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
            net_import_agg = net.maximum(0).sum_to(("h", "r"))
            max_reduction = np.max(
                (residual.sum_to(("h", "r")) / net_import_agg.maximum(eps)).values
            )
            logging.warning(
                f"Primary net imports exceed fabrication demand and could not be reassigned within "
                f"the polymer type; capped {len(coords)} entries at demand:\n{detail}"
                f"\nNet imports reduced by up to {max_reduction:.0%} in a single region and year."
            )

    def _adjust_primary_trade_for_secondary_excess(self, flw, trd):
        """
        Iteratively adjust primary plastics trade so that no region has more
        secondary material available than its primary demand plus net exports.

        Each iteration splits the per-region excess between an import reduction
        and an export increase proportional to each region's share of total trade:
            import share  = imports  / (imports + exports)
            export share  = exports  / (imports + exports)

        balance() is called after every adjustment to restore global trade
        balance, which partially re-introduces a residual excess — hence the
        loop.  Convergence is guaranteed because each iteration strictly
        reduces the excess.
        """
        secondary_excess = self.get_new_array(dim_letters=("t", "r", "m"))
        for iteration in range(20):
            secondary_excess[...] = (
                flw["reclmech => primary_market"]
                - flw["primary_market => fabrication"]
                - trd["primary"].net_exports
            )
            excess = secondary_excess.maximum(0)
            if not np.any(excess.values > 1e-6):
                break
            if iteration == 0:
                coords = secondary_excess.items_where(lambda x: x > 1e-6)  # rows over excess.dims
                h_idx = secondary_excess.dims.letters.index("t")
                r_idx = secondary_excess.dims.letters.index("r")
                m_idx = secondary_excess.dims.letters.index("m")
                # materials and years affected per region
                by_region = {}
                for row in coords:
                    materials, years = by_region.setdefault(str(row[r_idx]), (set(), set()))
                    materials.add(str(row[m_idx]))
                    years.add(int(row[h_idx]))
                detail = "\n".join(
                    f"    {region}: {', '.join(sorted(materials))}; "
                    f"{', '.join(str(y) for y in sorted(years))}"
                    for region, (materials, years) in sorted(by_region.items())
                )
                logging.warning(
                    f"There is more secondary plastics available than used; "
                    f"{len(coords)} entries:\n{detail}"
                )
            eps = sys.float_info.epsilon
            total_trade = trd["primary"].imports + trd["primary"].exports
            import_share = trd["primary"].imports / total_trade.maximum(eps)
            import_reduction = (excess * import_share).minimum(trd["primary"].imports)
            trd["primary"].imports[...] = trd["primary"].imports - import_reduction
            # The trade arrays carry the coarse type dimension "p" (Fibre/Rubber/Plastics) on top of
            # the material dimension "m", while the flows (and therefore the excess) don't.
            export_increase_m = excess - import_reduction.sum_over("p")
            export_p_share = trd["primary"].exports / trd["primary"].exports.sum_over("p").maximum(
                eps
            )
            trd["primary"].exports[...] = (
                trd["primary"].exports + export_increase_m * export_p_share
            )
            # balance() restores global trade balance but partially dilutes the regional fix → hence the loop.
            trd["primary"].balance()
        else:
            logging.warning(
                "Secondary excess in primary plastics trade did not converge after 20 iterations."
            )

    def compute_other_stocks(self):

        stk = self.stocks
        flw = self.flows

        # in-use stock is already computed in compute_in_use_stock

        stk["landfill"].inflow[...] = flw["collected => landfill"]
        stk["landfill"].compute()

        stk["uncontrolled"].inflow[...] = flw["eol => mismanaged"] + flw["reclmech => uncontrolled"]
        stk["uncontrolled"].compute()

        stk["atmospheric"].inflow[...] = flw["emission => atmosphere"]
        stk["atmospheric"].outflow[...] = (
            flw["atmosphere => feeddaccu"] + flw["atmosphere => feedbio"]
        )
        stk["atmospheric"].compute()
