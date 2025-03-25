import numpy as np
from typing import Union
from collections.abc import Iterable
from pydantic import field_validator, model_validator

from simson.common.base_model import SimsonBaseModel


def broadcast_trailing_dimensions(array: np.ndarray, to_shape_of: np.ndarray) -> np.ndarray:
    """Broadcasts array to shape of to_shape_of, adding dimensions if necessary."""
    new_shape = array.shape + (1,) * (len(to_shape_of.shape) - len(array.shape))
    b_reshaped = np.reshape(array, new_shape)
    b_broadcast = np.broadcast_to(b_reshaped, to_shape_of.shape)
    return b_broadcast


class Bound(SimsonBaseModel):
    var_name: str
    lower_bound: Union[float, np.ndarray]
    upper_bound: Union[float, np.ndarray]

    class Config:
        arbitrary_types_allowed = True

    @field_validator("lower_bound", "upper_bound", mode="before")
    def convert_to_array(cls, value):
        return np.array(value)

    @model_validator(mode="after")
    def valdiate_bounds(self):
        if self.lower_bound.shape != self.upper_bound.shape:
            raise ValueError("Lower and upper bounds must have the same shape")
        if np.any(self.lower_bound > self.upper_bound):
            raise ValueError("Lower bounds must be smaller than upper bounds")

        # Check if lower bound equals upper bound
        equal_mask = self.lower_bound == self.upper_bound
        if np.any(equal_mask):
            adjustment = 10e-10
            zero_mask = (self.lower_bound == 0) & (self.upper_bound == 0)

            # Handle case where both bounds are 0
            self.lower_bound[zero_mask] = -adjustment
            self.upper_bound[zero_mask] = adjustment

            # Handle general case where bounds are equal
            non_zero_mask = equal_mask & np.logical_not(zero_mask)
            self.lower_bound[non_zero_mask] -= adjustment * np.abs(self.lower_bound[non_zero_mask])
            self.upper_bound[non_zero_mask] += adjustment * np.abs(self.upper_bound[non_zero_mask])

        return self


def create_bounds_arr(
    bounds_list: list[Bound], all_prm_names: list[str], bound_shape: tuple
) -> np.ndarray:
    """Creates bounds array where each element is tuple of lower and upper bounds for each parameter."""

    if isinstance(bounds_list, Iterable) and len(bounds_list) >= 1:
        if not bound_shape == bounds_list[0].lower_bound.shape:
            raise ValueError("Bounds shape must match target shape")

    if any(
        b.lower_bound.shape != bound_shape or b.upper_bound.shape != bound_shape
        for b in bounds_list
    ):
        raise ValueError("All bounds must have the same shape")

    # Check for invalid parameter names
    invalid_params = set(b.var_name for b in bounds_list) - set(all_prm_names)
    if invalid_params:
        raise ValueError(f"Unknown parameters in bounds: {invalid_params}")

    # bounds = np.empty(bound_shape, dtype=object)
    param_positions = {name: i for i, name in enumerate(all_prm_names)}

    lower_bounds = np.full(bound_shape + (len(all_prm_names),), -np.inf)
    upper_bounds = np.full(bound_shape + (len(all_prm_names),), np.inf)

    for bound in bounds_list:
        pos = param_positions[bound.var_name]
        lower_bounds[..., pos] = bound.lower_bound
        upper_bounds[..., pos] = bound.upper_bound

    bounds = np.stack((lower_bounds, upper_bounds), axis=-2)
    return bounds
