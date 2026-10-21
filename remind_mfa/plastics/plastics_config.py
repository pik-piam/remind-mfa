from remind_mfa.common.common_config import CommonCfg, VisualizationCfg, BaseVisualizationCfg


class PlasticsVisualizationCfg(VisualizationCfg):
    flows: BaseVisualizationCfg
    """Visualization configuration for flows."""
    polymer_splits: BaseVisualizationCfg
    """Visualization configuration for polymer splits in consumption."""
    scenario_params: BaseVisualizationCfg = BaseVisualizationCfg()
    """Visualization configuration for scenario parameters."""


class PlasticsCfg(CommonCfg):
    visualization: PlasticsVisualizationCfg
    """Plastics visualization configuration."""
