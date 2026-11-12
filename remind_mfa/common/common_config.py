import os
from dataclasses import dataclass
from functools import cached_property
from typing import Literal

import flodym as fd
import pandas as pd
from pydantic import model_validator

from remind_mfa.common.data_extrapolations import Extrapolation
from remind_mfa.common.helpers import ModelNames, RemindMFABaseModel


def choose_subclass_by_name(name: str, parent: type) -> type:

    def recurse_subclasses(cls):
        return set(cls.__subclasses__()).union(
            [s for c in cls.__subclasses__() for s in recurse_subclasses(c)]
        )

    subclasses = {cls.__name__: cls for cls in recurse_subclasses(parent)}
    if name not in subclasses:
        raise ValueError(
            f"Subclass name for {parent.__name__} must be one of {list(subclasses.keys())}, but {name} was given."
        )
    return subclasses[name]


class InputHorizonError(ValueError):
    """The input data does not cover the configured time horizon."""


@dataclass(frozen=True)
class TimeHorizon:
    """Years of a model run: the historical period, known from input data, and the modelled future."""

    start_historical: int
    """First year of the historical period."""
    end_historical: int
    """Last year of the historical period."""
    end_future: int
    """Last modelled year."""

    def __post_init__(self):
        if not self.start_historical < self.end_historical < self.end_future:
            raise ValueError(
                "The time horizon needs start_historical < end_historical < end_future, but got "
                f"{self.start_historical}, {self.end_historical} and {self.end_future}."
            )

    @property
    def historical_years(self) -> range:
        """Years of the historical time dimension `h`."""
        return range(self.start_historical, self.end_historical + 1)

    @property
    def years(self) -> range:
        """Years of the time dimension `t`: the historical period, followed by the future."""
        return range(self.start_historical, self.end_future + 1)


class ModelSwitches(RemindMFABaseModel):

    scenario: str
    """Name of the scenario to use."""
    stock_extrapolation_class_name: str
    """Class name of the extrapolation subclass to use for stock extrapolation."""
    lifetime_model_name: str
    """Class name of the lifetime model subclass to use for the in-use stock."""
    start_historical: int | None = None
    """First model year, with which the historical period starts. Earlier input data is dropped.
    Defaults to the first year of the input data and can only be later."""
    end_historical: int | None = None
    """Last year of the historical period, which is given by input data. Later years are modelled
    and later historical input data is dropped. Defaults to the last historical year of the input
    data and can only be earlier."""
    end_future: int | None = None
    """Last model year. Defaults to the last year of the input data and can only be earlier."""

    def resolve_time_horizon(self, input_horizon: TimeHorizon | None) -> TimeHorizon:
        """Years of the time dimensions `h` (historical period) and `t` (whole model run).

        Args:
            input_horizon: Time horizon of the input data. If None, the input data does not state
                it, and all three time switches must be set.

        Raises:
            InputHorizonError: If a switch is unset and the input data does not state its value, or
                if a switch extends the time horizon of the input data.
        """
        switches = {
            "start_historical": self.start_historical,
            "end_historical": self.end_historical,
            "end_future": self.end_future,
        }
        if input_horizon is None:
            unset = [name for name, year in switches.items() if year is None]
            if unset:
                raise InputHorizonError(
                    "The input data does not state its time horizon (no *_time_range.cs4r file), so the "
                    f"model switches {', '.join(unset)} must be set. Alternatively, use input data "
                    "built with a recent version of mrmfa."
                )
            return TimeHorizon(**switches)
        exceeding = []
        if self.start_historical is not None and self.start_historical < input_horizon.start_historical:
            exceeding.append(
                f"start_historical = {self.start_historical} is before "
                f"{input_horizon.start_historical}"
            )
        for name in ("end_historical", "end_future"):
            year, input_year = switches[name], getattr(input_horizon, name)
            if year is not None and year > input_year:
                exceeding.append(f"{name} = {year} is after {input_year}")
        if exceeding:
            raise InputHorizonError(
                f"The model switches can only shorten the time horizon of the input data, but "
                f"{' and '.join(exceeding)} in the input data. Change or remove these switches, or use input data "
                "with a longer time horizon."
            )
        return TimeHorizon(
            **{
                name: getattr(input_horizon, name) if year is None else year
                for name, year in switches.items()
            }
        )

    @property
    def lifetime_model(self) -> type[fd.LifetimeModel]:
        return choose_subclass_by_name(self.lifetime_model_name, fd.LifetimeModel)

    @property
    def stock_extrapolation_class(self) -> type[Extrapolation]:
        """Check if the given extrapolation class is a valid subclass of OneDimensionalExtrapolation and return it."""
        return choose_subclass_by_name(self.stock_extrapolation_class_name, Extrapolation)


class BaseExportCfg(RemindMFABaseModel):
    do_export: bool = True
    """Whether to export this entity"""


class DocsExportCfg(BaseExportCfg):
    apply_mappings: bool = True
    """Whether to replace internal names in the generated tables by their display names."""


class IamcExportCfg(BaseExportCfg):
    """Common configuration of exports in IAMC format."""

    start_year: int = 1950
    """First year to export in IAMC format."""
    end_year: int | None = 2100
    """Last year to export in IAMC format."""

    @model_validator(mode="after")
    def validate_years(self):
        if self.end_year is not None and self.start_year > self.end_year:
            raise ValueError(
                f"IAMC export start_year {self.start_year} is after end_year {self.end_year}."
            )
        return self

    def years(self, end_future: int) -> range:
        """Years to export, from `start_year` to `end_year` inclusive.

        Args:
            end_future: Last model year, used if `end_year` is not set.

        Raises:
            ValueError: If the years to export end after `end_future` or start after it.
        """
        end_year = end_future if self.end_year is None else self.end_year
        if end_year > end_future:
            raise ValueError(
                f"IAMC export end_year {end_year} is after the last model year {end_future} "
                "(model_switches.end_future). Lower it or leave it unset to export until the last "
                "model year."
            )
        if self.start_year > end_year:
            raise ValueError(
                f"IAMC export start_year {self.start_year} is after the last model year {end_future}."
            )
        return range(self.start_year, end_year + 1)


class IamcReportingExportCfg(IamcExportCfg):
    """Configuration of the export of selected variables in IAMC nomenclature."""


class IamcRawExportCfg(IamcExportCfg):
    """Configuration of the export of all flows, stocks, trades and selected parameters in IAMC format."""

    detail: list[Literal["aggregated", "complete"]] = ["aggregated", "complete"]
    """Detail levels to write, one file each: "aggregated" (resolved by time and region only) or "complete" (with all splits and parameters)."""


class ExportCfg(BaseExportCfg):
    path: str = None
    """Path to export base folder where a subdirectory is created for each run"""
    bundle_export: bool = False
    """Whether to group all model outputs from one run into a shared <prefix>_series folder."""
    prefix: str | None = None
    """Optional fixed prefix for export file and folder names. Defaults to a timestamp."""
    csv: BaseExportCfg
    """Configuration of export to CSV files"""
    mrindustry: BaseExportCfg
    """Configuration of export of material flows for use as REMIND inputs."""
    pickle: BaseExportCfg
    """Configuration of export to pickle files."""
    assumptions: BaseExportCfg
    """Configuration of export of assumptions to a txt file."""
    docs: DocsExportCfg
    """Configuration of export to documentation files."""
    iamc_reporting: IamcReportingExportCfg
    """Configuration of export of selected variables in IAMC nomenclature."""
    iamc_raw: IamcRawExportCfg
    """Configuration of export of all flows, stocks, trades and selected parameters in IAMC format."""


class BaseVisualizationCfg(RemindMFABaseModel):
    do_visualize: bool = True
    """Whether to create visualizations for this entity"""


class SankeyVisualizationCfg(BaseVisualizationCfg):
    plotter_args: dict = {}
    """dictionary of arguments to pass to the Sankey plotter"""


class StockVisualizationCfg(BaseVisualizationCfg):
    per_capita: bool = False
    """Whether to visualize stock per capita."""
    over_gdp: bool = False
    """Whether to visualize stock over GDPpC. Alternative is over time"""
    accumulate_gdp: bool = False
    """Whether to accumulate GDPpC over time (i.e. do not allow decreasing GDPpC) for visualization purposes."""


class ConsumptionVisualizationCfg(BaseVisualizationCfg):
    per_capita: bool = False
    """Whether to visualize consumption per capita."""


class GDPVisualizationCfg(BaseVisualizationCfg):
    per_capita: bool = False
    """Whether to visualize gdp per capita."""


class VisualizationCfg(BaseVisualizationCfg):
    do_show_figs: bool = True
    """Whether to show figures."""
    do_save_figs: bool = False
    """Whether to save figures as static png files."""
    do_save_figs_html: bool = False
    """Whether to save figures as standalone HTML files."""
    plotting_engine: str = "plotly"
    """Plotting engine to use for visualizations."""
    plotly_renderer: str = "browser"
    """Plotly renderer to use for visualizations."""

    use_stock: StockVisualizationCfg
    """Visualization configuration for use stock."""
    gdp: GDPVisualizationCfg
    """Visualization configuration for GDP per capita."""
    production: BaseVisualizationCfg
    """Visualization configuration for production."""
    trade: BaseVisualizationCfg
    """Visualization configuration for trade."""
    consumption: ConsumptionVisualizationCfg
    """Visualization configuration for consumption."""
    sankey: SankeyVisualizationCfg
    """Visualization configuration for sankey."""
    extrapolation: BaseVisualizationCfg
    """Visualization configuration for extrapolation."""
    end_use_split: BaseVisualizationCfg
    """Visualization configuration for end-use splits."""

    @model_validator(mode="after")
    def validate_html_export(self):
        if self.do_save_figs_html and self.plotting_engine != "plotly":
            raise ValueError("do_save_figs_html requires plotting_engine = 'plotly'.")
        return self


class InputCfg(RemindMFABaseModel):
    madrat_output_path: str | None = None
    """Where to find the madrat output archives to extract input data from. If None, MADRAT_OUTPUT_FOLDER is used."""
    force_extract_tgz: bool
    """Whether to force re-extraction of input data from tgz files. If False, extraction is only performed if pre-extracted data is not up-to date."""
    input_data_path: str
    """Path to the input data directory."""
    scenarios_path: str
    """Path to the scenario definition directory."""
    input_data_revision: str
    """Target input-data revision, corresponding to rev<revision> in tgz names."""
    region_mapping: str
    """Target region mapping, corresponding to <region> in tgz names."""

    @cached_property
    def resolved_madrat_output_path(self) -> str:
        path = self.madrat_output_path or os.environ.get("MADRAT_OUTPUTFOLDER")
        if not path:
            raise ValueError(
                "No madrat output path configured. Set input.madrat_output_path or "
                "environment variable MADRAT_OUTPUTFOLDER."
            )
        return path

    @staticmethod
    def _normalize_revision(revision: str) -> str:
        revision = revision.strip()
        if revision.startswith("rev"):
            return revision[3:]
        return revision

    @model_validator(mode="after")
    def validate_input_data_selector(self):
        self.input_data_revision = self._normalize_revision(self.input_data_revision)
        return self


class CommonCfg(RemindMFABaseModel):
    model: ModelNames
    """Model to use. Must be one of 'plastics', 'steel', or 'cement'."""
    input: InputCfg
    """Input data configuration."""
    model_switches: ModelSwitches
    """Model customization parameters."""
    visualization: VisualizationCfg
    """Visualization configuration."""
    export: ExportCfg
    """Data export configuration."""

    def to_df(self) -> pd.DataFrame:
        """Exports configuration parameters to pandas DataFrames."""

        def flatten_dict(d, parent_key="", sep="."):
            items = []
            for k, v in d.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten_dict(v, new_key, sep=sep).items())
                else:
                    items.append((new_key, v))
            return dict(items)

        flat = flatten_dict(self.model_dump())
        df = pd.DataFrame(flat.items(), columns=["Parameter", "Value"])

        return df

    @classmethod
    def to_schema_df(cls, only_base: bool = True) -> pd.DataFrame:
        """Exports configuration schema (fields, types, descriptions) to pandas DataFrame.

        Args:
            only_base: If True, only return fields from GeneralCfg base class (excluding model-specific fields)
        """

        def get_field_schema(model_cls, parent_key="", sep="."):
            schema = []
            for field_name, field_info in model_cls.model_fields.items():
                new_key = f"{parent_key}{sep}{field_name}" if parent_key else field_name

                # Get type annotation
                annotation = field_info.annotation
                if hasattr(annotation, "__name__"):
                    type_str = annotation.__name__
                else:
                    type_str = str(annotation).replace("typing.", "")

                # Get description from docstring
                description = field_info.description or ""

                # Get default value if exists
                if field_info.default is not None:
                    default = field_info.default
                elif field_info.default_factory is not None:
                    default = str(field_info.default_factory())
                else:
                    default = ""

                schema.append(
                    {
                        "Parameter": new_key,
                        "Type": type_str,
                        "Default": default,
                        "Description": description,
                    }
                )

                # Recurse for nested Pydantic models
                if hasattr(annotation, "model_fields"):
                    schema.extend(get_field_schema(annotation, new_key, sep))

            return schema

        # Use GeneralCfg if only_base is True, otherwise use the calling class
        target_cls = CommonCfg if only_base else cls
        schema = get_field_schema(target_cls)
        df = pd.DataFrame(schema)
        return df
