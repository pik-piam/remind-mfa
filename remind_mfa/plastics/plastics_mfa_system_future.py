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
    # higher number of points than the default because packaging lifetimes are < 1 year
    lifetime_n_pts_per_interval = 10

    def compute(self, stock_projection: fd.FlodymArray, historical_trade: TradeSet):
        """
        Perform all computations for the MFA system.
        """
        self.compute_use_stock(stock_projection)
        self.compute_waste_trade()
        self.compute_flows(historical_trade)
        self.compute_other_stocks()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    def compute_waste_trade(self):
        # waste trade is extrapolated as a scenario parameter, therefore it is not filled in the historical MFA system

        self.trade_set["waste"].imports[...] = (
            self.parameters[f"waste_imports"] * self.parameters["carbon_content_polymers"]
        )
        self.trade_set["waste"].exports[...] = (
            self.parameters[f"waste_exports"] * self.parameters["carbon_content_polymers"]
        )
        self.trade_set.balance(to="maximum")

    def compute_use_stock(self, stock_projection):
        super().compute_use_stock(stock_projection, use_stock_name="use_dsm")

        # We use an auxiliary stock for the prediction step to save dimensions and computation time
        # Therefore, we have to transfer the result to the higher-dimensional stock in the MFA system
        split = (
            self.parameters["polymer_shares_use_inflow"]
            * self.parameters["carbon_content_polymers"]
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
            "total_polymerization_feed": self.get_new_array(dim_letters=("t", "e", "r", "p")),
            "total_primary_hvc": self.get_new_array(dim_letters=("t", "e", "r")),
            "total_waste_collected": self.get_new_array(dim_letters=("t", "e", "r", "p")),
            "not_reused": self.get_new_array(dim_letters=("t", "e", "r", "p", "u")),
            "reclmech_loss": self.get_new_array(dim_letters=("t", "e", "r", "p")),
            "hvc_c_content": self.get_new_array(dim_letters=("t", "e", "r")),
            "hvc_ratio_nonc_to_c": self.get_new_array(dim_letters=("t", "r")),
        }

        # fmt: off

        # EoL flows are computed first, starting from the stock outflow, since recycling flows are needed for the trade extrapolation
        flw["use => eol_management"][...] = stk["use"].outflow
        # reuse: a share of the in-use outflow re-enters the stock, capped by the stock inflow;
        # collection applies to the non-reused part
        # this is a prototype-implementation; not all items that will be collected for reuse can actually be reused
        # TODO implement reuse_yield and flow from reuse to sorting or one of the eol treatments
        flw["eol_management => reuse"][...] = (flw["use => eol_management"] * prm["reuse_share"]).minimum(stk["use"].inflow)
        flw["reuse => use"][...] = flw["eol_management => reuse"]
        aux["not_reused"][...] = flw["use => eol_management"] - flw["eol_management => reuse"]
        flw["eol_management => sorting"][...] = aux["not_reused"] * prm["collection_rate"]

        # exports of plastic waste cannot exceed collected eol plastics
        trd["waste"].exports[...] = trd["waste"].exports.minimum(flw["eol_management => sorting"])
        trd["waste"].balance(to="minimum")

        flw["waste_market => sorting"][...] = trd["waste"].imports
        flw["sorting => waste_market"][...] = trd["waste"].exports
        flw["imports => waste_market"][...] = flw["waste_market => sorting"]
        flw["waste_market => exports"][...] = flw["sorting => waste_market"]

        aux["total_waste_collected"][...] = flw["eol_management => sorting"] + flw["waste_market => sorting"] - flw["sorting => waste_market"]
        flw["sorting => reclmech"][...] = aux["total_waste_collected"] * prm["mechanical_recycling_rate"]
        flw["sorting => reclmech"][{"p": ("Rubbers","PET fibre", "Polyamide fibre", "Other fibre")}] = 0.0 # TODO remove once recycling rates are resolved by polymer
        flw["reclmech => aux_recyclate_market"][...] = flw["sorting => reclmech"] * prm["mechanical_recycling_yield"]
        aux["reclmech_loss"][...] = flw["sorting => reclmech"] - flw["reclmech => aux_recyclate_market"]
        flw["reclmech => uncontrolled"][...] = aux["reclmech_loss"] * prm["reclmech_loss_uncontrolled_rate"]
        flw["reclmech => incineration"][...] = aux["reclmech_loss"] - flw["reclmech => uncontrolled"]

        flw["sorting => reclchem"][...] = aux["total_waste_collected"] * prm["chemical_recycling_rate"]

        flw["sorting => landfill"][...] = aux["total_waste_collected"] * prm["landfill_rate"]

        flw["sorting => incineration"][...] = (
            aux["total_waste_collected"]
            - flw["sorting => reclmech"]
            - flw["sorting => reclchem"]
            - flw["sorting => landfill"]
        )
        flw["incineration => emission"][...] = flw["sorting => incineration"] + flw["reclmech => incineration"]

        flw["eol_management => mismanaged"][...] = aux["not_reused"] - flw["eol_management => sorting"]
        flw["mismanaged => uncontrolled"][...] = flw["eol_management => mismanaged"]

        # now trades and production flows are computed starting from the stock inflow
        flw["manufactured_products_market => use"][...] = stk["use"].inflow - flw["reuse => use"]

        # the historical trade still resolves the polymer type 'P'; the future MFA does not, so it is
        # summed away
        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["manufactured_products"].sum_over("P"),
            future_trade=self.trade_set["manufactured_products"],
            future_dom_demand=flw["manufactured_products_market => use"],
            n_trend_years=self.parameters["n_trend_years"],
            trade_factor=prm["trade_factor"],
        )
        extrapolator.run()

        flw["manufactured_products_market => exports"][...] = (
            trd["manufactured_products"].exports * self.parameters["carbon_content_polymers"]
        )
        flw["imports => manufactured_products_market"][...] = (
            trd["manufactured_products"].imports * self.parameters["carbon_content_polymers"]
        )
        flw["manufacturing => manufactured_products_market"][...] = flw["manufactured_products_market => use"] - flw["imports => manufactured_products_market"] + flw["manufactured_products_market => exports"]

        # a polymer's net imports above its manufacturing demand would make its primary production
        # negative; reassign that excess to the other polymers of the same polymer type (headroom),
        # keeping the trade's polymer split
        flw["primary_market => manufacturing"][...] = flw["manufacturing => manufactured_products_market"]
        # the historical trade resolves the polymer type 'P', the demand does not; expanding the
        # demand with the polymer type mapping keeps the excess reassignment within each polymer type
        self.cap_historical_net_imports_to_demand(
            trade=historical_trade["primary"],
            demand=flw["primary_market => manufacturing"] * prm["polymer_type_mapping"],
            category_dim="p",
        )

        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["primary"].sum_over("P"),
            future_trade=self.trade_set["primary"],
            future_dom_demand=flw["primary_market => manufacturing"],
            n_trend_years=self.parameters["n_trend_years"],
            trade_factor=prm["trade_factor"],
        )
        extrapolator.run()

        flw["primary_market => exports"][...] = (
            trd["primary"].exports * self.parameters["carbon_content_polymers"]
        )
        flw["imports => primary_market"][...] = (
            trd["primary"].imports * self.parameters["carbon_content_polymers"]
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
            recyclate=flw["reclmech => aux_recyclate_market"],
            demand=dom_supply,
        )
        flw["aux_recyclate_market => primary_market"][...] = flw["reclmech => aux_recyclate_market"] - trd["aux_recyclate"].exports + trd["aux_recyclate"].imports
        flw["polymerization => primary_market"][...] = (
            dom_supply - flw["aux_recyclate_market => primary_market"]
        )

        aux["total_polymerization_feed"][...] = flw["polymerization => primary_market"] / prm["polymerization_yield"]
        flw["hvc_production => polymerization"][...] = aux["total_polymerization_feed"].sum_to(("t", "r", "p")) * prm["hvc_input_shares"]
        flw["c4_production => polymerization"][...] = aux["total_polymerization_feed"].sum_to(("t", "r", "p")) * prm["c4_input_shares"]
        aux["net_other_polymerization_input"] = aux["total_polymerization_feed"] - flw["hvc_production => polymerization"] - flw["c4_production => polymerization"] # this is all input to polymerization that is not total HVC or C4 input - can be positive because of other reactants or negative because of upstream losses (e.g. for production of styrene from ethylene and benzene)
        flw["other_reactants => polymerization"][...] = aux["net_other_polymerization_input"].maximum(0) # the positive part is counted as other reactants input
        aux["upstream_losses"][...] = - aux["net_other_polymerization_input"].minimum(0) # the negative part is counted as upstream losses
        flw["polymerization => losses"][...] = aux["total_polymerization_feed"] - flw["polymerization => primary_market"] + aux["upstream_losses"]
        flw["losses => sysenv"][...] = flw["polymerization => losses"]
        # guard against 0/0 in region-years with no HVC input (e.g. countries that never
        # polymerize at iso resolution): the numerator is also 0 there, so the share is 0.
        aux["hvc_c_content"][...] = flw["hvc_production => polymerization"] / flw["hvc_production => polymerization"].sum_to(("t", "r")).maximum(sys.float_info.epsilon)

        # chemical recycling: chem-recycled HVC is redistributed between regions the same way as
        # mechanical recyclate, so a region's chemical recycling above its virgin HVC demand feeds
        # other regions instead of driving its primary (feedstock) HVC negative.
        flw["reclchem => aux_recl_feedstock_market"][...] = flw["sorting => reclchem"].sum_to(("t", "r")) * aux["hvc_c_content"] * prm["chemical_recycling_yield"] # TODO: differentiate yield by element instead of using C content of HVC!
        flw["reclchem => emission"][...] = flw["sorting => reclchem"] - flw["reclchem => aux_recl_feedstock_market"]
        self._redistribute_recyclate_surplus(
            market="aux_recl_feedstock",
            recyclate=flw["reclchem => aux_recl_feedstock_market"],
            demand=flw["hvc_production => polymerization"],
        )
        flw["aux_recl_feedstock_market => hvc_production"][...] = flw["reclchem => aux_recl_feedstock_market"] - trd["aux_recl_feedstock"].exports + trd["aux_recl_feedstock"].imports
        aux["total_primary_hvc"][...] = flw["hvc_production => polymerization"] - flw["aux_recl_feedstock_market => hvc_production"]

        # carbon cycles via bio daccu feedstocks
        flw["feeddaccu => hvc_production"][...] = aux["total_primary_hvc"] * prm["daccu_production_rate"]
        flw["feedbio => hvc_production"][...] = aux["total_primary_hvc"] * prm["bio_production_rate"]

        # captured emissions and ccu feedstocks
        # non-C atmosphere & captured has no meaning & is equivalent to sysenv
        flw["emission => captured"][...] = (flw["incineration => emission"] + flw["reclchem => emission"]) * prm["emission_capture_rate"]
        flw["emission => atmosphere"][...] = flw["incineration => emission"] + flw["reclchem => emission"] - flw["emission => captured"]
        flw["captured => feedccu"][...] = flw["emission => captured"]
        # non-C of CCU HVC production has to be calculated based on the same ratio as in overall HVC production
        aux["hvc_ratio_nonc_to_c"][...] = aux["total_primary_hvc"]["Other Elements"] / aux["total_primary_hvc"]["C"].maximum(sys.float_info.epsilon)
        flw["feedccu => hvc_production"]["C"] = flw["captured => feedccu"]["C"]
        flw["feedccu => hvc_production"]["Other Elements"] = flw["feedccu => hvc_production"]["C"] * aux["hvc_ratio_nonc_to_c"]
        flw["feedfoss => hvc_production"][...] = (
            aux["total_primary_hvc"]
            - flw["feeddaccu => hvc_production"]
            - flw["feedbio => hvc_production"]
            - flw["feedccu => hvc_production"]
        )

        flw["sysenv => c4_production"][...] = flw["c4_production => polymerization"]
        flw["sysenv => other_reactants"][...] = flw["other_reactants => polymerization"]
        flw["sysenv => feedfoss"][...] = flw["feedfoss => hvc_production"]
        flw["atmosphere => feedbio"][...] = flw["feedbio => hvc_production"]
        flw["atmosphere => feeddaccu"][...] = flw["feeddaccu => hvc_production"]
        flw["sysenv => feedccu"][...] = flw["feedccu => hvc_production"] - flw["captured => feedccu"]
        flw["sysenv => imports"][...] = flw["imports => manufactured_products_market"] + flw["imports => primary_market"] + flw["imports => waste_market"] + flw["imports => aux_recyclate_market"] + flw["imports => aux_recl_feedstock_market"]
        flw["exports => sysenv"][...] = flw["manufactured_products_market => exports"] + flw["primary_market => exports"] + flw["waste_market => exports"] + flw["aux_recyclate_market => exports"] + flw["aux_recl_feedstock_market => exports"]

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

        See :meth:`CommonMFASystem.redistribute_surplus`; additionally writes the market's trade
        flows. Used for both mechanical (``reclmech`` -> ``primary_market``) and chemical
        (``reclchem`` -> ``hvc_production``) recyclate.
        """
        trd, flw = self.trade_set, self.flows
        self.redistribute_surplus(trd[market], supply=recyclate, demand=demand)
        flw[f"imports => {market}_market"][...] = trd[market].imports
        flw[f"{market}_market => exports"][...] = trd[market].exports

    def compute_other_stocks(self):

        stk = self.stocks
        flw = self.flows

        # in-use stock is already computed in compute_use_stock

        stk["landfill"].inflow[...] = flw["sorting => landfill"]
        stk["landfill"].compute()

        stk["uncontrolled"].inflow[...] = (
            flw["eol_management => mismanaged"] + flw["reclmech => uncontrolled"]
        )
        stk["uncontrolled"].compute()

        stk["atmospheric"].inflow[...] = flw["emission => atmosphere"]
        stk["atmospheric"].outflow[...] = (
            flw["atmosphere => feeddaccu"] + flw["atmosphere => feedbio"]
        )
        stk["atmospheric"].compute()
