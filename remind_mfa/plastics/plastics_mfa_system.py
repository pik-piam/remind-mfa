import flodym as fd
import numpy as np
import logging

from remind_mfa.common.trade import TradeSet, Trade
from remind_mfa.common.trade_extrapolation import TradeExtrapolator
from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.plastics.plastics_config import PlasticsCfg


class PlasticsMFASystemFuture(fd.MFASystem):

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
        self.trade_set.balance(to="minimum")

    def compute_stock(self, stock_projection: fd.FlodymArray):
        self.stocks["in_use_dsm"].stock[...] = stock_projection
        self.stocks["in_use_dsm"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"], std=self.parameters["lifetime_std"],
        )
        # We use a higher number of points for the lifetime model than the default because packaging lifetimes are < 1 year
        self.stocks["in_use_dsm"].lifetime_model.n_pts_per_interval = 10
        self.stocks["in_use_dsm"].compute()

        if np.min(self.stocks["in_use_dsm"].inflow.values) < 0:
            negative_regions = [
                r
                for r in self.dims["r"].items
                if np.min(self.stocks["in_use_dsm"].inflow[r].values) < 0
            ]
            logging.warning(
                f"In-use stock inflow <0 in regions {negative_regions}! Correcting negative inflow to 0."
            )
            corrected_inflow = self.stocks["in_use_dsm"].inflow.maximum(1e-6)
            # correct negative inflow
            self.stocks["in_use_dsm"] = fd.InflowDrivenDSM(
                dims=self.stocks["in_use_dsm"].dims,
                lifetime_model=self.stocks["in_use_dsm"].lifetime_model,
                name="in_use",
                process=self.stocks["in_use_dsm"].process,
            )
            self.stocks["in_use_dsm"].inflow[...] = corrected_inflow
            self.stocks["in_use_dsm"].compute()

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
            "total_primary_fabrication": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "total_primary_virgin": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "total_waste_collected": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "reclmech_loss": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "total_primary_virgin_all_mat": self.get_new_array(dim_letters=("t", "e", "r")),
            "virgin_material_shares": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "captured_2_virginccu_by_mat": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "ratio_nonc_to_c": self.get_new_array(dim_letters=("m",)),
        }

        # fmt: off

        # EoL flows are computed first, starting from the stock outflow, since recycling flows are needed for the trade extrapolation
        flw["use => eol"][...] = stk["in_use"].outflow

        flw["waste_market => collected"][...] = trd["waste"].imports
        flw["collected => waste_market"][...] = trd["waste"].exports
        flw["imports => waste_market"][...] = flw["waste_market => collected"]
        flw["waste_market => exports"][...] = flw["collected => waste_market"]
        
        flw["eol => collected"][...] = flw["use => eol"] * prm["collection_rate"]
        aux["total_waste_collected"][...] = flw["eol => collected"] + flw["waste_market => collected"] - flw["collected => waste_market"]
        flw["collected => reclmech"][...] = aux["total_waste_collected"] * prm["mechanical_recycling_rate"]
        flw["reclmech => fabrication"][...] = flw["collected => reclmech"] * prm["mechanical_recycling_yield"]
        flw["reclmech => fabrication"]["Elastomers (tyres)"] = 0 # FIXME hot fix to avoid negative flows in virgin production; will be fixed once recycling rate has a material dimension 
        aux["reclmech_loss"][...] = flw["collected => reclmech"] - flw["reclmech => fabrication"]
        flw["reclmech => uncontrolled"][...] = aux["reclmech_loss"] * prm["reclmech_loss_uncontrolled_rate"]
        flw["reclmech => incineration"][...] = aux["reclmech_loss"] - flw["reclmech => uncontrolled"]

        flw["collected => reclchem"][...] = aux["total_waste_collected"] * prm["chemical_recycling_rate"]
        flw["reclchem => virgin"][...] = flw["collected => reclchem"]

        flw["collected => incineration"][...] = aux["total_waste_collected"] * prm["incineration_rate"]
        flw["incineration => emission"][...] = flw["collected => incineration"] + flw["reclmech => incineration"]

        flw["collected => landfill"][...] = (
            aux["total_waste_collected"]
            - flw["collected => reclmech"]
            - flw["collected => reclchem"]
            - flw["collected => incineration"]
        )

        flw["eol => mismanaged"][...] = flw["use => eol"] - flw["eol => collected"]
        flw["mismanaged => uncontrolled"][...] = flw["eol => mismanaged"]
        
        # non-C atmosphere & captured has no meaning & is equivalent to sysenv
        flw["emission => captured"][...] = flw["incineration => emission"] * prm["emission_capture_rate"]
        flw["emission => atmosphere"][...] = flw["incineration => emission"] - flw["emission => captured"]
        flw["captured => virginccu"][...] = flw["emission => captured"]

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

        # imports of primary plastics cannot exceed primary plastics demand in fabrication (plastics fabrication - mechanically recycled plastics)
        aux["total_primary_fabrication"][...] = flw["fabrication => good_market"] - flw["reclmech => fabrication"]
        historic_trade["primary_his"].imports[...] = historic_trade["primary_his"].imports.minimum(aux["total_primary_fabrication"][{"t": self.dims["h"]}])
        historic_trade["primary_his"].balance(to="minimum")

        extrapolator = TradeExtrapolator(
            historic_trade=historic_trade["primary_his"],
            future_trade=self.trade_set["primary"],
            future_dom_demand=aux["total_primary_fabrication"],
        )
        extrapolator.run()

        flw["primary_market => exports"][...] = (
            trd["primary"].exports * self.parameters["carbon_content_materials"]
        )
        flw["imports => primary_market"][...] = (
            trd["primary"].imports * self.parameters["carbon_content_materials"]
        )
        flw["primary_market => fabrication"][...] = aux["total_primary_fabrication"]

        flw["virgin => primary_market"][...] = (
            flw["primary_market => fabrication"]
            - flw["imports => primary_market"] 
            + flw["primary_market => exports"]
        )

        aux["total_primary_virgin"][...] = flw["virgin => primary_market"] - flw["reclchem => virgin"]
        flw["virgindaccu => virgin"][...] = aux["total_primary_virgin"] * prm["daccu_production_rate"]
        flw["virginbio => virgin"][...] = aux["total_primary_virgin"] * prm["bio_production_rate"]

        # assumption: virgin production from CCU is split by the same material shares as overall primary virgin production
        aux["total_primary_virgin_all_mat"][...] = aux["total_primary_virgin"]
        aux["virgin_material_shares"][...] = aux["total_primary_virgin"] / aux["total_primary_virgin_all_mat"]
        aux["captured_2_virginccu_by_mat"][...] = flw["captured => virginccu"] * aux["virgin_material_shares"]

        flw["virginccu => virgin"]["C"] = aux["captured_2_virginccu_by_mat"]["C"]
        aux["ratio_nonc_to_c"][...] = prm["carbon_content_materials"]["Other Elements"] / prm["carbon_content_materials"]["C"]
        flw["virginccu => virgin"]["Other Elements"] = flw["virginccu => virgin"]["C"] * aux["ratio_nonc_to_c"]

        flw["virginfoss => virgin"][...] = (
            flw["virgin => primary_market"]
            - flw["virgindaccu => virgin"]
            - flw["virginbio => virgin"]
            - flw["virginccu => virgin"]
            - flw["reclchem => virgin"]
        )

        flw["sysenv => virginfoss"][...] = flw["virginfoss => virgin"]
        flw["atmosphere => virginbio"][...] = flw["virginbio => virgin"]
        flw["atmosphere => virgindaccu"][...] = flw["virgindaccu => virgin"]
        flw["sysenv => virginccu"][...] = flw["virginccu => virgin"] - aux["captured_2_virginccu_by_mat"]
        flw["sysenv => imports"][...] = flw["imports => good_market"] + flw["imports => primary_market"] + flw["imports => waste_market"]
        flw["exports => sysenv"][...] = flw["good_market => exports"] + flw["primary_market => exports"] + flw["waste_market => exports"]

        # fmt: on

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
            flw["atmosphere => virgindaccu"] + flw["atmosphere => virginbio"]
        )
        stk["atmospheric"].compute()
