from remind_mfa.common.common_config import CommonCfg, ModelSwitches, VisualizationCfg
from remind_mfa.common.helper import CementModes


class CementModelSwitches(ModelSwitches):
    mode: CementModes

    @property
    def carbon_flow(self) -> bool:
        return self.mode == CementModes.CARBON_FLOW


class CementVisualizationCfg(VisualizationCfg):

    consumption: dict = {}
    prod_clinker: dict = {}
    """Visualization configuration for clinker production."""
    prod_cement: dict = {}
    """Visualization configuration for cement production."""
    prod_product: dict = {}
    """Visualization configuration for products production."""
    eol_stock: dict = {}
    """Visualization configuration for end-of-life stock."""
    carbonation: dict = {}


class CementCfg(CommonCfg):

    customization: CementModelSwitches
    visualization: CementVisualizationCfg
