import flodym as fd
from typing import Optional
import pandas as pd

from remind_mfa.common.data_extrapolations import Extrapolation
from remind_mfa.common.parameter_extrapolation import ParameterExtrapolation
from remind_mfa.common.helpers import RemindMFABaseModel, ModelNames, RegressOverModes


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
    parameter_extrapolation: Optional[dict[str, str]] = None
    """Mapping of parameter names to extrapolation subclass names for parameter extrapolation from historical values into the future."""

    @property
    def lifetime_model(self) -> type[fd.LifetimeModel]:
        return choose_subclass_by_name(self.lifetime_model_name, fd.LifetimeModel)

    @property
    def stock_extrapolation_class(self) -> type[Extrapolation]:
        """Check if the given extrapolation class is a valid subclass of OneDimensionalExtrapolation and return it."""
        return choose_subclass_by_name(self.stock_extrapolation_class_name, Extrapolation)

    @property
    def parameter_extrapolation_classes(self) -> Optional[dict[str, type[ParameterExtrapolation]]]:
        """Check if the given parameter extrapolation classes are valid subclasses of ParameterExtrapolation and return them."""
        if self.parameter_extrapolation is None:
            return None

        classes = {}
        for param_name, class_name in self.parameter_extrapolation.items():
            classes[param_name] = choose_subclass_by_name(class_name, ParameterExtrapolation)
        return classes


class BaseExportCfg(RemindMFABaseModel):
    do_export: bool = True
    """Whether to export this entity"""
    path: str = None
    """Path to export folder for this entity"""


class ExportCfg(BaseExportCfg):
    csv: BaseExportCfg
    """Configuration of export to CSV files"""
    pickle: BaseExportCfg
    """Configuration of export to pickle files."""
    assumptions: BaseExportCfg
    """Configuration of export of assumptions to a txt file."""
    docs: BaseExportCfg
    """Configuration of export to documentation files."""
    iamc: BaseExportCfg
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

    use_stock: StockVisualizationCfg
    """Visualization configuration for use stock."""
    production: BaseVisualizationCfg
    """Visualization configuration for production."""
    sankey: SankeyVisualizationCfg
    """Visualization configuration for sankey."""
    extrapolation: BaseVisualizationCfg
    """Visualization configuration for extrapolation."""


class InputCfg(RemindMFABaseModel):
    madrat_output_path: str
    """Where to find the madrat output archives to extract input data from."""
    force_extract_tgz: bool
    """Whether to force re-extraction of input data from tgz files. If False, extraction is only performed if pre-extracted data is not up-to date."""
    input_data_path: str
    """Path to the input data directory."""
    scenarios_path: str
    """Path to the scenario definition directory."""
    input_data_version: str
    """Version of the input data to use"""


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
