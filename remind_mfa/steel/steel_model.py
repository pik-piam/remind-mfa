import numpy as np
import flodym as fd
import logging

from remind_mfa.common.data_blending import blend
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

    # TODO: unify, then delete
    end_use_good_letter: str = "g"
    historic_stock_name: str = "historic_in_use"

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
            dims=self.dims["t", "r", "g"],
            values=(self.parameters["lifetime_factor"] * self.parameters["lifetime_mean"])
            .cast_to(self.dims["t", "r", "g"])
            .values,
        )
        self.parameters["lifetime_std"] = fd.Parameter(
            dims=self.dims["t", "r", "g"],
            values=(self.parameters["lifetime_factor"] * self.parameters["lifetime_std"])
            .cast_to(self.dims["t", "r", "g"])
            .values
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
        self.parameters["sector_split_high"][...] = self.parameters[
            "sector_split_high"
        ].get_shares_over("g")

        self.calc_sector_split()
        self.parameters["aggregate_fabrication_yield"] = fd.Parameter(dims=self.dims["t", "r"])
        self.parameters["aggregate_fabrication_yield"][...] = (
            self.parameters["fabrication_yield"] * self.parameters["sector_split"]
        ).sum_over("g")

    def calc_sector_split(self) -> fd.FlodymArray:
        """Blend over GDP per capita between typical sector splits for low and high GDP per capita regions."""
        target_dims = self.dims["t", "r", "g"]
        self.parameters["sector_split"] = fd.Parameter(dims=target_dims, name="sector_split")
        sector_split_1 = fd.Parameter(dims=target_dims)
        sector_split_2 = fd.Parameter(dims=target_dims)
        log_gdppc = self.parameters["gdppc"].apply(np.log)
        log_gdppc_low = self.parameters["secsplit_gdppc_low"].apply(np.log)
        log_gdppc_high = self.parameters["secsplit_gdppc_high"].apply(np.log)
        add_assumption_doc(
            type="expert guess",
            name="medium sector split",
            description=(
                "Demand sector split for medium GDP per capita, to account for higher construction "
                "share in medium GDP. Roughly based on given source, but adapted."
            ),
            source="https://steel.gov.in/sites/default/files/2025-03/GSI%20Report.pdf",
        )
        log_gddpc_medium = (log_gdppc_low + log_gdppc_high) / 2

        sector_split_1[...] = blend(
            target_dims=target_dims,
            y_lower=self.parameters["sector_split_low"],
            y_upper=self.parameters["sector_split_medium"],
            x=log_gdppc,
            x_lower=log_gdppc_low,
            x_upper=log_gddpc_medium,
            type="poly_mix",
        )

        sector_split_2[...] = blend(
            target_dims=target_dims,
            y_lower=self.parameters["sector_split_medium"],
            y_upper=self.parameters["sector_split_high"],
            x=log_gdppc,
            x_lower=log_gddpc_medium,
            x_upper=log_gdppc_high,
            type="poly_mix",
        )
        # copy/rename for use in common model
        self.parameters["sector_split_limit"] = self.parameters["sector_split_high"]

        mask = log_gdppc.cast_values_to(target_dims) < log_gddpc_medium.cast_values_to(target_dims)
        self.parameters["sector_split"].values = np.where(
            mask, sector_split_1.values, sector_split_2.values
        )
        return
    
    def compute_transience_parameters(self):
        logging.warning(
                f"TRANSIENCE mode is on. Recovery rate for EUR region is computed from EU-MFA. "
            )
        self.parameters["stock_outflow_EU-MFA"] = fd.Parameter(
            dims=self.dims["u", "f"],
            values=(self.parameters["collected_eol_EU-MFA"]+self.parameters["lost_eol_EU-MFA"])[{"r": "EUR"}].values,
        )
        self.parameters["collection_rate_EU-MFA"] = fd.Parameter(
            dims=self.dims["u", "f"],
            values=(self.parameters["collected_eol_EU-MFA"][{"r": "EUR"}]/self.parameters["stock_outflow_EU-MFA"]).values,
        )
        self.parameters["recovery_rate_EU-MFA"] = fd.Parameter(
            dims=self.dims["u", ],
            values=(self.parameters["available_scrap_EU-MFA"][{"r": "EUR"}]/self.parameters["collected_eol_EU-MFA"][{"r": "EUR"}].sum_to("u")).values,
        )
        self.parameters["recovery_rate"] = fd.Parameter(
            dims=self.dims["t", "r", "g"],
            values=self.parameters["recovery_rate"].cast_to(self.dims["t", "r", "g"]).values,
        )
        self.parameters["recovery_rate"][{"r": "EUR", "t": self.dims["u"], "g": self.dims["f"]}] = self.parameters["recovery_rate_EU-MFA"]*self.parameters["collection_rate_EU-MFA"] 
