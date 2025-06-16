import flodym as fd
import numpy as np
from enum import Enum

from remind_mfa.common.trade import TradeSet
from remind_mfa.common.trade_extrapolation import extrapolate_trade
from remind_mfa.common.price_driven_trade import PriceDrivenTrade
from remind_mfa.common.common_mfa_system import CommonMFASystem

class SteelMode(str, Enum):
    stock_driven = "stock_driven"
    inflow_driven = "inflow_driven"

class SteelMFASystem(CommonMFASystem):

    mode: SteelMode

    def compute(self, stock_projection: fd.FlodymArray, historic_trade: TradeSet):
        """
        Perform all computations for the MFA system.
        """
        self.compute_in_use_stock(stock_projection)
        self.compute_trade(historic_trade)
        self.compute_flows()
        self.compute_other_stocks()
        self.check_mass_balance()
        self.check_flows(raise_error=False)
        # self.update_price_elastic()

    def compute_trade(self, historic_trade: TradeSet):
        if self.stock_driven:
            self.extrapolate_trade_set(historic_trade)
        else:
            self.fill_trade()
            self.trade_set.balance(to="hmean")

    def update_price_elastic(self):
        self.compute_price_elastic_trade()
        # self.compute_consumption()
        # self.compute_in_use_stock() # ensure inflow-driven
        # self.compute_other_flows()
        # self.compute_other_stocks()

        # self.check_mass_balance()
        # self.check_flows(raise_error=False)

    def compute_price_elastic_trade(self):
        price = fd.FlodymArray(dims=self.dims["t", "r"])
        price[...] = 500.0
        # price.values[131:201,2] = np.minimum(800., np.linspace(500, 2000, 70))
        model = PriceDrivenTrade(dims=self.trade_set["intermediate"].exports.dims)
        model.calibrate(
            demand=self.flows["ip_market => fabrication"][2022],
            price=price[2022],
            imports_target=self.trade_set["intermediate"].imports[2022],
            exports_target=self.trade_set["intermediate"].exports[2022],
        )
        price, demand, supply, imports, exports = model.compute_price_driven_trade(
            price_0=price,
            demand_0=self.flows["ip_market => fabrication"],
            supply_0=self.flows["forming => ip_market"],
        )

        self.flows["ip_market => fabrication"][...] = demand
        self.flows["forming => ip_market"][...] = supply
        self.trade_set["intermediate"].imports[...] = imports
        self.trade_set["intermediate"].exports[...] = exports
        self.trade_set["intermediate"].balance()

        self.flows["imports => ip_market"][...] = self.trade_set["intermediate"].imports
        self.flows["ip_market => exports"][...] = self.trade_set["intermediate"].exports

    def compute_in_use_stock(self, stock_projection):
        if self.stock_driven:
            self.stocks["in_use"].stock[...] = stock_projection
        else:
            self.stocks["in_use"].inflow[...] = self.parameters["in_use_inflow"]

        self.stocks["in_use"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"], std=self.parameters["lifetime_std"]
        )
        self.stocks["in_use"].compute()
        if not self.stock_driven:
            self.stocks["in_use"].outflow[...] += self.parameters["fixed_in_use_outflow"]

    def extrapolate_trade_set(self, historic_trade: TradeSet):
        product_demand = self.stocks["in_use"].inflow
        extrapolate_trade(
            historic_trade["indirect"],
            self.trade_set["indirect"],
            product_demand,
            "imports",
            balance_to="hmean",
        )
        self.trade_set["indirect"].imports[...] = self.trade_set["indirect"].imports.minimum(
            product_demand
        )
        self.trade_set["indirect"].balance(to="minimum")

        fabrication = product_demand - self.trade_set["indirect"].net_imports
        extrapolate_trade(
            historic_trade["intermediate"],
            self.trade_set["intermediate"],
            fabrication,
            "imports",
            balance_to="hmean",
        )

        eol_products = self.stocks["in_use"].outflow * self.parameters["recovery_rate"]
        extrapolate_trade(
            historic_trade["scrap"],
            self.trade_set["scrap"],
            eol_products,
            "exports",
            balance_to="hmean",
        )
        self.trade_set["scrap"].exports[...] = self.trade_set["scrap"].exports.minimum(eol_products)
        self.trade_set["scrap"].balance(to="minimum")

    def compute_flows(self):
        # abbreviations for better readability
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        trd = self.trade_set

        aux = {
            "net_scrap_trade": self.get_new_array(dim_letters=("t", "r", "g")),
            "production": self.get_new_array(dim_letters=("t", "r")),
            "forming_outflow": self.get_new_array(dim_letters=("t", "r")),
            "scrap_in_production": self.get_new_array(dim_letters=("t", "r")),
            "available_scrap": self.get_new_array(dim_letters=("t", "r")),
            "eaf_share_production": self.get_new_array(dim_letters=("t", "r")),
            "production_inflow": self.get_new_array(dim_letters=("t", "r")),
            "max_scrap_production": self.get_new_array(dim_letters=("t", "r")),
            "scrap_share_production": self.get_new_array(dim_letters=("t", "r")),
            "bof_production_inflow": self.get_new_array(dim_letters=("t", "r")),
        }

        # fmt: off

        flw["good_market => use"][...] = stk["in_use"].inflow
        # Pre-use
        flw["imports => good_market"][...] = trd["indirect"].imports
        flw["good_market => exports"][...] = trd["indirect"].exports

        flw["fabrication => good_market"][...] = flw["good_market => use"][...] - trd["indirect"].net_imports

        flw["ip_market => fabrication"][...] = flw["fabrication => good_market"] / prm["fabrication_yield"]
        flw["fabrication => scrap_market"][...] = (flw["ip_market => fabrication"][...] - flw["fabrication => good_market"]) * (1. - prm["fabrication_losses"])
        flw["fabrication => losses"][...] = (flw["ip_market => fabrication"][...] - flw["fabrication => good_market"]) * prm["fabrication_losses"]

        flw["imports => ip_market"][...] = trd["intermediate"].imports
        flw["ip_market => exports"][...] = trd["intermediate"].exports

        flw["forming => ip_market"][...] = flw["ip_market => fabrication"] - trd["intermediate"].net_imports
        aux["production"][...] = flw["forming => ip_market"] / prm["forming_yield"]
        aux["forming_outflow"][...] = aux["production"] - flw["forming => ip_market"]
        flw["forming => losses"][...] = aux["forming_outflow"] * prm["forming_losses"]
        flw["forming => scrap_market"][...] = aux["forming_outflow"] - flw["forming => losses"]

        # Post-use

        flw["use => eol_market"][...] = stk["in_use"].outflow * prm["recovery_rate"]
        flw["use => obsolete"][...] = stk["in_use"].outflow - flw["use => eol_market"]

        flw["imports => eol_market"][...] = trd["scrap"].imports
        flw["eol_market => exports"][...] = trd["scrap"].exports
        aux["net_scrap_trade"][...] = flw["imports => eol_market"] - flw["eol_market => exports"]

        flw["eol_market => recycling"][...] = flw["use => eol_market"] + aux["net_scrap_trade"]
        flw["recycling => scrap_market"][...] = flw["eol_market => recycling"]

        # PRODUCTION

        aux["production_inflow"][...] = aux["production"] / prm["production_yield"]
        aux["max_scrap_production"][...] = aux["production_inflow"] * prm["max_scrap_share_base_model"]
        aux["available_scrap"][...] = (
            flw["recycling => scrap_market"]
            + flw["forming => scrap_market"]
            + flw["fabrication => scrap_market"]
        )
        aux["scrap_in_production"][...] = aux["available_scrap"].minimum(aux["max_scrap_production"])
        flw["scrap_market => excess_scrap"][...] = aux["available_scrap"] - aux["scrap_in_production"]
        aux["scrap_share_production"][...] = aux["scrap_in_production"] / aux["production_inflow"]
        aux["eaf_share_production"][...] = (
            aux["scrap_share_production"]
            - prm["scrap_in_bof_rate"].cast_to(aux["scrap_share_production"].dims)
        )
        aux["eaf_share_production"][...] = aux["eaf_share_production"] / (1 - prm["scrap_in_bof_rate"])
        aux["eaf_share_production"][...] = aux["eaf_share_production"].minimum(1).maximum(0)
        flw["scrap_market => eaf_production"][...] = aux["production_inflow"] * aux["eaf_share_production"]
        flw["scrap_market => bof_production"][...] = aux["scrap_in_production"] - flw["scrap_market => eaf_production"]
        aux["bof_production_inflow"][...] = aux["production_inflow"] - flw["scrap_market => eaf_production"]
        flw["extraction => bof_production"][...] = aux["bof_production_inflow"] - flw["scrap_market => bof_production"]
        flw["bof_production => forming"][...] = aux["bof_production_inflow"] * prm["production_yield"]
        flw["bof_production => losses"][...] = aux["bof_production_inflow"] - flw["bof_production => forming"]
        flw["eaf_production => forming"][...] = flw["scrap_market => eaf_production"] * prm["production_yield"]
        flw["eaf_production => losses"][...] = flw["scrap_market => eaf_production"] - flw["eaf_production => forming"]

        # buffers to sysenv for plotting
        flw["sysenv => imports"][...] = flw["imports => good_market"] + flw["imports => ip_market"] + flw["imports => eol_market"]
        flw["exports => sysenv"][...] = flw["good_market => exports"] + flw["ip_market => exports"] + flw["eol_market => exports"]
        flw["losses => sysenv"][...] = flw["forming => losses"] + flw["fabrication => losses"] + flw["bof_production => losses"] + flw["eaf_production => losses"]
        flw["sysenv => extraction"][...] = flw["extraction => bof_production"]
        # fmt: on

    def compute_other_stocks(self):
        stk = self.stocks
        flw = self.flows

        # in-use stock is already computed in compute_in_use_stock
        stk["obsolete"].inflow[...] = flw["use => obsolete"]
        stk["obsolete"].compute()

        stk["excess_scrap"].inflow[...] = flw["scrap_market => excess_scrap"]
        stk["excess_scrap"].compute()

    @property
    def stock_driven(self) -> bool:
        return self.mode == SteelMode.stock_driven
