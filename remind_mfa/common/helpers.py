from enum import Enum
from pydantic import BaseModel, ConfigDict


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


class RegressOverModes(str, Enum):
    GDPPC = "gdppc"
    LOGGDPPC = "loggdppc"
    LOCGDPPC_TIME_WEIGHTED_SUM = "loggdppc_time_weighted_sum"
