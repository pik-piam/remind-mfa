from typing import List, Literal, Optional

from pydantic import field_validator
import flodym as fd

from remind_mfa.common.data_blending import BLEND_TYPES
from remind_mfa.common.helpers import (
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


class ExtrapolationDefinition(RemindMFAParameterDefinition):

    # from parent class
    # name: str
    # description: Optional[str] = None
    dim_letters: tuple[str, ...] = ()
    """Dimensions for scenario data. Leave empty to extend an existing parameter without scenario data."""
    create_new: bool = False
    """Whether to create the extrapolated parameter instead of reading it from input data."""
    type: Optional[Literal["factor", "target"]] = None
    """Whether scenario values are relative factors or absolute targets."""
    blending_function: str = "linear"
    """Blending function to use for extrapolation. Must be one of the functions defined in `remind_mfa.common.data_blending.BLEND_TYPES`."""
    split_dimension_letter: Optional[str] = None
    """Only required if extrapolating a split. Ensures that along the given dimension the values sum  up to 1."""

    @field_validator("blending_function")
    @classmethod
    def validate_blending_function(cls, value):
        if value not in BLEND_TYPES:
            raise ValueError(f"Unknown blending function '{value}'. Must be one of {BLEND_TYPES}")
        return value

    # TODO later: potential checks
    # - is split dimension only one letter, is it one of the dim_letters?
    # - check if blend function exists


# extras: year, residual_item


scenario_parameters = [
    PlainDataPointDefinition(
        name="driver_scen",
        description="Name of the (SSP) scenario to use for all driver parameters with an `S` dimension",
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
    ExtrapolationDefinition(
        name="lifetime_mean",
        dim_letters=("r",),
        type="factor",
        blending_function="poly_mix",
    ),
    ExtrapolationDefinition(
        name="lifetime_std",
        dim_letters=("r",),
        type="factor",
        blending_function="poly_mix",
    ),
]
