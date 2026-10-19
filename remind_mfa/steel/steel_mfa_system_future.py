import numpy as np
import flodym as fd

from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.trade import TradeSet, Trade
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
            "new_scrap": fd.Parameter(dims=self.dims["t", "r"]),
        }

        # fmt: off

        flw["manufactured_products_market => use"][...] = stk["use"].inflow
        # Pre-use

        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["manufactured_products"],
            future_trade=trd["manufactured_products"],
            future_dom_demand=flw["manufactured_products_market => use"],
            n_trend_years=self.parameters["n_trend_years"],
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
            n_trend_years=self.parameters["n_trend_years"],
        )
        extrapolator.run()

        flw["imports => steel_market"][...] = trd["steel"].imports
        flw["steel_market => exports"][...] = trd["steel"].exports

        flw["forming => steel_market"][...] = flw["steel_market => manufacturing"] - trd["steel"].net_imports
        aux["steel_production"][...] = flw["forming => steel_market"] / prm["forming_yield"]
        flw["forming => losses"][...] = aux["steel_production"] * prm["forming_loss_rate"]
        flw["forming => scrap_pool"][...] = aux["steel_production"] - flw["forming => steel_market"] - flw["forming => losses"]

        # Post-use

        flw["use => hibernating"][...] = stk["use"].outflow * prm["hibernation_share"]
        flw["use => eol_management"][...] = stk["use"].outflow - flw["use => hibernating"]
        flw["eol_management => scrap_market"][...] = flw["use => eol_management"] * prm["recovery_rate"]
        flw["eol_management => losses"][...] = flw["use => eol_management"] - flw["eol_management => scrap_market"]

        extrapolator = TradeExtrapolator(
            historical_trade=historical_trade["scrap"],
            future_trade=trd["scrap"],
            future_dom_supply=flw["eol_management => scrap_market"],
            n_trend_years=self.parameters["n_trend_years"],
        )
        extrapolator.run()

        aux["production_inflow"][...] = aux["steel_production"] / (1 - prm["steel_production_loss_rate"])
        aux["max_scrap_production"][...] = aux["production_inflow"] * prm["max_scrap_share"]
        aux["new_scrap"][...] = flw["forming => scrap_pool"] + flw["manufacturing => scrap_pool"]
        self.cap_scrap_imports_to_usable_scrap(
            max_scrap_production=aux["max_scrap_production"],
            domestic_scrap=flw["eol_management => scrap_market"].sum_over("u") + aux["new_scrap"],
        )
        self.redistribute_excess_scrap(
            max_scrap_production=aux["max_scrap_production"],
            eol_scrap=flw["eol_management => scrap_market"].sum_over("u"),
            new_scrap=aux["new_scrap"],
        )

        flw["imports => scrap_market"][...] = trd["scrap"].imports
        flw["scrap_market => exports"][...] = trd["scrap"].exports

        flw["scrap_market => scrap_pool"][...] = flw["eol_management => scrap_market"] + trd["scrap"].net_imports

        # PRODUCTION

        aux["available_scrap"][...] = (
            flw["scrap_market => scrap_pool"]
            + flw["forming => scrap_pool"]
            + flw["manufacturing => scrap_pool"]
        )
        flw["scrap_pool => steel_production_scrap_based"][...] = aux["available_scrap"].minimum(aux["max_scrap_production"])
        flw["scrap_pool => excess_scrap"][...] = aux["available_scrap"] - flw["scrap_pool => steel_production_scrap_based"]

        flw["extraction => steel_production_ore_based"][...] = aux["production_inflow"] - flw["scrap_pool => steel_production_scrap_based"]
        flw["steel_production_ore_based => forming"][...] = flw["extraction => steel_production_ore_based"] * (1 - prm["steel_production_loss_rate"])
        flw["steel_production_ore_based => losses"][...] = flw["extraction => steel_production_ore_based"] - flw["steel_production_ore_based => forming"]
        flw["steel_production_scrap_based => forming"][...] = flw["scrap_pool => steel_production_scrap_based"] * (1 - prm["steel_production_loss_rate"])
        flw["steel_production_scrap_based => losses"][...] = flw["scrap_pool => steel_production_scrap_based"] - flw["steel_production_scrap_based => forming"]

        # buffers to sysenv for plotting
        flw["sysenv => imports"][...] = flw["imports => manufactured_products_market"] + flw["imports => steel_market"] + flw["imports => scrap_market"]
        flw["exports => sysenv"][...] = flw["manufactured_products_market => exports"] + flw["steel_market => exports"] + flw["scrap_market => exports"]
        flw["losses => sysenv"][...] = flw["forming => losses"] + flw["manufacturing => losses"] + flw["steel_production_ore_based => losses"] + flw["steel_production_scrap_based => losses"] + flw["eol_management => losses"]
        flw["sysenv => extraction"][...] = flw["extraction => steel_production_ore_based"]
        # fmt: on

    def cap_scrap_imports_to_usable_scrap(
        self, max_scrap_production: fd.FlodymArray, domestic_scrap: fd.FlodymArray
    ):
        """Limit future scrap net imports to the amount a region can use in steel production.

        The extrapolated scrap trade follows historical trade patterns and does not know how much
        scrap a region can absorb. Without this cap, regions that already have more domestic
        scrap than their steel production can take would import scrap only to divert it to
        excess scrap, while the exporting regions lack it for their own secondary production.
        The cap removes such imports and the exporting regions keep the scrap instead.
        Historical years keep the historical trade data.

        Args:
            max_scrap_production: Maximum scrap input to steel production.
            domestic_scrap: Scrap generated in the region (home, new and collected end-of-life
                scrap) before trade.
        """
        add_assumption_doc(
            type="model assumption",
            name="No scrap imports beyond usable scrap",
            description=(
                "Future scrap net imports of a region are limited to the difference between "
                "the maximum scrap input to its steel production and its domestic scrap. "
                "Scrap that is not imported remains in the exporting regions."
            ),
        )
        capacity = (max_scrap_production - domestic_scrap).maximum(0)
        capacity[{"t": self.dims["h"]}] = np.inf
        self.cap_net_imports_to_capacity(self.trade_set["scrap"], capacity=capacity)

    def redistribute_excess_scrap(
        self,
        max_scrap_production: fd.FlodymArray,
        eol_scrap: fd.FlodymArray,
        new_scrap: fd.FlodymArray,
    ):
        """Redistribute scrap that would become excess scrap to regions that can still use it.

        An auxiliary scrap trade is computed with :meth:`redistribute_surplus` and added to the
        scrap trade: Regions whose available scrap after the extrapolated scrap trade exceeds the
        maximum scrap input to their steel production export the surplus; regions below that
        maximum import it. This reduces excess scrap and increases scrap-based steel production
        in the importing regions. Historical years keep the historical trade data.

        Args:
            max_scrap_production: Maximum scrap input to steel production.
            eol_scrap: Collected end-of-life scrap before trade.
            new_scrap: Home and new scrap from forming and manufacturing.
        """
        add_assumption_doc(
            type="model assumption",
            name="Redistribution of excess scrap",
            description=(
                "Future scrap that exceeds the maximum scrap input to a region's steel "
                "production is exported to regions that have not reached that maximum, "
                "in proportion to their remaining capacity."
            ),
        )
        scrap_trade = self.trade_set["scrap"]
        available_scrap = eol_scrap + scrap_trade.net_imports + new_scrap
        # The scrap trade passes the scrap market, which holds only end-of-life scrap. Raising the
        # demand to the new scrap keeps aux exports below the end-of-life scrap after trade, so
        # the flow to the scrap pool stays non-negative. This does not change any region's headroom.
        demand = max_scrap_production.maximum(new_scrap)
        aux_trade = Trade(
            name="aux_scrap",
            imports=fd.FlodymArray(dims=scrap_trade.imports.dims),
            exports=fd.FlodymArray(dims=scrap_trade.exports.dims),
        )
        self.redistribute_surplus(aux_trade, supply=available_scrap, demand=demand)
        for flow in (aux_trade.imports, aux_trade.exports):
            flow[{"t": self.dims["h"]}] = 0.0
        scrap_trade.imports[...] = scrap_trade.imports + aux_trade.imports
        scrap_trade.exports[...] = scrap_trade.exports + aux_trade.exports

    def compute_other_stocks(self):
        stk = self.stocks
        flw = self.flows

        # in-use stock is already computed in compute_use_stock
        stk["hibernating"].inflow[...] = flw["use => hibernating"]
        stk["hibernating"].compute()

        stk["excess_scrap"].inflow[...] = flw["scrap_pool => excess_scrap"]
        stk["excess_scrap"].compute()
