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
    parameter_reconciliation: bool = False
    """Whether to perform parameter reconciliation with bottom-up stock data."""
    force_use_reconciliation_cache: bool = False
    """Whether to use an existing reconciliation cache file of the region mapping even if it was created from different inputs, settings or code (e.g. another scenario). Its log-corrections are then applied to the current input parameters without validation, the reached mismatch is logged, and the file is not overwritten. If no file exists, the reconciliation is computed and saved as usual."""


class CementVisualizationCfg(VisualizationCfg):

    clinker_production: BaseVisualizationCfg
    """Visualization configuration for clinker production."""
    cement_production: BaseVisualizationCfg
    """Visualization configuration for cement production."""
    construction: BaseVisualizationCfg
    """Visualization configuration for construction (construction material production)."""
    eol_stock: StockVisualizationCfg
    """Visualization configuration for end-of-life stock."""
    carbonation: BaseVisualizationCfg
    """Visualization configuration for carbonation."""


class CementCfg(CommonCfg):

    model_switches: CementModelSwitches
    """Model customization parameters for the cement model."""
    visualization: CementVisualizationCfg
    """Cement visualization configuration."""
