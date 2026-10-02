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
    historic_stock_name: str = "in_use_historic"

    do_stock_extrapolation_with_time_factor: bool = True
    time_factor_prms = {"horizontal_shift_base": 1980, "growth_rate": 0.01}
    # these are the parameters for a Gompertz function that reaches 20% saturation in 1950 and 80% in 2020

    def modify_parameters(self):
        # cast lifetime mean to correct dimensions for use in common model
        self.parameters["lifetime_mean"] = fd.Parameter(
            dims=self.dims["t", "r", "u"],
            values=self.parameters["lifetime_mean"].cast_to(self.dims["t", "r", "u"]).values,
        )
        self.parameters["lifetime_std"] = fd.Parameter(
            dims=self.dims["t", "r", "u"],
            values=self.parameters["lifetime_std"].cast_to(self.dims["t", "r", "u"]).values,
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

        # the future MFA does not carry the Type dimension 'p' (it is redundant with the material
        # dimension 'm'), and the waste trade is only used there, so collapse 'p' away
        for name in ("waste_his_imports", "waste_his_exports"):
            self.parameters[name] = fd.Parameter(
                name=name,
                dims=self.dims["h", "r", "m"],
                values=self.parameters[name].sum_values_over("p"),
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

        # 0/1 membership of each material in its polymer type, derived from the (p, m) sparsity of
        # the sector split. The future MFA drops the Type dimension 'p', since each material
        # belongs to exactly one type; multiply an m-resolved array by this mapping to re-expand
        # it to 'p' where the Type resolution is needed (e.g. the IAMC export by type).
        membership = self.parameters["sector_polymer_split"].sum_over(("h", "r", "u"))  # (p, m)
        mapping = fd.Parameter(
            name="material_type_mapping",
            dims=self.dims["p", "m"],
            values=(membership.values > 0).astype(float),
        )
        unmapped = mapping.sum_over("p").items_where(lambda x: x != 1)
        if unmapped.size:
            raise ValueError(
                "Each material must belong to exactly one Type in 'sector_polymer_split', but "
                f"{[row[0] for row in unmapped]} do(es) not. Check the Type/Material combinations "
                "in the input data and the plastics Type and Material dimension files."
            )
        self.parameters["material_type_mapping"] = mapping

    def transfer_historic_parameters(self):
        # get material split of stock inflow from historic MFA to be extrapolated by ParameterExtrapolation for use in future MFA
        self.parameters["material_shares_use_inflow"] = self.historic_mfa.parameters[
            "material_shares_use_inflow"
        ]
        # get global good split of stock inflow from historic MFA to be used as sector split limit in the stock extrapolation
        self.parameters["sector_split_limit"] = fd.Parameter(
            dims=self.dims["u",],
            values=self.historic_mfa.parameters["global_good_shares_use_inflow"][
                self.dims["h"].items[-1]
            ].values,
        )
