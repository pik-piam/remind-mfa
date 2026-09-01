import flodym as fd
import numpy as np

from .plastics_mfa_system import PlasticsMFASystemFuture
from .plastics_mfa_system_historic import PlasticsMFASystemHistoric
from .plastics_export import PlasticsDataExporter
from .plastics_visualization import PlasticsVisualizer
from .plastics_definition import get_plastics_definition
from .plastics_mappings import PlasticsDimensionFiles, PlasticsDisplayNames
from remind_mfa.plastics.plastics_definition import scenario_parameters as plastics_scn_prm_def
from remind_mfa.plastics.plastics_config import PlasticsCfg
from remind_mfa.common.common_model import CommonModel
from remind_mfa.common.data_blending import blend


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

    def modify_parameters(self):
        # cast lifetime mean to correct dimensions for use in common model
        self.parameters["lifetime_mean"] = fd.Parameter(
            dims=self.dims["t", "r", "g"],
            values=self.parameters["lifetime_mean"].cast_to(self.dims["t", "r", "g"]).values,
        )
        self.parameters["lifetime_std"] = fd.Parameter(
            dims=self.dims["t", "r", "g"],
            values=self.parameters["lifetime_std"].cast_to(self.dims["t", "r", "g"]).values,
        )
        # cast rates that are globally historically zero to the region dimension to allow for future extrapolation
        # differentiated by region
        self.parameters["chemical_recycling_rate"] = fd.Parameter(
            dims=self.dims["r",],
            values=self.parameters["chemical_recycling_rate"].cast_to(self.dims["r",]).values,
        )
        self.parameters["bio_production_rate"] = fd.Parameter(
            dims=self.dims["r",],
            values=self.parameters["bio_production_rate"].cast_to(self.dims["r",]).values,
        )
        self.parameters["daccu_production_rate"] = fd.Parameter(
            dims=self.dims["r",],
            values=self.parameters["daccu_production_rate"].cast_to(self.dims["r",]).values,
        )
        self.parameters["emission_capture_rate"] = fd.Parameter(
            dims=self.dims["r",],
            values=self.parameters["emission_capture_rate"].cast_to(self.dims["r",]).values,
        )

        # calculate landfill rate from historic eol rates (1 - sum of other eol rates)
        self.parameters["landfill_rate"] = fd.Parameter(
            name="landfill_rate",
            dims=self.dims["h", "r"],
            values=(
                1
                - self.parameters["incineration_rate"]
                - self.parameters["mechanical_recycling_rate"]
                - self.parameters["chemical_recycling_rate"].cast_to(self.dims["h", "r"])
            ).values,
        )

    def transfer_historic_parameters(self):
        # get material split of stock inflow from historic MFA to be extrapolated by ParameterExtrapolation for use in future MFA
        self.parameters["material_shares_use_inflow"] = self.historic_mfa.parameters[
            "material_shares_use_inflow"
        ]
        # get global good split of stock inflow from historic MFA to be used as sector split limit in the stock extrapolation
        self.parameters["sector_split_limit"] = fd.Parameter(
            dims=self.dims["g",],
            values=self.historic_mfa.parameters["global_good_shares_use_inflow"][
                self.dims["h"].items[-1]
            ].values,
        )
