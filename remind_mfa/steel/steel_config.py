from remind_mfa.common.common_config import CommonCfg, VisualizationCfg, BaseVisualizationCfg


class SteelVisualizationCfg(VisualizationCfg):
    scrap_demand_supply: BaseVisualizationCfg
    """Visualization configuration for scrap demand and supply."""


class SteelCfg(CommonCfg):

    visualization: SteelVisualizationCfg
    """Steel visualization configuration."""
