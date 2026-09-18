from typing import List, Optional

from pydantic import field_validator, model_validator
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


def trade_parameters_read_from_data(
    cfg: CommonCfg, trades: list[TradeDefinition]
) -> list[RemindMFAParameterDefinition]:
    """Definitions of the parameters holding future trade read from data (e.g. ATLAS output).

    Returns one import and one export parameter per trade market, with the dimensions of that market.
    Call with the *future* trade definitions.
    """
    trades_by_name = {trade.name: trade for trade in trades}
    parameters = []
    for market in cfg.trade.markets_from_data(cfg.model):
        if market not in trades_by_name:
            raise ValueError(
                f"Trade market '{market}' configured in trade.data_markets is not defined for "
                f"model '{cfg.model.value}'. Available markets: {list(trades_by_name)}."
            )
        for direction in ("imports", "exports"):
            parameters.append(
                RemindMFAParameterDefinition(
                    name=f"trade_{market}_{direction}",
                    dim_letters=trades_by_name[market].dim_letters,
                    description=f"Future {market} {direction} read from data instead of being "
                    "extrapolated from historic trade",
                )
            )
    return parameters


class PlainDataPointDefinition(RemindMFABaseModel):

    name: str
    """Name of the data point."""
    description: Optional[str] = None
    """Description of the parameter."""


class ExtrapolationDefinition(RemindMFAParameterDefinition):
    """Declares a parameter whose values are extrapolated from historic to full time.

    Scenario CSV rows supply the endpoint in the `value` column, either as a number
    or as the name of a model parameter whose values serve as the endpoint at the
    row's coordinates (blending toward another parameter).
    """

    dim_letters: tuple[str, ...] = ()
    """Dimensions for scenario data. Leave empty to extend an existing parameter without scenario data."""
    create_new: bool = False
    """Whether to create the extrapolated parameter instead of reading it from input data."""
    blending_function: str = "linear"
    """Blending function to use for extrapolation. Must be one of the functions defined in `remind_mfa.common.data_blending.BLEND_TYPES`."""
    split_dimension_letter: Optional[str] = None
    """Only required if extrapolating a split. Ensures that along the given dimension the values sum up to 1."""
    split_balancing_item: Optional[str] = None
    """Item of the split dimension that absorbs or provides the residual share when other items are
    targeted. Requires split_dimension_letter. Without it, unspecified items scale proportionally."""

    @field_validator("blending_function")
    @classmethod
    def validate_blending_function(cls, value):
        if value not in BLEND_TYPES:
            raise ValueError(f"Unknown blending function '{value}'. Must be one of {BLEND_TYPES}")
        return value

    @model_validator(mode="after")
    def validate_split_settings(self):
        if self.split_balancing_item is not None and self.split_dimension_letter is None:
            raise ValueError(
                f"'{self.name}': split_balancing_item requires split_dimension_letter."
            )
        if self.split_dimension_letter is None:
            return self
        if not self.dim_letters:
            raise ValueError(
                f"'{self.name}': split_dimension_letter is set but dim_letters is empty. "
                "Add split dimension to dim_letters."
            )
        if self.split_dimension_letter not in self.dim_letters:
            raise ValueError(
                f"'{self.name}': split_dimension_letter '{self.split_dimension_letter}' "
                f"is not in dim_letters {self.dim_letters}."
            )
        return self


scenario_parameters = [
    PlainDataPointDefinition(
        name="driver_scen",
        description="Name of the (SSP) scenario to use for all driver parameters with an `S` dimension",
    ),
    PlainDataPointDefinition(
        name="saturation_level",
        description="Saturation level for material use per capita (unit depends on the material, e.g. t/capita)",
    ),
    ExtrapolationDefinition(
        name="stock_factor",
        dim_letters=("r",),
        create_new=True,
    ),
    ExtrapolationDefinition(
        name="lifetime_mean",
        dim_letters=("r",),
        blending_function="poly_mix",
    ),
    ExtrapolationDefinition(
        name="lifetime_std",
        dim_letters=("r",),
        blending_function="poly_mix",
    ),
]
