import numpy as np
import flodym as fd
from copy import deepcopy

from remind_mfa.common.data_blending import blend
from remind_mfa.common.common_cfg import GeneralCfg
from remind_mfa.common.data_extrapolations import LogSigmoidExtrapolation
from remind_mfa.common.data_transformations import Bound, BoundList
from remind_mfa.common.stock_extrapolation import StockExtrapolation
from remind_mfa.common.custom_data_reader import REMINDMFAReader
from remind_mfa.common.trade import TradeSet
from remind_mfa.steel.steel_export import SteelDataExporter
from remind_mfa.steel.steel_mfa_system_future import SteelMFASystem
from remind_mfa.steel.steel_mfa_system_historic import SteelMFASystemHistoric
from remind_mfa.steel.steel_definition import get_definition, SteelMFADefinition
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.common_mfa_system import CommonMFASystem


class SteelModel:

    def __init__(self, cfg: GeneralCfg):
        self.cfg = cfg

    def run(self):
        stock_driven = self.cfg.customization.mode == "stock_driven"
        self.definition_future = get_definition(self.cfg, historic=False, stock_driven=stock_driven)
        self.read_data(self.definition_future)
        self.modify_parameters()
        self.data_writer = SteelDataExporter(
            cfg=self.cfg.visualization,
            do_export=self.cfg.do_export,
            output_path=self.cfg.output_path,
        )
        if stock_driven:
            self.definition_historic = get_definition(self.cfg, historic=True, stock_driven=False)
            self.historic_mfa = self.make_mfa(historic=True)
            self.historic_mfa.compute()
            stock_projection = self.get_long_term_stock()
            historic_trade = self.historic_mfa.trade_set
        else:
            stock_projection = None
            historic_trade = None

        self.future_mfa = self.make_mfa(historic=False, mode=self.cfg.customization.mode)
        self.future_mfa.compute(stock_projection, historic_trade)

        self.data_writer.export_mfa(mfa=self.future_mfa)
        self.data_writer.visualize_results(model=self)

    def read_data(self, definition: SteelMFADefinition):
        self.data_reader = REMINDMFAReader(
            input_data_path=self.cfg.input_data_path,
            definition=definition,
        )
        self.dims = self.data_reader.read_dimensions(definition.dimensions)
        self.parameters = self.data_reader.read_parameters(definition.parameters, dims=self.dims)

    def modify_parameters(self):
        """Manual changes to parameters in order to match historical scrap consumption."""

        scalar_lifetime_factor = 1.1
        add_assumption_doc(
            type="ad-hoc fix",
            name="overall lifetime factor",
            value=scalar_lifetime_factor,
            description=(
                "Factor multiplied to all lifetime means and standard deviations to match "
                "historical scrap consumption. Standard deviation gets an additional increase "
                "of 1.5 to smooth out unrealistic dips after rapid stock build-up"
            ),
        )
        lifetime_factor = fd.Parameter(dims=self.dims["t", "r"])
        lifetime_factor.values[...] = scalar_lifetime_factor
        self.parameters["lifetime_factor"] = lifetime_factor

        self.parameters["lifetime_mean"] = fd.Parameter(
            dims=self.dims["t", "r", "g"],
            values=(self.parameters["lifetime_factor"] * self.parameters["lifetime_mean"]).values,
        )
        self.parameters["lifetime_std"] = fd.Parameter(
            dims=self.dims["t", "r", "g"],
            values=(self.parameters["lifetime_factor"] * self.parameters["lifetime_std"]).values
            * 1.5,
        )
        construction_lifetime_factor = 1.2
        add_assumption_doc(
            type="ad-hoc fix",
            name="construction lifetime factor",
            value=construction_lifetime_factor,
            description=(
                "Additional factor multiplied to construction lifetime mean and standard deviation "
                "to match historical scrap consumption. The special treatment of construction "
                "is motivated by literature sources suggesting longer building lifetimes than the "
                "used source"
            ),
        )
        self.parameters["lifetime_mean"]["Construction"] = (
            self.parameters["lifetime_mean"]["Construction"] * construction_lifetime_factor
        )
        self.parameters["lifetime_std"]["Construction"] = (
            self.parameters["lifetime_std"]["Construction"] * construction_lifetime_factor
        )

        add_assumption_doc(
            type="ad-hoc fix",
            name="scrap rate factor",
            description=(
                "Time-dependent factor multiplied to forming and fabrication losses to match "
                "historical scrap consumption."
            ),
        )
        scrap_rate_factor = blend(
            target_dims=self.dims["t",],
            y_lower=1.4,
            y_upper=0.8,
            x="t",
            x_lower=1980,
            x_upper=2010,
            type="linear",
        )
        self.parameters["forming_yield"] = fd.Parameter(
            dims=self.dims["t",],
            values=(
                1 - scrap_rate_factor * (1 - self.parameters["forming_yield"].values.mean())
            ).values,
        )
        self.parameters["fabrication_yield"] = fd.Parameter(
            dims=self.dims["t", "g"],
            values=(1 - scrap_rate_factor * (1 - self.parameters["fabrication_yield"])).values,
        )

    def make_mfa(self, historic: bool, mode: str = None) -> CommonMFASystem:
        """
        Splitting production and direct trade by IP sector splits, and indirect trade by category trade sector splits (s. step 3)
        subtracting Losses in steel forming from production by IP data
        adding direct trade by IP to production by IP
        transforming that to production by category via some distribution assumptions
        subtracting losses in steel fabrication (transformation of IP to end use products)
        adding indirect trade by category
        This equals the inflow into the in use stock
        via lifetime assumptions I can calculate in use stock from inflow into in use stock and lifetime
        """
        if historic:
            definition = self.definition_historic
            mfasystem_class = SteelMFASystemHistoric
        else:
            definition = self.definition_future
            mfasystem_class = SteelMFASystem

        processes = fd.make_processes(definition.processes)
        flows = fd.make_empty_flows(
            processes=processes,
            flow_definitions=definition.flows,
            dims=self.dims,
        )
        stocks = fd.make_empty_stocks(
            processes=processes,
            stock_definitions=definition.stocks,
            dims=self.dims,
        )
        trade_set = TradeSet.from_definitions(
            definitions=definition.trades,
            dims=self.dims,
        )

        return mfasystem_class(
            cfg=self.cfg,
            parameters=self.parameters,
            processes=processes,
            dims=self.dims,
            flows=flows,
            stocks=stocks,
            trade_set=trade_set,
            mode=mode,
        )

    def get_long_term_stock(self) -> fd.FlodymArray:
        indep_fit_dim_letters = (
            ("g",) if self.cfg.customization.do_stock_extrapolation_by_category else ()
        )
        historic_stocks = self.historic_mfa.stocks["historic_in_use"].stock
        sat_level = self.get_saturation_level(historic_stocks)
        sat_bound = Bound(
            var_name="saturation_level",
            lower_bound=sat_level,
            upper_bound=sat_level,
            dims=self.dims[indep_fit_dim_letters],
        )
        bound_list = BoundList(
            bound_list=[
                sat_bound,
            ],
            target_dims=self.dims[indep_fit_dim_letters],
        )

        add_assumption_doc(
            type="ad-hoc fix",
            name="stock saturation level factor",
            description=(
                "Region-dependent factor multiplied to regressed saturation level to keep future "
                "steel demand in line with other literature sources."
            ),
        )
        add_assumption_doc(
            type="ad-hoc fix",
            name="stock growth speed factor",
            description=(
                "Region-dependent factor multiplied to regressed stock growth speed to prevent "
                "rapid increase in steel demand and continue historical trends."
            ),
        )
        # scale stocks (y) and gdp (x) to get different vertical and horizontal scalings with just
        # one regression:
        # divide by factor, then regress, then multiply again, which is equivalent to
        # multiplying targets by this factor
        historic_stocks = historic_stocks / self.parameters["saturation_level_factor"]
        gdppc_old = deepcopy(self.parameters["gdppc"])
        self.parameters["gdppc"] = self.parameters["gdppc"] ** self.parameters[
            "stock_growth_speed_factor"
        ] * self.parameters["gdppc"][{"t": 2022}] ** (
            1.0 - self.parameters["stock_growth_speed_factor"]
        )

        # extrapolate in use stock to future
        self.stock_handler = StockExtrapolation(
            historic_stocks,
            dims=self.dims,
            parameters=self.parameters,
            stock_extrapolation_class=self.cfg.customization.stock_extrapolation_class,
            target_dim_letters=(
                "all" if self.cfg.customization.do_stock_extrapolation_by_category else ("t", "r")
            ),
            indep_fit_dim_letters=indep_fit_dim_letters,
            bound_list=bound_list,
        )
        total_in_use_stock = self.stock_handler.stocks

        # scale back stocks and gdp
        total_in_use_stock = total_in_use_stock * self.parameters["saturation_level_factor"]
        self.parameters["gdppc"] = gdppc_old

        if not self.cfg.customization.do_stock_extrapolation_by_category:
            # calculate and apply sector splits for in use stock
            sector_splits = self.calc_stock_sector_splits()
            total_in_use_stock = total_in_use_stock * sector_splits
        return total_in_use_stock

    def get_saturation_level(self, historic_stocks: fd.StockArray):
        pop = self.parameters["population"]
        gdppc = self.parameters["gdppc"]
        historic_pop = pop[{"t": self.dims["h"]}]
        historic_stocks_pc = historic_stocks.sum_over("g") / historic_pop

        multi_dim_extrapolation = LogSigmoidExtrapolation(
            data_to_extrapolate=historic_stocks_pc.values,
            predictor_values=gdppc.values,
            independent_dims=(),
        )
        multi_dim_extrapolation.regress()
        saturation_level = multi_dim_extrapolation.fit_prms[0]

        if self.cfg.customization.do_stock_extrapolation_by_category:
            high_stock_sector_split = self.get_high_stock_sector_split()
            saturation_level = saturation_level * high_stock_sector_split.values

        saturation_level_factor = 0.75
        add_assumption_doc(
            type="ad-hoc fix",
            name="saturation level factor",
            value=saturation_level_factor,
            description=(
                "Factor multiplied to regressed saturation level to reduce future steel demand "
                "in line with other literature sources."
            ),
        )
        saturation_level *= saturation_level_factor

        return saturation_level

    def get_high_stock_sector_split(self):
        prm = self.parameters
        last_lifetime = prm["lifetime_mean"][{"t": self.dims["t"].items[-1]}]
        last_gdppc = prm["gdppc"][{"t": self.dims["t"].items[-1]}]
        av_lifetime = (last_lifetime * last_gdppc).sum_over("r") / last_gdppc.sum_over("r")
        high_stock_sector_split = (av_lifetime * prm["sector_split_high"]).get_shares_over("g")
        return high_stock_sector_split

    def calc_stock_sector_splits(self):
        historical_sector_splits = self.historic_mfa.stocks[
            "historic_in_use"
        ].stock.get_shares_over("g")
        prm = self.parameters
        sector_split_high = self.get_high_stock_sector_split()
        sector_split_theory = blend(
            target_dims=self.dims["t", "r", "g"],
            y_lower=prm["sector_split_low"],
            y_upper=sector_split_high,
            x=prm["gdppc"].apply(np.log),
            x_lower=float(np.log(1000)),
            x_upper=float(np.log(100000)),
        )
        last_historical = historical_sector_splits[{"h": self.dims["h"].items[-1]}]
        historical_extrapolated = last_historical.cast_to(self.dims["t", "r", "g"])
        historical_extrapolated[{"t": self.dims["h"]}] = historical_sector_splits
        sector_splits = blend(
            target_dims=self.dims["t", "r", "g"],
            y_lower=historical_extrapolated,
            y_upper=sector_split_theory,
            x="t",
            x_lower=self.dims["h"].items[-1],
            x_upper=self.dims["t"].items[-1],
            type="converge_quadratic",
        )
        return sector_splits
