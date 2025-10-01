from remind_mfa.common.base_model import RemindMFABaseModel
import flodym as fd
from typing import Optional

from .data_extrapolations import Extrapolation
from .parameter_extension import ParameterExtension


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


class ModelSwitches(RemindMFABaseModel):

    stock_extrapolation_class_name: str
    lifetime_model_name: str
    do_stock_extrapolation_by_category: bool = False
    mode: Optional[str] = None
    parameter_extension: Optional[dict[str, str]] = None

    @property
    def lifetime_model(self) -> type[fd.LifetimeModel]:
        return choose_subclass_by_name(self.lifetime_model_name, fd.LifetimeModel)

    @property
    def stock_extrapolation_class(self) -> type[Extrapolation]:
        """Check if the given extrapolation class is a valid subclass of OneDimensionalExtrapolation and return it."""
        return choose_subclass_by_name(self.stock_extrapolation_class_name, Extrapolation)

    @property
    def parameter_extension_classes(self) -> Optional[dict[str, type[ParameterExtension]]]:
        """Check if the given parameter extension classes are valid subclasses of ParameterExtension and return them."""
        if self.parameter_extension is None:
            return None

        classes = {}
        for param_name, class_name in self.parameter_extension.items():
            classes[param_name] = choose_subclass_by_name(class_name, ParameterExtension)
        return classes


class ExportCfg(RemindMFABaseModel):
    csv: bool = True
    pickle: bool = True
    assumptions: bool = True
    future_input: bool = False


class VisualizationCfg(RemindMFABaseModel):

    use_stock: dict = {"do_visualize": False}
    production: dict = {"do_visualize": False}
    sankey: dict = {"do_visualize": False}
    extrapolation: dict = {"do_visualize": False}
    do_show_figs: bool = True
    do_save_figs: bool = False
    plotting_engine: str = "plotly"
    plotly_renderer: str = "browser"


class CementVisualizationCfg(VisualizationCfg):

    clinker_production: dict = {}
    cement_production: dict = {}
    concrete_production: dict = {}
    eol_stock: dict = {}


class SteelVisualizationCfg(VisualizationCfg):

    scrap_demand_supply: dict = {"do_visualize": False}
    sector_splits: dict = {"do_visualize": False}
    trade: dict = {"do_visualize": False}
    consumption: dict = {"do_visualize": False}
    gdppc: dict = {"do_visualize": False}


class PlasticsVisualizationCfg(VisualizationCfg):

    pass


class GeneralCfg(RemindMFABaseModel):

    model_class: str
    madrat_output_path: str
    input_data_path: str
    input_data_version: str
    model_switches: ModelSwitches
    visualization: VisualizationCfg
    output_path: str
    do_export: ExportCfg

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


class PlasticsCfg(GeneralCfg):

    visualization: PlasticsVisualizationCfg


class CementCfg(GeneralCfg):

    visualization: CementVisualizationCfg


class SteelCfg(GeneralCfg):

    visualization: SteelVisualizationCfg
