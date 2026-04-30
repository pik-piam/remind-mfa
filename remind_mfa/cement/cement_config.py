from remind_mfa.common.helpers import RemindMFABaseModel
from remind_mfa.common.common_config import (
    CommonCfg,
    ModelSwitches,
    VisualizationCfg,
    BaseVisualizationCfg,
    StockVisualizationCfg,
)


class ParameterReconciliationSwitches(RemindMFABaseModel):
    do_reconcile: bool = False
    """Whether to perform parameter reconciliation with bottom-up stock data."""
    do_combine_mfas: bool = False
    """Whether to compute a combined MFA using BU stock where available and TD stock otherwise."""


class CementModelSwitches(ModelSwitches):
    """This class adds extra model switches specific to the cement MFA."""

    carbonation: bool = False
    """Whether to run the carbonation model to account for process CO2 emissions and carbon uptake."""
    parameter_reconciliation: ParameterReconciliationSwitches = ParameterReconciliationSwitches()
    """Cement-specific switches for parameter reconciliation and combined MFA generation."""


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
