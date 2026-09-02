import os
from functools import cached_property

import flodym as fd
import pandas as pd
from pydantic import model_validator

from remind_mfa.common.data_extrapolations import Extrapolation
from remind_mfa.common.helpers import ModelNames, RegressOverModes, RemindMFABaseModel


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


class ModelSwitches(RemindMFABaseModel):

    scenario: str
    """Name of the scenario to use."""
    stock_extrapolation_class_name: str
    """Class name of the extrapolation subclass to use for stock extrapolation."""
    lifetime_model_name: str
    """Class name of the lifetime model subclass to use for the in-use stock."""
    do_stock_extrapolation_by_category: bool = False
    """Whether to perform stock extrapolation by good category."""
    regress_over: RegressOverModes
    """Variable to use as a predictor for stock extrapolation."""
    do_stock_extrapolation_with_time_factor: bool = False
    """Whether to include a time factor in stock extrapolation to account for innovation and associated changes in material applications over time."""

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
    path: str = None
    """Path to export folder for this entity"""


class IamcExportCfg(BaseExportCfg):
    t: str = "1950:2100"
    """Inclusive "start:stop" year range to export in IAMC format (e.g. "1950:2100")."""

    @property
    def time_items(self) -> list[int]:
        start, stop = self._parse_range()
        return list(range(start, stop + 1))  # inclusive of stop

    def _parse_range(self) -> tuple[int, int]:
        parts = str(self.t).split(":")
        if len(parts) != 2:
            raise ValueError(f"iamc.t must be a 'start:stop' year range, got {self.t!r}")
        try:
            start, stop = int(parts[0]), int(parts[1])
        except ValueError:
            raise ValueError(f"iamc.t must be a 'start:stop' year range, got {self.t!r}")
        if start > stop:
            raise ValueError(f"iamc.t start must not be after stop, got {self.t!r}")
        return start, stop

    @model_validator(mode="after")
    def validate_time_range(self):
        self._parse_range()
        return self


class ExportCfg(BaseExportCfg):
    csv: BaseExportCfg
    """Configuration of export to CSV files"""
    mrindustry: BaseExportCfg
    """Configuration of export of material flows for use as REMIND inputs."""
    pickle: BaseExportCfg
    """Configuration of export to pickle files."""
    assumptions: BaseExportCfg
    """Configuration of export of assumptions to a txt file."""
    docs: BaseExportCfg
    """Configuration of export to documentation files."""
    iamc: IamcExportCfg
    """Configuration of export of results in IAMC format."""


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
    figures_path: str
    """Path to the figures directory."""
    do_show_figs: bool = True
    """Whether to show figures."""
    do_save_figs: bool = False
    """Whether to save figures."""
    plotting_engine: str = "plotly"
    """Plotting engine to use for visualizations."""
    plotly_renderer: str = "browser"
    """Plotly renderer to use for visualizations."""
    fig_width: int = 1000
    """Logical width (px) of saved figures. Keep close to the final display size: readability
    in a report depends on the font size relative to this width, not on the pixel resolution."""
    fig_height: int = 600
    """Logical height (px) of saved figures."""
    fig_scale: int = 3
    """Resolution multiplier for saved figures (sharpness only; does not affect text readability)."""
    font_size: int = 18
    """Base font size (px) applied to saved figures. Larger fonts relative to fig_width make text
    readable once the image is scaled down to fit a Word/report page."""

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
    sector_splits: BaseVisualizationCfg
    """Visualization configuration for sector splits."""


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


class TransienceCfg(RemindMFABaseModel):
    transience_run: bool = False
    """Whether model run is a run with input data from other MIC3 models in the TRANSIENCE project."""
    baseline_pickle_path: str | None = None
    """Name of the run to use as baseline for transience trade extrapolations."""
    transience_scenario: str = "baseline"
    """Name of the scenario to use. Must be one of 'baseline', 'ME', 'RU'."""
    trade_scenario: str = "default"
    """Name of the trade extrapolation scenario to use. Must be one of 'default', 'fix_supply_alpha0', 'fix_supply_alpha1'."""


class CommonCfg(RemindMFABaseModel):
    model: ModelNames
    """Model to use. Must be one of 'plastics', 'steel', or 'cement'."""
    transience: TransienceCfg
    """Configuration for runs with input data from other MIC3 models in the TRANSIENCE project."""
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
