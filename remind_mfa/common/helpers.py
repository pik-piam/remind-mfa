from enum import Enum
from pydantic import BaseModel, ConfigDict


class ModelNames(str, Enum):
    PLASTICS = "plastics"
    STEEL = "steel"
    CEMENT = "cement"


def prefix_from_module(module: str) -> str:
    return module[:2]


def module_from_prefix(prefix: str) -> str:
    for model in ModelNames:
        if prefix_from_module(model.value) == prefix:
            return model.value
    raise ValueError(f"Unknown prefix: {prefix}")


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
