from remind_mfa.common.common_config import CommonCfg, VisualizationCfg


class PlasticsVisualizationCfg(VisualizationCfg):
    flows: dict = {"do_visualize": False}
    """Visualization configuration for flows."""


class PlasticsCfg(CommonCfg):

    visualization: PlasticsVisualizationCfg
