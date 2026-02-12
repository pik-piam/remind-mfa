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
from remind_mfa.steel.steel_mappings import SteelDimensionFiles, SteelDisplayNames
from remind_mfa.steel.steel_visualization import SteelVisualizer
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.common_model import CommonModel
from remind_mfa.steel.steel_definition import scenario_parameters as steel_scn_prm_def


class SteelModel(CommonModel):

    ConfigCls = SteelCfg
    DimensionFilesCls = SteelDimensionFiles
    DataExporterCls = SteelDataExporter
    VisualizerCls = SteelVisualizer
    DisplayNamesCls = SteelDisplayNames
    HistoricMFASystemCls = SteelMFASystemHistoric
    FutureMFASystemCls = SteelMFASystem
    get_definition = staticmethod(get_steel_definition)
    custom_scn_prm_def = steel_scn_prm_def

    def modify_parameters(self):
        """Manual changes to parameters in order to match historical scrap consumption."""

        lifetime_factor = blend(
            target_dims=self.dims["t",],
            y_lower=0.9,
            y_upper=1.1,
            x="t",
            x_lower=1970,
            x_upper=2020,
            type="linear",
        )
        add_assumption_doc(
            type="ad-hoc fix",
            name="overall lifetime factor",
            description=(
                "Time-dependent factor multiplied to all lifetime means and standard deviations to match "
                "historical scrap consumption. Standard deviation gets an additional increase "
                "of 1.5 to smooth out unrealistic dips after rapid stock build-up"
            ),
        )
        lifetime_factor_prm = fd.Parameter(dims=self.dims["t",])
        lifetime_factor_prm[...] = lifetime_factor
        self.parameters["lifetime_factor"] = lifetime_factor_prm

        self.parameters["lifetime_mean"] = fd.Parameter(
            dims=self.dims["t", "g"],
            values=(self.parameters["lifetime_factor"] * self.parameters["lifetime_mean"]).values,
        )
        self.parameters["lifetime_std"] = fd.Parameter(
            dims=self.dims["t", "g"],
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
        self.parameters["recovery_rate"] = fd.Parameter(
            dims=self.dims["r", "g"],
            values=self.parameters["recovery_rate"].cast_to(self.dims["r", "g"]).values * 0.85,
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
            y_upper=0.75,
            x="t",
            x_lower=1970,
            x_upper=2020,
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
        self.parameters["sector_split_high"]["Products"] *= 1.5
        self.parameters["sector_split_high"][...] = self.parameters["sector_split_high"].get_shares_over("g")

    def get_long_term_stock(self) -> fd.FlodymArray:

        saturation_level = 11
        arr = self.get_high_stock_sector_split() * saturation_level
        bound = Bound(
            var_name="saturation_level",
            lower_bound=arr,
            upper_bound=arr,
        )
        historic_stocks = self.historic_mfa.stocks["historic_in_use"].stock

        # 1) common regression
        indep_fit_dim_letters = ("g",)

        bound_list_obj = BoundList(
            target_dims=self.dims[indep_fit_dim_letters],
            bound_list=[bound],
        )

        self.stock_handler = StockExtrapolation(
            cfg=self.cfg.model_switches,
            historic_stocks=historic_stocks,
            dims=self.dims,
            parameters=self.parameters,
            target_dim_letters="all",
            indep_fit_dim_letters=indep_fit_dim_letters,
            bound_list=bound_list_obj,
        )
        self.stock_handler.extrapolate()
        return self.stock_handler.stocks


    def get_high_stock_sector_split(self):
        prm = self.parameters
        last_lifetime = prm["lifetime_mean"][{"t": self.dims["t"].items[-1]}]
        last_gdppc = prm["gdppc"][{"t": self.dims["t"].items[-1]}]
        av_lifetime = (last_lifetime * last_gdppc).sum_over("r") / last_gdppc.sum_over("r")
        high_stock_sector_split = (av_lifetime * prm["sector_split_high"]).get_shares_over("g")
        return high_stock_sector_split
