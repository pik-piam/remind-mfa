import flodym as fd

from remind_mfa.common.trade import TradeSet
from remind_mfa.common.trade_extrapolation import TradeExtrapolator
from remind_mfa.common.price_driven_trade import PriceDrivenTrade
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.steel.steel_config import SteelCfg


class SteelMFASystem(CommonMFASystem):

    cfg: SteelCfg

    def compute(self, stock_projection: fd.FlodymArray, historical_trade: TradeSet):
        """
        Perform all computations for the MFA system.
        """
        self.compute_use_stock(stock_projection)
        self.compute_flows(historical_trade)
        self.compute_other_stocks()
        self.check_mass_balance()
        self.check_flows(raise_error=False)
        # self.update_price_elastic()

    def update_price_elastic(self):
        self.compute_price_elastic_trade()
        # self.compute_consumption()
        # self.compute_use_stock() # ensure inflow-driven
        # self.compute_other_flows()
        # self.compute_other_stocks()

        # self.check_mass_balance()
        # self.check_flows(raise_error=False)

    def compute_price_elastic_trade(self):
        price = fd.FlodymArray(dims=self.dims["t", "r"])
        price[...] = 500.0
        # price.values[131:201,2] = np.minimum(800., np.linspace(500, 2000, 70))
        model = PriceDrivenTrade(dims=self.trade_set["steel"].exports.dims)
        model.calibrate(
            demand=self.flows["steel_market => manufacturing"][2022],
            price=price[2022],
            imports_target=self.trade_set["steel"].imports[2022],
            exports_target=self.trade_set["steel"].exports[2022],
        )
        price, demand, supply, imports, exports = model.compute_price_driven_trade(
            price_0=price,
            demand_0=self.flows["steel_market => manufacturing"],
            supply_0=self.flows["forming => steel_market"],
        )

        self.flows["steel_market => manufacturing"][...] = demand
        self.flows["forming => steel_market"][...] = supply
        self.trade_set["steel"].imports[...] = imports
        self.trade_set["steel"].exports[...] = exports
        self.trade_set["steel"].balance()

        self.flows["imports => steel_market"][...] = self.trade_set["steel"].imports
        self.flows["steel_market => exports"][...] = self.trade_set["steel"].exports

    def compute_use_stock(self, stock_projection):
        self.stocks["use"].stock[...] = stock_projection
        self.stocks["use"].lifetime_model.set_prms(
            mean=self.parameters["lifetime_mean"], std=self.parameters["lifetime_std"]
        )
        self.stocks["use"].compute()
        self.correct_negative_inflow("use")

    def compute_flows(self, historical_trade: TradeSet):
        # abbreviations for better readability
        prm = self.parameters
        flw = self.flows
        stk = self.stocks
        trd = self.trade_set

        aux = {
            "steel_production": fd.Parameter(dims=self.dims["t", "r"]),
            "available_scrap": fd.Parameter(dims=self.dims["t", "r"]),
            "production_inflow": fd.Parameter(dims=self.dims["t", "r"]),
            "max_scrap_production": fd.Parameter(dims=self.dims["t", "r"]),
        }

        # fmt: off

        flw["manufactured_products_market => use"][...] = stk["use"].inflow
        # Pre-use

        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["manufactured_products"],
            future_trade=trd["manufactured_products"],
            future_dom_demand=flw["manufactured_products_market => use"],
        )
        extrapolator.run()

        flw["imports => manufactured_products_market"][...] = trd["manufactured_products"].imports
        flw["manufactured_products_market => exports"][...] = trd["manufactured_products"].exports

        flw["manufacturing => manufactured_products_market"][...] = flw["manufactured_products_market => use"][...] - trd["manufactured_products"].net_imports

        flw["steel_market => manufacturing"][...] = flw["manufacturing => manufactured_products_market"] / prm["aggregate_manufacturing_yield"]
        flw["manufacturing => scrap_pool"][...] = (flw["steel_market => manufacturing"][...] - flw["manufacturing => manufactured_products_market"]) * (1. - prm["manufacturing_losses"])
        flw["manufacturing => losses"][...] = (flw["steel_market => manufacturing"][...] - flw["manufacturing => manufactured_products_market"]) * prm["manufacturing_losses"]

        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["steel"],
            future_trade=trd["steel"],
            future_dom_demand=flw["steel_market => manufacturing"],
        )
        extrapolator.run()

        flw["imports => steel_market"][...] = trd["steel"].imports
        flw["steel_market => exports"][...] = trd["steel"].exports

        flw["forming => steel_market"][...] = flw["steel_market => manufacturing"] - trd["steel"].net_imports
        aux["steel_production"][...] = flw["forming => steel_market"] / prm["forming_yield"]
        flw["forming => losses"][...] = aux["steel_production"] * prm["forming_loss_rate"]
        flw["forming => scrap_pool"][...] = aux["steel_production"] - flw["forming => steel_market"] - flw["forming => losses"]

        # Post-use

        flw["use => scrap_market"][...] = stk["use"].outflow * prm["recovery_rate"]
        flw["use => obsolete"][...] = stk["use"].outflow - flw["use => scrap_market"]

        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["scrap"],
            future_trade=trd["scrap"],
            future_dom_supply=flw["use => scrap_market"],
        )
        extrapolator.run()

        flw["imports => scrap_market"][...] = trd["scrap"].imports
        flw["scrap_market => exports"][...] = trd["scrap"].exports

        flw["scrap_market => recycling"][...] = flw["use => scrap_market"] + trd["scrap"].net_imports
        flw["recycling => scrap_pool"][...] = flw["scrap_market => recycling"]

        # PRODUCTION

        aux["production_inflow"][...] = aux["steel_production"] / (1 - prm["steel_production_loss_rate"])
        aux["max_scrap_production"][...] = aux["production_inflow"] * 0.7 #TODO: make a parameter
        aux["available_scrap"][...] = (
            flw["recycling => scrap_pool"]
            + flw["forming => scrap_pool"]
            + flw["manufacturing => scrap_pool"]
        )
        flw["scrap_pool => steel_production_scrap_based"][...] = aux["available_scrap"].minimum(aux["max_scrap_production"])
        flw["scrap_pool => excess_scrap"][...] = aux["available_scrap"] - flw["scrap_pool => steel_production_scrap_based"]

        flw["extraction => steel_production_ore_based"][...] = aux["production_inflow"] - flw["scrap_pool => steel_production_scrap_based"]
        flw["extraction => steel_production_ore_based"][...] = flw["extraction => steel_production_ore_based"] - flw["scrap_pool => steel_production_ore_based"]
        flw["steel_production_ore_based => forming"][...] = flw["extraction => steel_production_ore_based"] * (1 - prm["steel_production_loss_rate"])
        flw["steel_production_ore_based => losses"][...] = flw["extraction => steel_production_ore_based"] - flw["steel_production_ore_based => forming"]
        flw["steel_production_scrap_based => forming"][...] = flw["scrap_pool => steel_production_scrap_based"] * (1 - prm["steel_production_loss_rate"])
        flw["steel_production_scrap_based => losses"][...] = flw["scrap_pool => steel_production_scrap_based"] - flw["steel_production_scrap_based => forming"]

        # buffers to sysenv for plotting
        flw["sysenv => imports"][...] = flw["imports => manufactured_products_market"] + flw["imports => steel_market"] + flw["imports => scrap_market"]
        flw["exports => sysenv"][...] = flw["manufactured_products_market => exports"] + flw["steel_market => exports"] + flw["scrap_market => exports"]
        flw["losses => sysenv"][...] = flw["forming => losses"] + flw["manufacturing => losses"] + flw["steel_production_ore_based => losses"] + flw["steel_production_scrap_based => losses"]
        flw["sysenv => extraction"][...] = flw["extraction => steel_production_ore_based"]
        # fmt: on

    def compute_other_stocks(self):
        stk = self.stocks
        flw = self.flows

        # in-use stock is already computed in compute_use_stock
        stk["obsolete"].inflow[...] = flw["use => obsolete"]
        stk["obsolete"].compute()

        stk["excess_scrap"].inflow[...] = flw["scrap_pool => excess_scrap"]
        stk["excess_scrap"].compute()
