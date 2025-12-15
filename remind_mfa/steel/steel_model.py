import numpy as np
import flodym as fd
from copy import deepcopy

from remind_mfa.common.data_blending import blend
from remind_mfa.common.data_transformations import Bound, BoundList
from remind_mfa.common.stock_extrapolation import StockExtrapolation
from remind_mfa.steel.steel_export import SteelDataExporter
from remind_mfa.steel.steel_mfa_system_future import SteelMFASystem
from remind_mfa.steel.steel_mfa_system_historic import SteelMFASystemHistoric
from remind_mfa.steel.steel_definition import get_steel_definition
from remind_mfa.steel.steel_config import SteelCfg
from remind_mfa.steel.steel_data_reader import SteelDataReader
from remind_mfa.steel.steel_visualization import SteelVisualizer
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.common_model import CommonModel
from remind_mfa.steel.steel_definition import scenario_parameters as steel_scn_prm_def


class SteelModel(CommonModel):

    ConfigCls = SteelCfg
    DataReaderCls = SteelDataReader
    DataExporterCls = SteelDataExporter
    VisualizerCls = SteelVisualizer
    HistoricMFASystemCls = SteelMFASystemHistoric
    FutureMFASystemCls = SteelMFASystem
    get_definition = staticmethod(get_steel_definition)
    custom_scn_prm_def = steel_scn_prm_def

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

    def get_long_term_stock(self) -> fd.FlodymArray:
        indep_fit_dim_letters = (
            ("g",) if self.cfg.model_switches.do_stock_extrapolation_by_category else ()
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
            cfg=self.cfg.model_switches,
            historic_stocks=historic_stocks,
            dims=self.dims,
            parameters=self.parameters,
            target_dim_letters=(
                "all" if self.cfg.model_switches.do_stock_extrapolation_by_category else ("t", "r")
            ),
            indep_fit_dim_letters=indep_fit_dim_letters,
            bound_list=bound_list,
        )
        total_in_use_stock = self.stock_handler.stocks

        # scale back stocks and gdp
        total_in_use_stock = total_in_use_stock * self.parameters["saturation_level_factor"]
        self.parameters["gdppc"] = gdppc_old

        if not self.cfg.model_switches.do_stock_extrapolation_by_category:
            # calculate and apply sector splits for in use stock
            sector_splits = self.calc_stock_sector_splits()
            total_in_use_stock = total_in_use_stock * sector_splits
        return total_in_use_stock

    def get_saturation_level(self, historic_stocks: fd.StockArray):
        pop = self.parameters["population"]
        gdppc = self.parameters["gdppc"]
        historic_pop = pop[{"t": self.dims["h"]}]
        historic_stocks_pc = historic_stocks.sum_over("g") / historic_pop

        multi_dim_extrapolation = self.cfg.model_switches.stock_extrapolation_class(
            data_to_extrapolate=historic_stocks_pc.values,
            predictor_values=np.log10(gdppc.values),
            independent_dims=(),
        )
        multi_dim_extrapolation.regress()
        saturation_level = multi_dim_extrapolation.fit_prms[0]

        if self.cfg.model_switches.do_stock_extrapolation_by_category:
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
