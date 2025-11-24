from remind_mfa.common.base_model import RemindMFABaseModel
import flodym as fd
from typing import Optional
from pydantic import Field
import pandas as pd

from .data_extrapolations import Extrapolation


IMPLEMENTED_MODELS = [
    "plastics",
    "steel",
    "cement",
]


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


class ModelCustomization(RemindMFABaseModel):

    stock_extrapolation_class_name: str = Field(
        description="Name of the extrapolation class to use for stock extrapolation."
    )
    lifetime_model_name: str = Field(description="Name of the lifetime model to use.")
    do_stock_extrapolation_by_category: bool = Field(
        default=False, description="Whether to perform stock extrapolation by good category."
    )
    regress_over: str = Field(
        default="gdppc", description="Variable to use as a predictor for stock extrapolation."
    )
    mode: Optional[str] = Field(
        default=None, description="Mode of the MFA model, e.g. 'stock_driven' or 'inflow_driven'."
    )

    @property
    def lifetime_model(self) -> fd.LifetimeModel:
        return choose_subclass_by_name(self.lifetime_model_name, fd.LifetimeModel)

    @property
    def stock_extrapolation_class(self) -> Extrapolation:
        """Check if the given extrapolation class is a valid subclass of OneDimensionalExtrapolation and return it."""
        return choose_subclass_by_name(self.stock_extrapolation_class_name, Extrapolation)


class ExportCfg(RemindMFABaseModel):
    csv: bool = Field(default=True, description="Whether to export results as CSV files.")
    pickle: bool = Field(default=True, description="Whether to export results as pickle files.")
    assumptions: bool = Field(
        default=True, description="Whether to export assumptions as a txt file."
    )
    docs: bool = Field(default=False, description="Whether to create documentation files.")
    future_input: bool = Field(
        default=False,
        description="Whether to export results as future input data used in the model.",
    )
    iamc: bool = Field(default=False, description="Whether to export results in IAMC format.")


class VisualizationCfg(RemindMFABaseModel):

    do_visualize: bool = Field(default=True, description="Whether to create visualizations.")
    use_stock: dict = Field(
        default={"do_visualize": False}, description="Visualization configuration for use stock."
    )
    production: dict = Field(
        default={"do_visualize": False}, description="Visualization configuration for production."
    )
    sankey: dict = Field(
        default={"do_visualize": False}, description="Visualization configuration for sankey."
    )
    extrapolation: dict = Field(
        default={"do_visualize": False},
        description="Visualization configuration for extrapolation.",
    )
    do_show_figs: bool = Field(default=True, description="Whether to show figures.")
    do_save_figs: bool = Field(default=False, description="Whether to save figures.")
    plotting_engine: str = Field(
        default="plotly", description="Plotting engine to use for visualizations."
    )
    plotly_renderer: str = Field(
        default="browser", description="Plotly renderer to use for visualizations."
    )


class CementVisualizationCfg(VisualizationCfg):

    clinker_production: dict = Field(
        default={}, description="Visualization configuration for clinker production."
    )
    cement_production: dict = Field(
        default={}, description="Visualization configuration for cement production."
    )
    concrete_production: dict = Field(
        default={}, description="Visualization configuration for concrete production."
    )
    eol_stock: dict = Field(
        default={}, description="Visualization configuration for end-of-life stock."
    )


class SteelVisualizationCfg(VisualizationCfg):

    scrap_demand_supply: dict = Field(
        default={"do_visualize": False},
        description="Visualization configuration for scrap demand and supply.",
    )
    sector_splits: dict = Field(
        default={"do_visualize": False},
        description="Visualization configuration for sector splits.",
    )
    trade: dict = Field(
        default={"do_visualize": False}, description="Visualization configuration for trade."
    )
    consumption: dict = Field(
        default={"do_visualize": False}, description="Visualization configuration for consumption."
    )
    gdppc: dict = Field(
        default={"do_visualize": False},
        description="Visualization configuration for GDP per capita.",
    )


class PlasticsVisualizationCfg(VisualizationCfg):

    flows: dict = Field(
        default={"do_visualize": False}, description="Visualization configuration for flows."
    )


class GeneralCfg(RemindMFABaseModel):

    model_class: str = Field(
        description="Model class to use. Must be one of 'plastics', 'steel', or 'cement'."
    )
    input_data_path: str = Field(description="Path to the input data directory.")
    customization: ModelCustomization = Field(description="Model customization parameters.")
    visualization: VisualizationCfg = Field(description="Visualization configuration.")
    output_path: str = Field(description="Path to the output directory.")
    docs_path: str = Field(description="Path to the documentation directory.")
    do_export: ExportCfg = Field(description="Export configuration.")

    @classmethod
    def from_model_class(cls, **kwargs) -> "GeneralCfg":
        if "model_class" not in kwargs:
            raise ValueError("model_class must be provided.")
        model_class = kwargs["model_class"]
        subclasses = {
            "plastics": PlasticsCfg,
            "steel": SteelCfg,
            "cement": CementCfg,
        }
        if model_class not in subclasses:
            raise ValueError(f"Model class {model_class} not supported.")
        subcls = subclasses[model_class]
        return subcls(**kwargs)

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
        target_cls = GeneralCfg if only_base else cls
        schema = get_field_schema(target_cls)
        df = pd.DataFrame(schema)
        return df


class PlasticsCfg(GeneralCfg):

    visualization: PlasticsVisualizationCfg


class CementCfg(GeneralCfg):

    visualization: CementVisualizationCfg


class SteelCfg(GeneralCfg):

    visualization: SteelVisualizationCfg
