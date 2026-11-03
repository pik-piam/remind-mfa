from remind_mfa.common.common_config import CommonCfg, ModelSwitches


class CementModelSwitches(ModelSwitches):
    """This class adds extra model switches specific to the cement MFA."""

    carbonation: bool = False
    """Whether to run the carbonation model to account for process CO2 emissions and carbon uptake."""
    parameter_reconciliation: bool = False
    """Whether to perform parameter reconciliation with bottom-up stock data."""


class CementCfg(CommonCfg):

    model_switches: CementModelSwitches
    """Model customization parameters for the cement model."""
