from typing import Optional
import flodym as fd
import numpy as np

from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.trade import TradeSet
from remind_mfa.common.custom_data_reader import CustomDataReader
from remind_mfa.common.trade_extrapolation import extrapolate_trade
from remind_mfa.common.stock_extrapolation import StockExtrapolation
from remind_mfa.common.common_cfg import PlasticsCfg
from remind_mfa.common.data_transformations import Bound, BoundList


class PlasticsMFASystemFuture(fd.MFASystem):

    cfg: Optional[PlasticsCfg] = None
    trade_set: TradeSet

    def compute(self, historic_stock: fd.Stock, historic_trade: TradeSet):
        """
        Perform all computations for the MFA system.
        """
        # self.compute_trade()
        self.extrapolate_stock(historic_stock)
        self.transfer_to_simple_stock()
        self.extrapolate_trades(historic_trade)
        self.compute_flows()
        self.compute_other_stocks()
        self.check_mass_balance()
        self.check_flows(raise_error=False)

    # def compute_trade(self):

    #     for name, trade in self.trade_set.markets.items():
    #         if name == "waste":
    #             trade.imports[...] = self.parameters[f"{name}_imports"]
    #             trade.exports[...] = self.parameters[f"{name}_exports"]
    #     self.trade_set.balance(to="maximum")

    def extrapolate_stock(self, historic_stock: fd.Stock):
        """
        Stock extrapolation is first done per good over all regions;
        upper bound of saturation level is set as the maximum historic stock per capita;
        stock extrapolation is then repeated per region and good, using the maximum of the previously fitted global saturation level
        and the maximum historic stock per capita in the respective region as upper bound.
        """
        weight = 70
        add_assumption_doc(
            type="integer number",
            name="weight for loggdppc time weighted sum predictor in stock extrapolation",
            value=weight,
            description=(
                "Weight used for the predictor in stock extrapolation that is a weighted sum of gdppc and time"
                "according to the formula: 'log10(gdppc) * weight + time', "
                "determined from a regression of time vs. log10(gdppc) at constant stock per capita."
            ),
        )
        historic_pop = self.parameters["population"][{"t": self.dims["h"]}]
        stock_pc = historic_stock.stock / historic_pop
        # First extrapolation to get global saturation levels
        indep_fit_dim_letters = ("g",)
        lower_bound = fd.FlodymArray(
            dims=self.dims[indep_fit_dim_letters],
            values=np.zeros(self.dims[indep_fit_dim_letters].shape),
        )
        upper_bound = fd.FlodymArray(
            dims=stock_pc.dims[indep_fit_dim_letters], values=np.max(stock_pc.values, axis=(0, 1))
        )
        sat_bound = Bound(
            var_name="saturation_level",
            lower_bound=lower_bound.values,
            upper_bound=upper_bound.values,
            dims=lower_bound.dims,
        )
        bound_list = BoundList(
            bound_list=[
                sat_bound,
            ],
            target_dims=self.dims[indep_fit_dim_letters],
        )
        stock_handler = StockExtrapolation(
            historic_stocks=historic_stock.stock,
            dims=self.dims,
            parameters=self.parameters,
            stock_extrapolation_class=self.cfg.customization.stock_extrapolation_class,
            regress_over=self.cfg.customization.regress_over,
            weight=weight,
            target_dim_letters=(
                "all" if self.cfg.customization.do_stock_extrapolation_by_category else ("t", "r")
            ),
            bound_list=bound_list,
            indep_fit_dim_letters=indep_fit_dim_letters,
        )
        # Second extrapolation per region and good, using the maximum of the previously fitted global saturation level
        # and the maximum historic stock per capita in the respective region as upper bound
        indep_fit_dim_letters = ("r", "g")
        saturation_level = stock_handler.pure_parameters["saturation_level"].cast_to(
            self.dims[indep_fit_dim_letters]
        )
        upper_bound_sat = saturation_level.maximum(
            fd.FlodymArray(
                dims=stock_pc.dims[indep_fit_dim_letters], values=np.max(stock_pc.values, axis=0)
            )
        )
        sat_bound = Bound(
            var_name="saturation_level",
            lower_bound=upper_bound_sat.values,
            upper_bound=upper_bound_sat.values,
            dims=upper_bound_sat.dims,
        )
        bound_list = BoundList(
            bound_list=[
                sat_bound,
            ],
            target_dims=self.dims[indep_fit_dim_letters],
        )
        self.stock_handler = StockExtrapolation(
            historic_stocks=historic_stock.stock,
            dims=self.dims,
            parameters=self.parameters,
            stock_extrapolation_class=self.cfg.customization.stock_extrapolation_class,
            regress_over=self.cfg.customization.regress_over,
            weight = weight,
            target_dim_letters=(
                "all" if self.cfg.customization.do_stock_extrapolation_by_category else ("t", "r")
            ),
            bound_list=bound_list,
            indep_fit_dim_letters=indep_fit_dim_letters,
        )
        in_use_stock = self.stock_handler.stocks
        self.stocks["in_use_dsm"].stock[...] = in_use_stock
        self.stocks["in_use_dsm"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"], std=self.parameters["lifetime_std"]
        )
        self.stocks["in_use_dsm"].compute()

    def transfer_to_simple_stock(self):
        # We use an auxiliary stock for the prediction step to save dimensions and computation time
        # Therefore, we have to transfer the result to the higher-dimensional stock in the MFA system
        split = (
            self.parameters["material_shares_in_goods"]
            * self.parameters["carbon_content_materials"]
        )
        self.stocks["in_use"].stock[...] = self.stocks["in_use_dsm"].stock * split
        self.stocks["in_use"].inflow[...] = self.stocks["in_use_dsm"].inflow * split
        self.stocks["in_use"].outflow[...] = self.stocks["in_use_dsm"].outflow * split

    def extrapolate_trades(self, historic_trade: TradeSet):

        product_demand = self.stocks["in_use"].inflow

        extrapolate_trade(
            historic_trade["primary_his"],
            self.trade_set["primary"],
            product_demand,
            "imports",
            balance_to="hmean",
        )

        extrapolate_trade(
            historic_trade["intermediate_his"],
            self.trade_set["intermediate"],
            product_demand,
            "imports",
            balance_to="hmean",
        )

        extrapolate_trade(
            historic_trade["manufactured_his"],
            self.trade_set["manufactured"],
            product_demand,
            "imports",
            balance_to="hmean",
        )

        extrapolate_trade(
            historic_trade["final_his"],
            self.trade_set["final"],
            product_demand,
            "imports",
            balance_to="hmean",
        )

    def compute_flows(self):

        # abbreviations for better readability
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        trd = self.trade_set

        aux = {
            "reclmech_loss": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "virgin_2_fabr_all_mat": self.get_new_array(dim_letters=("t", "e", "r")),
            "virgin_material_shares": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "captured_2_virginccu_by_mat": self.get_new_array(dim_letters=("t", "e", "r", "m")),
            "ratio_nonc_to_c": self.get_new_array(dim_letters=("m",)),
            "final_2_fabrication": self.get_new_array(dim_letters=("t", "e", "m")),
        }

        # non-C atmosphere & captured has no meaning & is equivalent to sysenv
        material_element_split = prm["material_shares_in_goods"] * prm["carbon_content_materials"]
        good_split = stk["in_use"].inflow.sum_over(("e", "m")).get_shares_over("g")
        good_split_eol = stk["in_use"].outflow.sum_over(("e", "m")).get_shares_over("g")
        material_element_split_noGood = (
            stk["in_use"].inflow.sum_over(("g")).get_shares_over(("e", "m"))
        )

        flw["primary_market => processing"][...] = (
            trd["primary"].imports * material_element_split_noGood
        )
        flw["virgin => primary_market"][...] = (
            trd["primary"].exports * material_element_split_noGood
        )
        flw["sysenv => primary_market"][...] = flw["primary_market => processing"][...]
        flw["primary_market => sysenv"][...] = flw["virgin => primary_market"][...]

        flw["intermediate_market => fabrication"][...] = (
            (trd["intermediate"].imports + trd["manufactured"].imports)
            * material_element_split_noGood
        )
        flw["processing => intermediate_market"][...] = (
            trd["intermediate"].exports + trd["manufactured"].exports
        ) * material_element_split_noGood
        flw["sysenv => intermediate_market"][...] = flw["intermediate_market => fabrication"][...]
        flw["intermediate_market => sysenv"][...] = flw["processing => intermediate_market"][...]

        flw["good_market => use"][...] = (
            trd["final"].imports * good_split * material_element_split
        )
        flw["fabrication => good_market"][...] = (
            trd["final"].exports * good_split * material_element_split
        )
        flw["sysenv => good_market"][...] = flw["good_market => use"][...]
        flw["good_market => sysenv"][...] = flw["fabrication => good_market"][...]

        flw["fabrication => use"][...] = stk["in_use"].inflow - flw["good_market => use"][...]

        # fmt: off

        flw["use => eol"][...] = stk["in_use"].outflow

        flw["waste_market => collected"][...] = prm["waste_imports"] * good_split_eol * material_element_split
        flw["collected => waste_market"][...] = prm["waste_exports"] * good_split_eol * material_element_split
        flw["sysenv => waste_market"][...] = flw["waste_market => collected"][...]
        flw["waste_market => sysenv"][...] = flw["collected => waste_market"][...]

        flw["eol => collected"][...] = flw["use => eol"] * prm["collection_rate"]
        flw["collected => reclmech"][...] = (flw["eol => collected"] + flw["waste_market => collected"] - flw["collected => waste_market"]) * prm["mechanical_recycling_rate"]
        flw["reclmech => processing"][...] = flw["collected => reclmech"] * prm["mechanical_recycling_yield"]
        aux["reclmech_loss"][...] = flw["collected => reclmech"] - flw["reclmech => processing"]
        flw["reclmech => uncontrolled"][...] = aux["reclmech_loss"] * prm["reclmech_loss_uncontrolled_rate"]
        flw["reclmech => incineration"][...] = aux["reclmech_loss"] - flw["reclmech => uncontrolled"]

        flw["collected => reclchem"][...] = (flw["eol => collected"] + flw["waste_market => collected"] - flw["collected => waste_market"]) * prm["chemical_recycling_rate"]
        flw["reclchem => virgin"][...] = flw["collected => reclchem"]

        flw["collected => incineration"][...] = (flw["eol => collected"] + flw["waste_market => collected"] - flw["collected => waste_market"]) * prm["incineration_rate"]

        flw["collected => landfill"][...] = (
            flw["eol => collected"]
            + flw["waste_market => collected"]
            - flw["collected => waste_market"]
            - flw["collected => reclmech"]
            - flw["collected => reclchem"]
            - flw["collected => incineration"]
        )

        flw["eol => mismanaged"][...] = (
            flw["use => eol"]
            - flw["eol => collected"]
        )

        flw["mismanaged => uncontrolled"][...] = (
            flw["eol => mismanaged"]
        )

        flw["incineration => emission"][...] = flw["collected => incineration"] + flw["reclmech => incineration"]

        flw["emission => captured"][...] = flw["incineration => emission"] * prm["emission_capture_rate"]
        flw["emission => atmosphere"][...] = flw["incineration => emission"] - flw["emission => captured"]
        flw["captured => virginccu"][...] = flw["emission => captured"]

        flw["processing => fabrication"][...] = (
            flw["fabrication => use"]
            + flw["fabrication => good_market"]
            - flw["intermediate_market => fabrication"]
        )

        flw["virgin => processing"][...] = (
            flw["processing => fabrication"]
            - flw["primary_market => processing"]
            + flw["processing => intermediate_market"]
            - flw["reclmech => processing"]
        )

        flw["virgindaccu => virgin"][...] = flw["virgin => processing"] * prm["daccu_production_rate"]
        flw["virginbio => virgin"][...] = flw["virgin => processing"] * prm["bio_production_rate"]

        aux["virgin_2_fabr_all_mat"][...] = flw["virgin => processing"]
        aux["virgin_material_shares"][...] = flw["virgin => processing"] / aux["virgin_2_fabr_all_mat"]
        aux["captured_2_virginccu_by_mat"][...] = flw["captured => virginccu"] * aux["virgin_material_shares"]

        flw["virginccu => virgin"]["C"] = aux["captured_2_virginccu_by_mat"]["C"]
        aux["ratio_nonc_to_c"][...] = prm["carbon_content_materials"]["Other Elements"] / prm["carbon_content_materials"]["C"]
        flw["virginccu => virgin"]["Other Elements"] = flw["virginccu => virgin"]["C"] * aux["ratio_nonc_to_c"]

        flw["virginfoss => virgin"][...] = (
            flw["virgin => processing"]
            - flw["virgindaccu => virgin"]
            - flw["virginbio => virgin"]
            - flw["virginccu => virgin"]
            - flw["reclchem => virgin"]
            + flw["virgin => primary_market"]
        )

        flw["sysenv => virginfoss"][...] = flw["virginfoss => virgin"]
        flw["atmosphere => virginbio"][...] = flw["virginbio => virgin"]
        flw["atmosphere => virgindaccu"][...] = flw["virgindaccu => virgin"]
        flw["sysenv => virginccu"][...] = flw["virginccu => virgin"] - aux["captured_2_virginccu_by_mat"]

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
