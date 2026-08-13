from remind_mfa.common.common_config import CommonCfg, VisualizationCfg, BaseVisualizationCfg


class PlasticsVisualizationCfg(VisualizationCfg):
    flows: BaseVisualizationCfg
    """Visualization configuration for flows."""
    material_splits: BaseVisualizationCfg
    """Visualization configuration for material splits in consumption."""


class PlasticsCfg(CommonCfg):
    visualization: PlasticsVisualizationCfg
    """Plastics visualization configuration."""
