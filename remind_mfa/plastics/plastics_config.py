from remind_mfa.common.common_config import CommonCfg, VisualizationCfg, BaseVisualizationCfg


class PlasticsVisualizationCfg(VisualizationCfg):
    flows: BaseVisualizationCfg
    """Visualization configuration for flows."""


class PlasticsCfg(CommonCfg):
    transience: bool = False
    """Whether the model is run with input data from other MIC3 models in the TRANSIENCE project."""
    visualization: PlasticsVisualizationCfg
    """Plastics visualization configuration."""
