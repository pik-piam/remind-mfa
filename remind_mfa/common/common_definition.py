from typing import List, Optional
import flodym as fd

from remind_mfa.common.helper import (
    RemindMFABaseModel,
)
from remind_mfa.common.common_config import CommonCfg
from remind_mfa.common.trade import TradeDefinition


class RemindMFAParameterDefinition(fd.ParameterDefinition):

    description: Optional[str] = None
    """Description of the parameter."""


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
    RemindMFAParameterDefinition(
        name="lifetime_factor",
        dim_letters=("r",),
    ),
    PlainDataPointDefinition(
        name="lifetime_factor_blending_year",
    ),
]
