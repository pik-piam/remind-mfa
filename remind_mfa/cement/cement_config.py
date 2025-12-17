from enum import Enum
from remind_mfa.common.common_config import (
    CommonCfg,
    ModelSwitches,
    VisualizationCfg,
    BaseVisualizationCfg,
    StockVisualizationCfg,
)


class CementModes(str, Enum):
    BASE = "base"
    CARBON_FLOW = "carbon_flow"


class CementModelSwitches(ModelSwitches):
    mode: CementModes

    @property
    def carbon_flow(self) -> bool:
        return self.mode == CementModes.CARBON_FLOW


class CementVisualizationCfg(VisualizationCfg):

    consumption: BaseVisualizationCfg
    """Visualization configuration for consumption."""
    prod_clinker: BaseVisualizationCfg
    """Visualization configuration for clinker production."""
    prod_cement: BaseVisualizationCfg
    """Visualization configuration for cement production."""
    prod_product: BaseVisualizationCfg
    """Visualization configuration for products production."""
    eol_stock: StockVisualizationCfg
    """Visualization configuration for end-of-life stock."""
    carbonation: BaseVisualizationCfg
    """Visualization configuration for carbonation."""


class CementCfg(CommonCfg):

    model_switches: CementModelSwitches
    """Model customization parameters for the cement model."""
    visualization: CementVisualizationCfg
    """Cement visualization configuration."""
