from remind_mfa.common.common_config import CommonCfg, VisualizationCfg


class SteelVisualizationCfg(VisualizationCfg):
    scrap_demand_supply: dict = {"do_visualize": False}
    """Visualization configuration for scrap demand and supply."""
    sector_splits: dict = {"do_visualize": False}
    """Visualization configuration for sector splits."""
    trade: dict = {"do_visualize": False}
    """Visualization configuration for trade."""
    consumption: dict = {"do_visualize": False}
    """Visualization configuration for consumption."""
    gdppc: dict = {"do_visualize": False}
    """Visualization configuration for GDP per capita."""


class SteelCfg(CommonCfg):

    visualization: SteelVisualizationCfg
