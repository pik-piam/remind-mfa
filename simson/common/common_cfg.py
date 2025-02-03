from pydantic import BaseModel as PydanticBaseModel
import flodym as fd


class ModelCustomization(PydanticBaseModel):
    curve_strategy: str
    ldf_type: str
    _lifetime_model_class: type = None

    @property
    def lifetime_model(self):
        lifetime_model_classes = {
            "Fixed": fd.FixedLifetime,
            "Normal": fd.NormalLifetime,
            "FoldedNormal": fd.FoldedNormalLifetime,
            "LogNormal": fd.LogNormalLifetime,
            "Weibull": fd.WeibullLifetime,
        }
        return lifetime_model_classes[self.ldf_type]


class VisualizationCfg(PydanticBaseModel):
    stock: dict = {"do_visualize": False}
    production: dict = {"do_visualize": False}
    sankey: dict = {"do_visualize": False}
    scrap_demand_supply: dict = {"do_visualize": False}
    sector_splits: dict = {"do_visualize": False}
    do_show_figs: bool = True
    do_save_figs: bool = False
    plotting_engine: str = "plotly"


class CommonCfg(PydanticBaseModel):
    input_data_path: str
    customization: ModelCustomization
    visualization: VisualizationCfg
    output_path: str
    do_export: dict[str, bool]
