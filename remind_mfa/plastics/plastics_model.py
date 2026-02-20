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

    def modify_parameters(self):
        # copy/rename for use in common model
        self.parameters["sector_split_limit"] = self.parameters["sector_split"]
        # cast lifetime mean to correct dimensions for use in common model
        self.parameters["lifetime_mean"] = fd.Parameter(
            dims=self.dims["t", "g"],
            values=self.parameters["lifetime_mean"].cast_to(self.dims["t", "g"]).values,
        )
