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


# Required such that the model_dump() call in the to_dfs() method knows about the additional
# description field in the parameter definition objects
class CementModes(str, Enum):
    BASE = "base"
    CARBON_FLOW = "carbon_flow"
