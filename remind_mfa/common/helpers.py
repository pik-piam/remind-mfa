import logging
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from pathlib import Path

import flodym as fd
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from remind_mfa.common.common_model import CommonModel

_SERIES_EXPORT_PATH = None

DOCS_PATH = Path(__file__).parents[2] / "docs"


def _timestamp_prefix() -> str:
    return datetime.now().strftime("%Y-%m-%d--%H-%M-%S")


def export_dir_prefix(prescribed_prefix: str | None = None) -> str:
    """Return the export prefix, creating it once and reusing it across model runs."""
    return prescribed_prefix if prescribed_prefix is not None else _timestamp_prefix()


def series_export_path(base_path: str, prefix: str | None = None) -> str:
    """Return the series prefix, creating it once and reusing it across model runs."""
    global _SERIES_EXPORT_PATH
    if _SERIES_EXPORT_PATH is None:
        _SERIES_EXPORT_PATH = Path(base_path) / (export_dir_prefix(prefix) + "_series")
    return _SERIES_EXPORT_PATH


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


def clip_negative_arr(arr: fd.FlodymArray, warn_small_negative: bool = True) -> fd.FlodymArray:
    """Set negative values of an array to 0, with a warning.

    Args:
        arr: Array to clip. If it has a region dimension (r), the warning lists the regions with
            negative values.
        warn_small_negative: Whether to also warn if all negative values are small, as these
            may originate from numerical issues.

    Returns:
        The array with negative values set to 0.
    """
    min_value = arr.values.min()
    if min_value >= 0:
        return arr
    small_negative_threshold = 1e-6
    is_small = abs(min_value) <= small_negative_threshold
    if not is_small or warn_small_negative:
        message = f"{arr.name} <0"
        if "r" in arr.dims:
            negative_regions = [r for r in arr.dims["r"].items if arr[r].values.min() < 0]
            message += f" in regions {negative_regions}"
        logging.warning(f"{message}! Correcting negative values to 0.")
    return arr.maximum(0)


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
