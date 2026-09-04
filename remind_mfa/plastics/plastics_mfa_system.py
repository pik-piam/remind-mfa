import flodym as fd
import numpy as np
import logging
from copy import deepcopy
import sys

from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.common.trade import TradeSet, Trade
from remind_mfa.common.trade_extrapolation import TradeExtrapolator, FixedSupplyTradeExtrapolator
from remind_mfa.plastics.plastics_config import PlasticsCfg


class PlasticsMFASystemFuture(CommonMFASystem):

    cfg: PlasticsCfg

    def compute(
        self,
        stock_projection: fd.FlodymArray,
        historic_trade: TradeSet,
        baseline_trade: TradeSet,
        baseline_flows: dict,
    ):
        """
        Perform all computations for the MFA system.
        """
        self.compute_stock(stock_projection)
        self.compute_waste_trade()
        self.compute_flows(historic_trade, baseline_trade, baseline_flows)
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
        self.stocks["in_use"].inflow[...] = self.stocks["in_use_dsm"].inflow * split
        self.stocks["in_use"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"],
            std=self.parameters["lifetime_std"],
        )
        # We use a higher number of points for the lifetime model than the default because packaging lifetimes are < 1 year
        self.stocks["in_use"].lifetime_model.n_pts_per_interval = 10
        self.stocks["in_use"].compute()

        if self.cfg.transience.transience_run == True:
            # store original inflow for comparison
            self.demand_REMIND_MFA = self.stocks["in_use"].inflow[
                {"r": "EU27+3", "m": self.dims["n"], "g": self.dims["f"], "t": self.dims["u"]}
            ]
            # Replace with EU-MFA data
            # TODO extrapolate EU-MFA data or run MFA only until 2060
            demand_EU_MFA = (
                self.parameters["stock_inflow_EU-MFA"]
                * self.parameters["carbon_content_materials"][{"m": self.dims["n"]}]
            )
            self.demand_EU_MFA = demand_EU_MFA[{"r": "EU27+3"}]
            self.stocks["in_use"].inflow[
                {"r": "EU27+3", "m": self.dims["n"], "g": self.dims["f"], "t": self.dims["u"]}
            ] = self.demand_EU_MFA
            self.stocks["in_use"].compute()
            # store original outflow (generated from EU-MFA inflow and REMIND-MFA lifetime model) for comparison
            self.stock_outflow_REMIND_MFA = self.stocks["in_use"].outflow[
                {"r": "EU27+3", "m": self.dims["n"], "g": self.dims["f"], "t": self.dims["u"]}
            ]
            # Replace with EU-MFA data
            stock_outflow_EU_MFA = (
                self.parameters["stock_outflow_EU-MFA"]
                * self.parameters["carbon_content_materials"][{"m": self.dims["n"]}]
            )
            self.stock_outflow_EU_MFA = stock_outflow_EU_MFA[{"r": "EU27+3"}]
            inflow = self.stocks["in_use"].inflow
            outflow = self.stocks["in_use"].outflow
            self.stocks["in_use"] = fd.SimpleFlowDrivenStock(
                dims=self.stocks["in_use"].dims,
                lifetime_model=self.stocks["in_use"].lifetime_model,
                name=self.stocks["in_use"].name,
                process=self.stocks["in_use"].process,
            )
            self.stocks["in_use"].inflow[...] = inflow
            self.stocks["in_use"].inflow[
                {"r": "EU27+3", "m": self.dims["n"], "g": self.dims["f"], "t": self.dims["u"]}
            ] = self.demand_EU_MFA
            self.stocks["in_use"].outflow[...] = outflow
            self.stocks["in_use"].outflow[
                {"r": "EU27+3", "m": self.dims["n"], "g": self.dims["f"], "t": self.dims["u"]}
            ] = self.stock_outflow_EU_MFA
            self.stocks["in_use"].compute()
            logging.warning(
                f"TRANSIENCE mode is on. Both in-use stock inflow and outflow for EU27+3 region are not computed from stock projection, but taken from EU-MFA. "
                f"The stock is calculated as a simple flow-driven stock. "
            )

    def compute_flows(
        self, historic_trade: TradeSet, baseline_trade: TradeSet, baseline_flows: dict
    ):

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
        #flw["collected => reclmech"][{"m": ("Rubbers","PET fibre", "Polyamide fibre", "Other fibre")}] = 0.0 # TODO remove once recycling rates are resolved by material
        flw["reclmech => aux_recyclate_trade"][...] = flw["collected => reclmech"] * prm["mechanical_recycling_yield"]
        aux["reclmech_loss"][...] = flw["collected => reclmech"] - flw["reclmech => aux_recyclate_trade"]
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

        flw["good_market => use"][...] = stk["in_use"].inflow
        # imports of final goods cannot exceed plastics demand
        historic_trade["final_his"].imports[...] = historic_trade["final_his"].imports.minimum(flw["good_market => use"][{"t": self.dims["h"]}])
        historic_trade["final_his"].balance(to="minimum")

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
        self.cap_historical_net_imports_to_demand(
            trade=historic_trade["primary_his"],
            demand=flw["primary_market => fabrication"],
            category_dim="m",
        )

        if self.cfg.transience.trade_scenario in ("fix_supply_alpha0", "fix_supply_alpha1"):
            if self.cfg.transience.baseline_pickle_path is None:
                raise ValueError("TRANSIENCE trade extrapolation scenario 'fix_supply' requires a baseline_pickle_path to be provided in the config. Please provide a valid path or choose a different trade extrapolation scenario.")
            alpha = 0.0 if self.cfg.transience.trade_scenario == "fix_supply_alpha0" else 1.0
            # default extrapolation with the new (scenario) demand, used where demand
            # exceeds baseline and fixing supply is not defensible
            default_trade = deepcopy(self.trade_set["primary"])
            TradeExtrapolator(
                historic_trade=historic_trade["primary_his"],
                future_trade=default_trade,
                future_dom_demand=flw["primary_market => fabrication"],
            ).run()
            extrapolator = FixedSupplyTradeExtrapolator(
                historic_trade = historic_trade["primary_his"],
                baseline_future_trade = baseline_trade["primary"],
                default_future_trade = default_trade,
                future_trade = self.trade_set["primary"],
                baseline_dom_demand = baseline_flows["primary_market => fabrication"],
                future_dom_demand = flw["primary_market => fabrication"],
                fixed_supply_region = "EU27+3",
                import_adjustment_share = alpha,
            )
        else:
            extrapolator = TradeExtrapolator(
                historic_trade=historic_trade["primary_his"],
                future_trade=self.trade_set["primary"],
                future_dom_demand=flw["primary_market => fabrication"],
            )
        extrapolator.run()

        flw["primary_market => exports"][...] = (
            trd["primary"].exports * self.parameters["carbon_content_materials"]
        )
        flw["imports => primary_market"][...] = (
            trd["primary"].imports * self.parameters["carbon_content_materials"]
        )

        # --- recyclate trade: redistribute mechanical-recycling surplus between regions ---
        # dom_supply is the domestic primary supply implied by the primary trade solution, i.e.
        # what virgin polymerization + recyclate must jointly cover. Where a region's recyclate
        # exceeds it, the surplus is redistributed to regions that still make virgin plastic
        # instead of forcing local virgin production negative (which happens for net-importer /
        # high-recycling countries, especially at fine spatial resolution).
        dom_supply = (
            flw["primary_market => fabrication"]
            - flw["imports => primary_market"]
            + flw["primary_market => exports"]
        )
        self._redistribute_recyclate_surplus(
            market="aux_recyclate_trade",
            recyclate=flw["reclmech => aux_recyclate_trade"],
            demand=dom_supply,
        )
        flw["aux_recyclate_trade => primary_market"][...] = flw["reclmech => aux_recyclate_trade"] - trd["aux_recyclate_trade"].exports + trd["aux_recyclate_trade"].imports
        flw["polymerization => primary_market"][...] = (
            dom_supply - flw["aux_recyclate_trade => primary_market"]
        )

        aux["total_polymerization_feed"][...] = flw["polymerization => primary_market"] / prm["polymerization_yield"]
        flw["HVC_input => polymerization"][...] = aux["total_polymerization_feed"].sum_to(("t", "r", "m")) * prm["HVC_input_ratio"]
        flw["C4_input => polymerization"][...] = aux["total_polymerization_feed"].sum_to(("t", "r", "m")) * prm["C4_input_ratio"]
        aux["net_other_polymerization_input"] = aux["total_polymerization_feed"] - flw["HVC_input => polymerization"] - flw["C4_input => polymerization"] # this is all input to polymerization that is not total HVC or C4 input - can be positive because of other reactants or negative because of upstream losses (e.g. for production of styrene from ethylene and benzene)
        flw["other_reactants => polymerization"][...] = aux["net_other_polymerization_input"].maximum(0) # the positive part is counted as other reactants input
        aux["upstream_losses"][...] = - aux["net_other_polymerization_input"].minimum(0) # the negative part is counted as upstream losses
        flw["polymerization => losses"][...] = aux["total_polymerization_feed"] - flw["polymerization => primary_market"] + aux["upstream_losses"]
        flw["losses => sysenv"][...] = flw["polymerization => losses"]
        # guard against 0/0 in region-years with no HVC input (e.g. countries that never
        # polymerize at iso resolution): the numerator is also 0 there, so the share is 0.
        aux["HVC_c_content"][...] = flw["HVC_input => polymerization"] / flw["HVC_input => polymerization"].sum_to(("t", "r")).maximum(sys.float_info.epsilon)

        # chemical recycling: chem-recycled HVC is redistributed between regions the same way as
        # mechanical recyclate, so a region's chemical recycling above its virgin HVC demand feeds
        # other regions instead of driving its primary (feedstock) HVC negative.
        flw["reclchem => aux_recl_feedstock_trade"][...] = flw["collected => reclchem"].sum_to(("t", "r")) * aux["HVC_c_content"] * prm["chemical_recycling_yield"] # TODO: differentiate yield by element instead of using C content of HVC!
        flw["reclchem => emission"][...] = flw["collected => reclchem"] - flw["reclchem => aux_recl_feedstock_trade"]
        self._redistribute_recyclate_surplus(
            market="aux_recl_feedstock_trade",
            recyclate=flw["reclchem => aux_recl_feedstock_trade"],
            demand=flw["HVC_input => polymerization"],
        )
        flw["aux_recl_feedstock_trade => HVC_input"][...] = flw["reclchem => aux_recl_feedstock_trade"] - trd["aux_recl_feedstock_trade"].exports + trd["aux_recl_feedstock_trade"].imports
        aux["total_primary_HVC"][...] = flw["HVC_input => polymerization"] - flw["aux_recl_feedstock_trade => HVC_input"]

        # carbon cycles via bio daccu feedstocks
        flw["feeddaccu => HVC_input"][...] = aux["total_primary_HVC"] * prm["daccu_production_rate"]
        flw["feedbio => HVC_input"][...] = aux["total_primary_HVC"] * prm["bio_production_rate"]

        # captured emissions and ccu feedstocks
        # non-C atmosphere & captured has no meaning & is equivalent to sysenv
        flw["emission => captured"][...] = (flw["incineration => emission"] + flw["reclchem => emission"]) * prm["emission_capture_rate"]
        flw["emission => atmosphere"][...] = flw["incineration => emission"] + flw["reclchem => emission"] - flw["emission => captured"]
        flw["captured => feedccu"][...] = flw["emission => captured"]
        # non-C of CCU HVC production has to be calculated based on the same ratio as in overall HVC production
        aux["HVC_ratio_nonc_to_c"][...] = aux["total_primary_HVC"]["Other Elements"] / aux["total_primary_HVC"]["C"].maximum(sys.float_info.epsilon)
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
        flw["sysenv => imports"][...] = flw["imports => good_market"] + flw["imports => primary_market"] + flw["imports => waste_market"] + flw["imports => aux_recyclate_trade"] + flw["imports => aux_recl_feedstock_trade"]
        flw["exports => sysenv"][...] = flw["good_market => exports"] + flw["primary_market => exports"] + flw["waste_market => exports"] + flw["aux_recyclate_trade => exports"] + flw["aux_recl_feedstock_trade => exports"]

        # fmt: on

    def _redistribute_recyclate_surplus(
        self,
        market: str,
        recyclate: fd.FlodymArray,
        demand: fd.FlodymArray,
    ):
        """Redistribute a region's recyclate surplus via an auxiliary trade market.

        Where a region's ``recyclate`` exceeds the domestic ``demand`` it can feed, the surplus is
        exported; regions with headroom (``demand`` above their recyclate) import it, so the
        backward-computed primary input stays non-negative instead of going negative for net-importer /
        high-recycling regions.

        Exports carry the surplus; imports are seeded with the headroom as a per-region
        distribution shape (shares summing to 1 per slice) and balanced up to the surplus total
        (``to="maximum"``), so each region imports ``surplus * headroom_share``. While a slice's
        total surplus <= total headroom, every region's import stays <= its headroom.

        Writes the market's imports and exports.
        Used for both mechanical (``reclmech`` -> ``primary_market``) and chemical
        (``reclchem`` -> ``HVC_input``) recyclate.
        """
        trd, flw = self.trade_set, self.flows
        surplus = (recyclate - demand).maximum(0)
        headroom = (demand - recyclate).maximum(0)
        trd[market].exports[...] = surplus
        trd[market].imports[...] = headroom / headroom.sum_over("r").maximum(sys.float_info.epsilon)
        trd[market].balance(to="maximum", mask_scaled=(trd[market].exports.values == 0))
        flw[f"imports => {market}"][...] = trd[market].imports
        flw[f"{market} => exports"][...] = trd[market].exports

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
