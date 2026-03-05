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

    # TODO: unify, then delete
    end_use_good_letter: str = "s"
    historic_stock_name: str = "historic_cement_in_use"
    stock_projection_saturation_level: int = 24  # TODO replace this first guess

    def modify_parameters(self):
        # copy/rename for use in common model
        self.parameters["sector_split_limit"] = self.parameters["stock_type_split"]
