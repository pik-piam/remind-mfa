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

    def compute(self, stock_projection: fd.FlodymArray, historical_trade: TradeSet):
        """
        Perform all computations for the MFA system.
        """
        self.compute_stock(stock_projection)
        self.compute_waste_trade()
        self.compute_flows(historical_trade)
        self.compute_other_stocks()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_waste_trade(self):
        # waste trade is extrapolated as a scenario parameter, therefore it is not filled in the historical MFA system

        self.trade_set["waste"].imports[...] = (
            self.parameters[f"waste_imports"] * self.parameters["carbon_content_materials"]
        )
        self.trade_set["waste"].exports[...] = (
            self.parameters[f"waste_exports"] * self.parameters["carbon_content_materials"]
        )
        self.trade_set.balance(to="maximum")

    def compute_stock(self, stock_projection: fd.FlodymArray):
        self.stocks["use_dsm"].stock[...] = stock_projection
        self.stocks["use_dsm"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"],
            std=self.parameters["lifetime_std"],
        )
        # We use a higher number of points for the lifetime model than the default because packaging lifetimes are < 1 year
        self.stocks["use_dsm"].lifetime_model.n_pts_per_interval = 10
        self.stocks["use_dsm"].compute()
        self.correct_negative_inflow("use_dsm")

        # We use an auxiliary stock for the prediction step to save dimensions and computation time
        # Therefore, we have to transfer the result to the higher-dimensional stock in the MFA system
        split = (
            self.parameters["material_shares_use_inflow"]
            * self.parameters["carbon_content_materials"]
        )
        self.stocks["use"].stock[...] = self.stocks["use_dsm"].stock * split
        self.stocks["use"].inflow[...] = self.stocks["use_dsm"].inflow * split
        self.stocks["use"].outflow[...] = self.stocks["use_dsm"].outflow * split

    def compute_flows(self, historical_trade: TradeSet):

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
            "total_waste_collected": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "reclmech_loss": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "HVC_c_content": self.get_new_array(dim_letters=("t", "e", "r")),
            "HVC_ratio_nonc_to_c": self.get_new_array(dim_letters=("t", "r")),
        }

        # fmt: off

        # EoL flows are computed first, starting from the stock outflow, since recycling flows are needed for the trade extrapolation
        flw["use => eol"][...] = stk["use"].outflow
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
        flw["reclmech => aux_recyclate"][...] = flw["collected => reclmech"] * prm["mechanical_recycling_yield"]
        aux["reclmech_loss"][...] = flw["collected => reclmech"] - flw["reclmech => aux_recyclate"]
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
        flw["manufactured_products_market => use"][...] = stk["use"].inflow

        # the historical trade still resolves the polymer type 'p'; the future MFA does not, so it is
        # summed away
        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["manufactured_products"].sum_over("p"),
            future_trade=self.trade_set["manufactured_products"],
            future_dom_demand=stk["use"].inflow,
        )
        extrapolator.run()

        flw["manufactured_products_market => exports"][...] = (
            trd["manufactured_products"].exports * self.parameters["carbon_content_materials"]
        )
        flw["imports => manufactured_products_market"][...] = (
            trd["manufactured_products"].imports * self.parameters["carbon_content_materials"]
        )
        flw["manufacturing => manufactured_products_market"][...] = flw["manufactured_products_market => use"] - flw["imports => manufactured_products_market"] + flw["manufactured_products_market => exports"]

        # a material's net imports above its manufacturing demand would make its primary production
        # negative; reassign that excess to the other materials of the same polymer type (headroom),
        # keeping the trade's material split
        flw["primary_market => manufacturing"][...] = flw["manufacturing => manufactured_products_market"]
        # the historical trade resolves the polymer type 'p', the demand does not; expanding the
        # demand with the type mapping keeps the excess reassignment within each polymer type
        self.cap_historical_net_imports_to_demand(
            trade=historical_trade["primary"],
            demand=flw["primary_market => manufacturing"] * prm["material_type_mapping"],
            category_dim="m",
        )

        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["primary"].sum_over("p"),
            future_trade=self.trade_set["primary"],
            future_dom_demand=flw["primary_market => manufacturing"],
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
            flw["primary_market => manufacturing"]
            - flw["imports => primary_market"]
            + flw["primary_market => exports"]
        )
        self._redistribute_recyclate_surplus(
            market="aux_recyclate",
            recyclate=flw["reclmech => aux_recyclate"],
            demand=dom_supply,
        )
        flw["aux_recyclate => primary_market"][...] = flw["reclmech => aux_recyclate"] - trd["aux_recyclate"].exports + trd["aux_recyclate"].imports
        flw["polymerization => primary_market"][...] = (
            dom_supply - flw["aux_recyclate => primary_market"]
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
        flw["reclchem => aux_recl_feedstock"][...] = flw["collected => reclchem"].sum_to(("t", "r")) * aux["HVC_c_content"] * prm["chemical_recycling_yield"] # TODO: differentiate yield by element instead of using C content of HVC!
        flw["reclchem => emission"][...] = flw["collected => reclchem"] - flw["reclchem => aux_recl_feedstock"]
        self._redistribute_recyclate_surplus(
            market="aux_recl_feedstock",
            recyclate=flw["reclchem => aux_recl_feedstock"],
            demand=flw["HVC_input => polymerization"],
        )
        flw["aux_recl_feedstock => HVC_input"][...] = flw["reclchem => aux_recl_feedstock"] - trd["aux_recl_feedstock"].exports + trd["aux_recl_feedstock"].imports
        aux["total_primary_HVC"][...] = flw["HVC_input => polymerization"] - flw["aux_recl_feedstock => HVC_input"]

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
        flw["sysenv => imports"][...] = flw["imports => manufactured_products_market"] + flw["imports => primary_market"] + flw["imports => waste_market"] + flw["imports => aux_recyclate"] + flw["imports => aux_recl_feedstock"]
        flw["exports => sysenv"][...] = flw["manufactured_products_market => exports"] + flw["primary_market => exports"] + flw["waste_market => exports"] + flw["aux_recyclate => exports"] + flw["aux_recl_feedstock => exports"]

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

        # in-use stock is already computed in compute_use_stock

        stk["landfill"].inflow[...] = flw["collected => landfill"]
        stk["landfill"].compute()

        stk["uncontrolled"].inflow[...] = flw["eol => mismanaged"] + flw["reclmech => uncontrolled"]
        stk["uncontrolled"].compute()

        stk["atmospheric"].inflow[...] = flw["emission => atmosphere"]
        stk["atmospheric"].outflow[...] = (
            flw["atmosphere => feeddaccu"] + flw["atmosphere => feedbio"]
        )
        stk["atmospheric"].compute()
