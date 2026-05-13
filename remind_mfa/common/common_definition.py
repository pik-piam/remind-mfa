from typing import List, Optional
import flodym as fd

from remind_mfa.common.helpers import (
    RemindMFABaseModel,
)
from remind_mfa.common.common_config import CommonCfg
from remind_mfa.common.trade import TradeDefinition


class RemindMFAParameterDefinition(fd.ParameterDefinition):

    description: Optional[str] = None
    """Description of the parameter."""
    scenario_folder: Optional[str] = None
    """If set, the parameter file is read from ``input_data/<scenario_folder>/<scenario>/``
    instead of the shared ``input_data/`` directory, where ``<scenario>`` comes from
    ``cfg.transience.transience_scenario``. Use this for parameters that differ between transience scenarios."""


class RemindMFADefinition(fd.MFADefinition):
    """All the information needed to define an MFA system, compiled of lists of definition objects."""

    trades: List[TradeDefinition] = []
    parameters: List[RemindMFAParameterDefinition]
    """List of definitions of parameters used in the model."""


def get_definition():
    return RemindMFADefinition(
        dimensions=[], processes=[], flows=[], stocks=[], parameters=[], trades=[]
    )


class PlainDataPointDefinition(RemindMFABaseModel):

    name: str
    """Name of the data point."""
    description: Optional[str] = None
    """Description of the parameter."""


scenario_parameters = [
    PlainDataPointDefinition(
        name="gdp_pop_scen", description="Name of the (SSP) scenario to use for GDP and population"
    ),
    PlainDataPointDefinition(
        name="saturation_level",
        description="Saturation level for material use per capita (unit depends on the material, e.g. t/capita)",
    ),
    RemindMFAParameterDefinition(
        name="stock_factor",
        dim_letters=("r",),
    ),
    RemindMFAParameterDefinition(
        name="stock_factor_year",
        dim_letters=("r",),
    ),
    RemindMFAParameterDefinition(
        name="lifetime_factor",
        dim_letters=("r",),
    ),
    RemindMFAParameterDefinition(
        name="lifetime_factor_year",
        dim_letters=("r",),
    ),
]
