import logging
from copy import deepcopy

import flodym as fd
import numpy as np

from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.trade import Trade, TradeSet
from remind_mfa.common.trade_extrapolation import TradeExtrapolator, FixedSupplyTradeExtrapolator
from remind_mfa.common.price_driven_trade import PriceDrivenTrade
from remind_mfa.common.common_definition import EU_MFA_REGION
from remind_mfa.common.common_mfa_system import CommonMFASystem
from remind_mfa.steel.steel_config import SteelCfg


class SteelMFASystem(CommonMFASystem):

    cfg: SteelCfg

    def compute(
        self,
        stock_projection: fd.FlodymArray,
        historical_trade: TradeSet,
        baseline_trade: TradeSet,
        baseline_flows: dict,
    ):
        """
        Perform all computations for the MFA system.
        """
        self.compute_use_stock(stock_projection)
        self.compute_flows(historical_trade, baseline_trade, baseline_flows)
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

    def compute_use_stock(self, stock_projection: fd.FlodymArray):
        super().compute_use_stock(stock_projection)

        if self.cfg.transience.transience_run == True:
            # TODO extrapolate EU-MFA data or run MFA only until 2050
            self.demand_EU_MFA = self.parameters["stock_inflow_EU-MFA"][{"r": EU_MFA_REGION}]
            # store original inflow for comparison
            self.demand_REMIND_MFA = self.stocks["use"].inflow[
                {"r": EU_MFA_REGION, "u": self.dims["f"], "t": self.dims["v"]}
            ]
            # Replace with EU-MFA data
            inflow = self.stocks["use"].inflow
            self.stocks["use"] = fd.InflowDrivenDSM(
                dims=self.stocks["use"].dims,
                lifetime_model=self.stocks["use"].lifetime_model,
                name=self.stocks["use"].name,
                process=self.stocks["use"].process,
            )
            self.stocks["use"].inflow[...] = inflow
            self.stocks["use"].inflow[
                {"r": EU_MFA_REGION, "u": self.dims["f"], "t": self.dims["v"]}
            ] = self.demand_EU_MFA
            self.stocks["use"].compute()
            # store original outflow (generated from EU-MFA inflow and REMIND-MFA lifetime model) for comparison
            self.stock_outflow_REMIND_MFA = self.stocks["use"].outflow[
                {"r": EU_MFA_REGION, "u": self.dims["f"], "t": self.dims["v"]}
            ]
            # Replace with EU-MFA data
            self.stock_outflow_EU_MFA = self.parameters["stock_outflow_EU-MFA"]
            inflow = self.stocks["use"].inflow
            outflow = self.stocks["use"].outflow
            self.stocks["use"] = fd.SimpleFlowDrivenStock(
                dims=self.stocks["use"].dims,
                lifetime_model=self.stocks["use"].lifetime_model,
                name=self.stocks["use"].name,
                process=self.stocks["use"].process,
            )
            self.stocks["use"].inflow[...] = inflow
            self.stocks["use"].inflow[
                {"r": EU_MFA_REGION, "u": self.dims["f"], "t": self.dims["v"]}
            ] = self.demand_EU_MFA
            self.stocks["use"].outflow[...] = outflow
            self.stocks["use"].outflow[
                {"r": EU_MFA_REGION, "u": self.dims["f"], "t": self.dims["v"]}
            ] = self.stock_outflow_EU_MFA
            self.stocks["use"].compute()
            logging.warning(
                f"TRANSIENCE mode is on. Both in-use stock inflow and outflow for EUR region are not computed from stock projection, but taken from EU-MFA. "
                f"The stock is calculated as a simple flow-driven stock. "
            )

    def compute_flows(
        self, historical_trade: TradeSet, baseline_trade: TradeSet, baseline_flows: dict
    ):
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
            "not_reused": fd.Parameter(dims=self.dims["t", "r", "u"]),
        }

        # fmt: off

        # Hibernation and reuse first, since reuse reduces the demand for new products
        # reuse: a share of the not hibernating in-use outflow re-enters the stock, capped by the stock inflow
        flw["use => hibernating"][...] = self.compute_hibernation(stk["use"].outflow)
        flw["use => eol_management"][...] = stk["use"].outflow - flw["use => hibernating"]
        flw["eol_management => reuse"][...] = (flw["use => eol_management"] * prm["reuse_share"]).minimum(stk["use"].inflow)
        flw["reuse => use"][...] = flw["eol_management => reuse"]

        # Pre-use

        flw["manufactured_products_market => use"][...] = stk["use"].inflow - flw["reuse => use"]

        if "manufactured_products" in self.get_trade_markets_from_data():
            self.set_trade_from_data("manufactured_products", historical_trade["manufactured_products"])
        else:
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

        if "steel" in self.get_trade_markets_from_data():
            self.set_trade_from_data("steel", historical_trade["steel"])
        elif self.cfg.transience.trade_scenario in ("fix_supply_alpha0", "fix_supply_alpha1"):
            if self.cfg.transience.baseline_pickle_path is None:
                raise ValueError("TRANSIENCE trade extrapolation scenario 'fix_supply' requires a baseline_pickle_path to be provided in the config. Please provide a valid path or choose a different trade extrapolation scenario.")
            alpha = 0.0 if self.cfg.transience.trade_scenario == "fix_supply_alpha0" else 1.0
            # default extrapolation with the new (scenario) demand, used where demand
            # exceeds baseline and fixing supply is not defensible. (For steel this case
            # is currently not triggered, as CE measures only decrease demand.)
            default_trade = deepcopy(self.trade_set["steel"])
            TradeExtrapolator(
                historical_trade=historical_trade["steel"],
                future_trade=default_trade,
                future_dom_demand=flw["steel_market => manufacturing"],
                n_trend_years=self.parameters["n_trend_years"],
            ).run()
            extrapolator = FixedSupplyTradeExtrapolator(
                historic_trade = historical_trade["steel"],
                baseline_future_trade = baseline_trade["steel"],
                default_future_trade = default_trade,
                future_trade = self.trade_set["steel"],
                baseline_dom_demand = baseline_flows["steel_market => manufacturing"],
                future_dom_demand = flw["steel_market => manufacturing"],
                import_adjustment_share = alpha,
            )
            extrapolator.run()
        else:
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

        # recovery applies to the non-reused part of the demolished outflow
        aux["not_reused"][...] = flw["use => eol_management"] - flw["eol_management => reuse"]
        flw["eol_management => scrap_market"][...] = aux["not_reused"] * prm["recovery_rate"]
        flw["eol_management => eol_waste"][...] = aux["not_reused"] - flw["eol_management => scrap_market"]

        if self.cfg.transience.transience_run == True:
            # historical scrap trade needs to be scaled down to not exceed the EU-MFA stock outflow * recovery_rate (which would be the case for 1903-1950)
            # in a normal run, this happens in the historical MFA, but since we replaced the stock outflow with EU-MFA data, we need to ensure the scrap trade is consistent with this
            historical_trade["scrap"].exports[...] = historical_trade["scrap"].exports.minimum(flw["eol_management => scrap_market"][{"t": self.dims["h"]}])
            historical_trade["scrap"].balance(to="minimum")

        aux["production_inflow"][...] = aux["steel_production"] / (1 - prm["steel_production_loss_rate"])
        aux["max_scrap_production"][...] = aux["production_inflow"] * prm["max_scrap_share"]

        if "scrap" in self.get_trade_markets_from_data():
            self.set_trade_from_data("scrap", historical_trade["scrap"])
        else:
            extrapolator = TradeExtrapolator(
                historical_trade=historical_trade["scrap"],
                future_trade=trd["scrap"],
                future_dom_supply=flw["eol_management => scrap_market"],
                n_trend_years=self.parameters["n_trend_years"],
            )
            extrapolator.run()

            # trade read from data is used as given; only the extrapolated trade is adjusted to
            # the scrap the regions can use
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
        flw["losses => sysenv"][...] = flw["forming => losses"] + flw["manufacturing => losses"] + flw["steel_production_ore_based => losses"] + flw["steel_production_scrap_based => losses"]
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

        # in-use stock is already computed in compute_use_stock,
        # hibernating stock in compute_flows
        stk["eol_waste"].inflow[...] = flw["eol_management => eol_waste"]
        stk["eol_waste"].compute()

        stk["excess_scrap"].inflow[...] = flw["scrap_pool => excess_scrap"]
        stk["excess_scrap"].compute()
