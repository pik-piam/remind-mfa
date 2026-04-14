from enum import Enum
from remind_mfa.common.common_config import (
    CommonCfg,
    ModelSwitches,
    VisualizationCfg,
    BaseVisualizationCfg,
    StockVisualizationCfg,
)

class CementModelSwitches(ModelSwitches):
    """This class adds extra model switches specific to the cement MFA."""
    
    carbonation: bool = False
    """Whether to run the carbonation model to account for process CO2 emissions and carbon uptake."""


class CementVisualizationCfg(VisualizationCfg):

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
