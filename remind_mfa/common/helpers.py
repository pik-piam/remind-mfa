from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from remind_mfa.common.common_model import CommonModel

EXPORT_DIR_PREFIX = None


def get_export_dir_prefix() -> str:
    """Prefix for export directory names. If set to a fixed string previously, retrieve that.
    Else, default to a current timestamp.
    """
    if EXPORT_DIR_PREFIX is None:
        return datetime.now().strftime("%Y-%m-%d--%H-%M-%S")
    return EXPORT_DIR_PREFIX


def set_export_dir_prefix(prefix: str) -> None:
    """Set a prefix for export file and folder names."""
    global EXPORT_DIR_PREFIX
    EXPORT_DIR_PREFIX = prefix


class ModelNames(str, Enum):
    PLASTICS = "plastics"
    STEEL = "steel"
    CEMENT = "cement"


def get_model_class(name: ModelNames) -> type["CommonModel"]:

    match name:
        case ModelNames.PLASTICS:
            from remind_mfa.plastics.plastics_model import PlasticsModel

            return PlasticsModel
        case ModelNames.STEEL:
            from remind_mfa.steel.steel_model import SteelModel

            return SteelModel
        case ModelNames.CEMENT:
            from remind_mfa.cement.cement_model import CementModel

            return CementModel


def init_model(cfg: dict) -> "CommonModel":
    """Choose an MFA subclass and return an initialized instance."""

    if "model" not in cfg:
        raise ValueError("'model' must be given.")
    model = ModelNames(cfg["model"])
    return get_model_class(model)(cfg=cfg)


def prefix_from_module(module: str) -> str:
    if len(module) < 2:
        raise ValueError("Module name must be at least 2 characters long")
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
    LOGGDPPC = "loggdppc"
    LOGGDPPC_TIME = "loggdppc_time"
