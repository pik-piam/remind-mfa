from enum import Enum
from pydantic import BaseModel, ConfigDict
from flodym import ParameterDefinition, MFADefinition
from typing import Optional, List

from remind_mfa.common.trade import TradeDefinition


class ModelNames(str, Enum):
    PLASTICS = "plastics"
    STEEL = "steel"
    CEMENT = "cement"


class RemindMFABaseModel(BaseModel):

    model_config = ConfigDict(
        extra="forbid",
        protected_namespaces=(),
        arbitrary_types_allowed=True,
        use_attribute_docstrings=True,
    )


class RemindMFAParameterDefinition(ParameterDefinition):

    description: Optional[str] = None
    """Description of the parameter."""


class PlainDataPointDefinition(RemindMFABaseModel):

    name: str
    """Name of the data point."""
    description: Optional[str] = None
    """Description of the parameter."""


# Required such that the model_dump() call in the to_dfs() method knows about the additional
# description field in the parameter definition objects
class RemindMFADefinition(MFADefinition):
    """All the information needed to define an MFA system, compiled of lists of definition objects."""

    trades: List[TradeDefinition] = []
    parameters: List[RemindMFAParameterDefinition]
    """List of definitions of parameters used in the model."""


class CementModes(str, Enum):
    BASE = "base"
    CARBON_FLOW = "carbon_flow"
