import numpy as np
import flodym as fd

from .plastics_mfa_system import PlasticsMFASystemFuture
from .plastics_mfa_system_historic import PlasticsMFASystemHistoric
from .plastics_export import PlasticsDataExporter
from .plastics_visualization import PlasticsVisualizer
from .plastics_definition import get_plastics_definition
from remind_mfa.plastics.plastics_definition import scenario_parameters as plastics_scn_prm_def
from .plastics_data_reader import PlasticsDataReader
from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.assumptions_doc import add_assumption_doc
from remind_mfa.common.stock_extrapolation import StockExtrapolation
from remind_mfa.common.data_transformations import Bound, BoundList


class PlasticsModel(CommonModel):

    ConfigCls = PlasticsCfg
    DataReaderCls = PlasticsDataReader
    DataExporterCls = PlasticsDataExporter
    VisualizerCls = PlasticsVisualizer
    HistoricMFASystemCls = PlasticsMFASystemHistoric
    FutureMFASystemCls = PlasticsMFASystemFuture
    get_definition = staticmethod(get_plastics_definition)
    custom_scn_prm_def = plastics_scn_prm_def

    def get_long_term_stock(self):
        """
        Stock extrapolation is first done per good over all regions;
        upper bound of saturation level is set as the maximum historic stock per capita;
        stock extrapolation is then repeated per region and good, using the maximum of the previously fitted global saturation level
        and the maximum historic stock per capita in the respective region as upper bound.
        """
        historic_stock = self.historic_mfa.stocks["in_use_historic"]
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
            cfg=self.cfg.model_switches,
            historic_stocks=historic_stock.stock,
            dims=self.dims,
            parameters=self.parameters,
            weight=weight,
            target_dim_letters=(
                "all" if self.cfg.model_switches.do_stock_extrapolation_by_category else ("t", "r")
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
            cfg=self.cfg.model_switches,
            historic_stocks=historic_stock.stock,
            dims=self.dims,
            parameters=self.parameters,
            weight=weight,
            target_dim_letters=(
                "all" if self.cfg.model_switches.do_stock_extrapolation_by_category else ("t", "r")
            ),
            bound_list=bound_list,
            indep_fit_dim_letters=indep_fit_dim_letters,
        )
        return self.stock_handler.stocks
