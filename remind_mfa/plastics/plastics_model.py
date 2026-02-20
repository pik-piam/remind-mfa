import numpy as np
import flodym as fd

from .plastics_mfa_system import PlasticsMFASystemFuture
from .plastics_mfa_system_historic import PlasticsMFASystemHistoric
from .plastics_export import PlasticsDataExporter
from .plastics_visualization import PlasticsVisualizer
from .plastics_definition import get_plastics_definition
from .plastics_mappings import PlasticsDimensionFiles, PlasticsDisplayNames
from remind_mfa.plastics.plastics_definition import scenario_parameters as plastics_scn_prm_def
from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.stock_extrapolation import StockExtrapolation
from remind_mfa.common.data_transformations import Bound, BoundList


class PlasticsModel(CommonModel):

    ConfigCls = PlasticsCfg
    DimensionFilesCls = PlasticsDimensionFiles
    DataExporterCls = PlasticsDataExporter
    VisualizerCls = PlasticsVisualizer
    DisplayNamesCls = PlasticsDisplayNames
    HistoricMFASystemCls = PlasticsMFASystemHistoric
    FutureMFASystemCls = PlasticsMFASystemFuture
    get_definition = staticmethod(get_plastics_definition)
    custom_scn_prm_def = plastics_scn_prm_def

    # TODO: unify, then delete
    end_use_good_letter: str = "g"
    historic_stock_name: str = "in_use_historic"
    stock_projection_saturation_level: int = 6000 #TODO replace this first guess

    def get_long_term_stock(self):
        """
        Stock extrapolation is done per good over all regions;
        upper bound of saturation level is set as 1.2 * the maximum historic stock per capita for each good category;
        offsets for GDP per capita and time are bounded between 0 and maximum historic GDP per capita / year such that the inflexion point cannot be outside the historic range.
        """
        historic_stock = self.historic_mfa.stocks["in_use_historic"]
        historic_pop = self.parameters["population"][{"t": self.dims["h"]}]
        stock_pc = historic_stock.stock / historic_pop
        indep_fit_dim_letters = ("g",)
        sat_bound = Bound(
            var_name="saturation_level",
            lower_bound=fd.FlodymArray(dims=self.dims[indep_fit_dim_letters]),
            upper_bound=np.max(
                stock_pc.values, axis=(stock_pc.dims.index("h"), stock_pc.dims.index("r"))
            )
            * 1.2,
            dims=self.dims[indep_fit_dim_letters],
        )
        lower_bound = fd.FlodymArray(dims=self.dims[indep_fit_dim_letters])
        # Define bounds for Logistic parameters
        # offset_bound_gdp = Bound(
        #     var_name="x1_offset",
        #     lower_bound=lower_bound,
        #     upper_bound=fd.FlodymArray(dims=self.dims[indep_fit_dim_letters],
        #                                values=np.log10(np.max(self.parameters["gdppc"][self.dims["h"].items[-1]].values)) * np.ones(lower_bound.shape)),
        # )
        # offset_bound_time = Bound(
        #     var_name="x2_offset",
        #     lower_bound=lower_bound,
        #     upper_bound=fd.FlodymArray(dims=self.dims[indep_fit_dim_letters],
        #                                values=self.dims["h"].items[-1]*np.ones(lower_bound.shape)),
        # )
        # Define bounds for Gompertz parameters
        offset_bound_gdp = Bound(
            var_name="x1_offset",
            lower_bound=fd.FlodymArray(
                dims=self.dims[indep_fit_dim_letters], values=np.ones(lower_bound.shape) * 0.05
            ),
            upper_bound=fd.FlodymArray(
                dims=self.dims[indep_fit_dim_letters], values=np.ones(lower_bound.shape) * 20
            ),
        )
        offset_bound_time = Bound(
            var_name="x2_offset",
            lower_bound=fd.FlodymArray(
                dims=self.dims[indep_fit_dim_letters], values=np.ones(lower_bound.shape) * 0.05
            ),
            upper_bound=fd.FlodymArray(
                dims=self.dims[indep_fit_dim_letters], values=np.ones(lower_bound.shape) * 20
            ),
        )
        growth_rate_bound_gdp = Bound(
            var_name="x1_growth_rate",
            lower_bound=fd.FlodymArray(
                dims=self.dims[indep_fit_dim_letters], values=np.ones(lower_bound.shape) * 0.3
            ),
            upper_bound=fd.FlodymArray(
                dims=self.dims[indep_fit_dim_letters], values=np.ones(lower_bound.shape) * 3
            ),
        )
        growth_rate_bound_time = Bound(
            var_name="x2_growth_rate",
            lower_bound=fd.FlodymArray(
                dims=self.dims[indep_fit_dim_letters], values=np.ones(lower_bound.shape) * 0.3
            ),
            upper_bound=fd.FlodymArray(
                dims=self.dims[indep_fit_dim_letters], values=np.ones(lower_bound.shape) * 3
            ),
        )
        bound_list = BoundList(
            bound_list=[
                # sat_bound,
                offset_bound_gdp,
                offset_bound_time,
                growth_rate_bound_gdp,
                growth_rate_bound_time,
            ],
            target_dims=self.dims[indep_fit_dim_letters],
        )
        self.stock_handler = StockExtrapolation(
            cfg=self.cfg.model_switches,
            historic_stocks=historic_stock.stock,
            dims=self.dims,
            parameters=self.parameters,
            target_dim_letters=(
                "all" if self.cfg.model_switches.do_stock_extrapolation_by_category else ("t", "r")
            ),
            bound_list=bound_list,
            indep_fit_dim_letters=indep_fit_dim_letters,
        )
        return self.stock_handler.stocks
