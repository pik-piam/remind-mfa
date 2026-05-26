import logging
import numpy as np
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

        # calculate landfill rate from historic eol rates (1 - sum of other eol rates)
        self.parameters["landfill_rate"] = fd.Parameter(
            name="landfill_rate",
            dims=self.dims["h", "r"],
            values=(
                1
                - self.parameters["incineration_rate"]
                - self.parameters["mechanical_recycling_rate"]
                - self.parameters["chemical_recycling_rate"]
            ).values,
        )

        # Conversion Mt -> t
        # TODO: move to mrmfa
        self.parameters["primary_his_imports"][...] *= 1e6
        self.parameters["primary_his_exports"][...] *= 1e6
        self.parameters["final_his_imports"][...] *= 1e6
        self.parameters["final_his_exports"][...] *= 1e6
        self.parameters["waste_his_imports"][...] *= 1e6
        self.parameters["waste_his_exports"][...] *= 1e6
        self.parameters["consumption"][...] *= 1e6

    def get_sector_split_limit(self):
        """Sector splits differ between regions, which may be due to different consumption preference patterns which we would like to keep, but
        also due to different economic conditions. For low-gdp regions, we cannot assume that the current split will be maintained in the future.
        Therefore, we use the historic split for highest gdp region, but blend to the global split if historic gdp is low in regions
        """

        # get regional good split of stock inflow from historic MFA
        self.parameters["historic_sector_split"] = fd.Parameter(
            dims=self.dims["r", "g"],
            values=self.historic_mfa.parameters["good_shares_use_inflow"][
                self.dims["h"].items[-1]
            ].values,
        )
        # get historic gdp per capita for blending
        hist_gdp = self.parameters["gdppc"][self.dims["h"].items[-1]]

        alpha = blend(
            target_dims=self.dims["r",],
            y_lower=0,
            y_upper=1,
            x=hist_gdp,
            x_lower=np.min(hist_gdp.values),
            x_upper=np.max(hist_gdp.values),
            type="quintic",
        )
        sector_split_limit = (
            self.parameters["sector_split"].cast_to(self.dims["r", "g"]) ** (1 - alpha)
            * self.parameters["historic_sector_split"] ** alpha
        ).get_shares_over("g")
        self.parameters["sector_split_limit"] = fd.Parameter(
            dims=self.dims["r", "g"],
            values=sector_split_limit.values,
        )

    def transfer_historic_parameters(self):
        # get material split of stock inflow from historic MFA to be extrapolated by ParameterExtrapolation for use in future MFA
        self.parameters["material_shares_use_inflow"] = self.historic_mfa.parameters[
            "material_shares_use_inflow"
        ]
        self.get_sector_split_limit()

    def compute_transience_parameters(self):
        logging.warning(
                f"TRANSIENCE mode is on. Collection rate, mechanical recycling rate and mechanical recycling yield for EU27+3 region are computed from EU-MFA. "
            )
        self.parameters["collection_rate_EU-MFA"] = fd.Parameter(
            dims=self.dims["u", "n", "f"],
            values=(self.parameters["collected_eol_EU-MFA"]/self.parameters["stock_outflow_EU-MFA"])[{"r": "EU27+3"}].values,
        )
        self.parameters["mechanical_recycling_rate_EU-MFA"] = fd.Parameter(
            dims=self.dims["u", "n"],
            values=(self.parameters["sorted_eol_EU-MFA"].sum_to(("u", "r", "n"))/self.parameters["collected_eol_EU-MFA"].sum_to(("u", "r", "n")))[{"r": "EU27+3"}].values,
        )
        self.parameters["mechanical_recycling_yield_EU-MFA"] = fd.Parameter(
            dims=self.dims["u", "n"],
            values=(self.parameters["recycled_eol_EU-MFA"].sum_to(("u", "r", "n"))/self.parameters["sorted_eol_EU-MFA"].sum_to(("u", "r", "n")))[{"r": "EU27+3"}].values,
        )
        # adjust dimensions of REMIND-MFA rates and replace EU region with EU-MFA rates
        self.parameters["collection_rate"] = fd.Parameter(
            name="collection_rate",
            dims=self.dims["t", "r", "m", "g"],
            values=self.parameters["collection_rate"].cast_to(self.dims["t", "r", "m", "g"]).values,
        )
        eu_mfa_collection_rate = self.parameters["collection_rate_EU-MFA"].values
        nan_mask = ~np.isfinite(eu_mfa_collection_rate)
        if nan_mask.any():
            nan_indices = np.argwhere(nan_mask)
            u_items, n_items, f_items = self.dims["u"].items, self.dims["n"].items, self.dims["f"].items
            nan_combos = [(u_items[i[0]], n_items[i[1]], f_items[i[2]]) for i in nan_indices[:20]]
            logging.warning(
                f"NaN/Inf values in collection_rate_EU-MFA for {nan_mask.sum()} combinations "
                f"(EU-MFA_Time, EU-MFA_Material, EU-MFA_Good) — keeping existing REMIND-MFA values. "
                f"First occurrences: {nan_combos}"
            )
            existing = self.parameters["collection_rate"][{"r": "EU27+3", "m": self.dims["n"], "g": self.dims["f"], "t": self.dims["u"]}].values
            eu_mfa_collection_rate = np.where(nan_mask, existing, eu_mfa_collection_rate)
        self.parameters["collection_rate"][{"r": "EU27+3", "m": self.dims["n"], "g": self.dims["f"], "t": self.dims["u"]}] = fd.Parameter(
            dims=self.dims["u", "n", "f"], values=eu_mfa_collection_rate
        )
        self.parameters["mechanical_recycling_rate"] = fd.Parameter(
            name="mechanical_recycling_rate",
            dims=self.dims["t", "r", "m"],
            values=self.parameters["mechanical_recycling_rate"].cast_to(self.dims["t", "r", "m"]).values,
        )
        eu_mfa_mech_rate = self.parameters["mechanical_recycling_rate_EU-MFA"].values
        nan_mask = ~np.isfinite(eu_mfa_mech_rate)
        if nan_mask.any():
            nan_indices = np.argwhere(nan_mask)
            u_items, n_items = self.dims["u"].items, self.dims["n"].items
            nan_combos = [(u_items[i[0]], n_items[i[1]]) for i in nan_indices[:20]]
            logging.warning(
                f"NaN/Inf values in mechanical_recycling_rate_EU-MFA for {nan_mask.sum()} combinations "
                f"(EU-MFA_Time, EU-MFA_Material) — keeping existing REMIND-MFA values. "
                f"First occurrences: {nan_combos}"
            )
            existing = self.parameters["mechanical_recycling_rate"][{"r": "EU27+3", "m": self.dims["n"], "t": self.dims["u"]}].values
            eu_mfa_mech_rate = np.where(nan_mask, existing, eu_mfa_mech_rate)
        self.parameters["mechanical_recycling_rate"][{"r": "EU27+3", "m": self.dims["n"], "t": self.dims["u"]}] = fd.Parameter(
            dims=self.dims["u", "n"], values=eu_mfa_mech_rate
        )
        self.parameters["mechanical_recycling_yield"] = fd.Parameter(
            name="mechanical_recycling_yield",
            dims=self.dims["t", "r", "m"],
            values=self.parameters["mechanical_recycling_yield"].cast_to(self.dims["t", "r", "m"]).values,
        )
        eu_mfa_mech_yield = self.parameters["mechanical_recycling_yield_EU-MFA"].values
        nan_mask = ~np.isfinite(eu_mfa_mech_yield)
        if nan_mask.any():
            nan_indices = np.argwhere(nan_mask)
            nan_combos = [(u_items[i[0]], n_items[i[1]]) for i in nan_indices[:20]]
            logging.warning(
                f"NaN/Inf values in mechanical_recycling_yield_EU-MFA for {nan_mask.sum()} combinations "
                f"(EU-MFA_Time, EU-MFA_Material) — keeping existing REMIND-MFA values. "
                f"First occurrences: {nan_combos}"
            )
            existing = self.parameters["mechanical_recycling_yield"][{"r": "EU27+3", "m": self.dims["n"], "t": self.dims["u"]}].values
            eu_mfa_mech_yield = np.where(nan_mask, existing, eu_mfa_mech_yield)
        self.parameters["mechanical_recycling_yield"][{"r": "EU27+3", "m": self.dims["n"], "t": self.dims["u"]}] = fd.Parameter(
            dims=self.dims["u", "n"], values=eu_mfa_mech_yield
        )
