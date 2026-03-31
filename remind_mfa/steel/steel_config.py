from remind_mfa.common.common_config import CommonCfg, VisualizationCfg, BaseVisualizationCfg


class GDPVisualizationCfg(BaseVisualizationCfg):
    per_capita: bool = False
    """Whether to visualize stock per capita."""


class SteelVisualizationCfg(VisualizationCfg):
    scrap_demand_supply: BaseVisualizationCfg
    """Visualization configuration for scrap demand and supply."""
    sector_splits: BaseVisualizationCfg
    """Visualization configuration for sector splits."""
    gdppc: GDPVisualizationCfg
    """Visualization configuration for GDP per capita."""


class SteelCfg(CommonCfg):

    visualization: SteelVisualizationCfg
    """Steel visualization configuration."""
