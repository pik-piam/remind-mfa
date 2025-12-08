import numpy as np

import flodym as fd

from remind_mfa.cement.cement_config import CementCfg
from remind_mfa.common.data_transformations import Bound, BoundList
from remind_mfa.cement.cement_definition import get_cement_definition
from remind_mfa.cement.cement_mfa_system_historic import (
    InflowDrivenHistoricCementMFASystem,
)
from remind_mfa.cement.cement_mfa_system_historic import InflowDrivenHistoricCementMFASystem
from remind_mfa.cement.cement_mfa_system_future import StockDrivenCementMFASystem
from remind_mfa.cement.cement_mappings import CementDimensionFiles, CementDisplayNames
from remind_mfa.cement.cement_export import CementDataExporter
from remind_mfa.cement.cement_visualization import CementVisualizer
from remind_mfa.common.stock_extrapolation import StockExtrapolation
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.common_model import CommonModel
from remind_mfa.cement.cement_definition import scenario_parameters as cement_scn_prm_def


class CementModel(CommonModel):

    ConfigCls = CementCfg
    DimensionFilesCls = CementDimensionFiles
    DataExporterCls = CementDataExporter
    VisualizerCls = CementVisualizer
    DisplayNamesCls = CementDisplayNames
    HistoricMFASystemCls = InflowDrivenHistoricCementMFASystem
    FutureMFASystemCls = StockDrivenCementMFASystem
    get_definition = staticmethod(get_cement_definition)
    custom_scn_prm_def = cement_scn_prm_def

    def get_long_term_stock(self) -> fd.FlodymArray:
        """Extrapolate in use stock to future."""

        indep_fit_dim_letters = ("r",)

        # 1) constrain saturation level
        region_sat = fd.FlodymArray(
            dims=self.dims[("r",)],
            values=np.array([20, 20, 20, 24, 24, 20, 20, 18, 30, 20, 18, 18]),
        )
        sat_bound = Bound(
            var_name="saturation_level",
            lower_bound=region_sat,
            upper_bound=region_sat,
        )
        add_assumption_doc(
            type="expert guess",
            value=region_sat.values,
            name="Saturation level of in-use cement stock extrapolation",
            description="The saturation level of the in-use cement stock (T/cap) "
            "is set individually for each region, based on historic trends.",
        )

        # 2) constrain growth rate
        max_growth_rate = (
            25  # t/cap per tenfold GDP increase, inferred from China #self.get_max_growth_rate()
        )
        max_stretch_factor = 4 * max_growth_rate / region_sat
        min_stretch_factor = fd.FlodymArray(
            dims=self.dims[("r",)], values=np.zeros_like(max_stretch_factor.values)
        )

        # remove stretch factor limitations in industrialized regions
        industrialized_regions = ["EUR", "NEU", "CAZ", "CHA", "JPN", "USA"]
        ind_indices = [
            self.historic_mfa.stocks["historic_cement_in_use"].stock.dims["r"].items.index(r)
            for r in industrialized_regions
        ]
        max_stretch_factor.values[ind_indices] = np.inf

        stretch_bound = Bound(
            var_name="stretch_factor",
            lower_bound=min_stretch_factor,
            upper_bound=max_stretch_factor,
        )

        add_assumption_doc(
            type="expert guess",
            value=max_growth_rate,
            name="Maximum growth rate of in-use cement stock extrapolation ",
            description="The maximum growth rate of the in-use cement stock (T/cap per tenfold GDP increase) is set based "
            " on historic trends in industrialized regions, where China shows the highest continuous growth rate. "
            "The maximum growth rate informs the upper bound of the stretch factor in the stock extrapolation "
            "for countries with low historic stock levels. ",
        )

        # 3) constrain offset
        # Currently, this does not change anything as no region seems to be faster given the above constraints
        min_offset = 8.8e3  # $gdppc at which 50% of saturation is reached, inferred from China (fastest region)
        offset_bound = Bound(
            var_name="x_offset",
            lower_bound=min_offset,
            upper_bound=np.inf,
        )

        add_assumption_doc(
            type="expert guess",
            value=min_offset,
            name="Minimum offset of in-use cement stock extrapolation",
            description="The minimum offset of the in-use cement stock ($gdppc where 50 percent of saturation is reached) "
            "is set based on historic trends in China which has grown its stock at the lowest GDP levels. ",
        )

        # 4) combine bounds
        bound_list = BoundList(
            bound_list=[sat_bound, stretch_bound, offset_bound],
            target_dims=self.dims[indep_fit_dim_letters],
        )

        # 5) extrapolate stock
        self.stock_handler = StockExtrapolation(
            cfg=self.cfg.model_switches,
            historic_stocks=self.historic_mfa.stocks["historic_cement_in_use"].stock,
            dims=self.dims,
            parameters=self.parameters,
            target_dim_letters=("t", "r"),
            indep_fit_dim_letters=indep_fit_dim_letters,
            bound_list=bound_list,
        )

        add_assumption_doc(
            type="model assumption",
            name="Region specific stock extrapolation.",
            description="Each region has its own stock extrapolation. "
            "Independent fit of stretch_factor and x_offset, within bounds. ",
        )

        total_in_use_stock = self.stock_handler.stocks

        total_in_use_stock = total_in_use_stock * self.parameters["stock_type_split"]
        return total_in_use_stock
