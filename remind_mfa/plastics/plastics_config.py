from remind_mfa.common.common_config import CommonCfg, VisualizationCfg, BaseVisualizationCfg


class PlasticsVisualizationCfg(VisualizationCfg):
    flows: BaseVisualizationCfg
    """Visualization configuration for flows."""


class PlasticsCfg(CommonCfg):

    visualization: PlasticsVisualizationCfg
    """Plastics visualization configuration."""
