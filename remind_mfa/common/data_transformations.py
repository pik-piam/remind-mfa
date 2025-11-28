import flodym as fd
import numpy as np
from typing import Union
from pydantic import model_validator, Field

from remind_mfa.common.helper import RemindMFABaseModel


def broadcast_trailing_dimensions(array: np.ndarray, to_shape_of: np.ndarray) -> np.ndarray:
    """Broadcasts array to shape of to_shape_of, adding dimensions if necessary."""
    new_shape = array.shape + (1,) * (len(to_shape_of.shape) - len(array.shape))
    b_reshaped = np.reshape(array, new_shape)
    b_broadcast = np.broadcast_to(b_reshaped, to_shape_of.shape)
    return b_broadcast


class Bound(RemindMFABaseModel):
    """
    Flodym-compatible bounds for a parameter.
    """

    var_name: str
    """Name of the variable for which the bounds are defined."""
    dims: fd.DimensionSet = fd.DimensionSet(dim_list=[])
    """Dimensions of the bounds. Not required if bounds are scalar.
    May also be part of the lower and upper bounds."""
    lower_bound: fd.FlodymArray
    upper_bound: fd.FlodymArray

    @model_validator(mode="before")
    @classmethod
    def convert_to_fd_array(cls, data: dict):
        required_fields = ["var_name", "lower_bound", "upper_bound"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        # extract variables
        var_name = data.get("var_name")
        dims = data.get("dims")
        lower = data.get("lower_bound")
        upper = data.get("upper_bound")

        # prepare bounds and dimensions
        lower, dims = cls._extract_bound_array(lower, dims, "lower")
        upper, dims = cls._extract_bound_array(upper, dims, "upper")

        if dims is None:
            dims = cls.model_fields.get("dims").default

        return {
            "var_name": var_name,
            "lower_bound": fd.FlodymArray(dims=dims, values=lower, name="lower_bound"),
            "upper_bound": fd.FlodymArray(dims=dims, values=upper, name="upper_bound"),
            "dims": dims,
        }

    @staticmethod
    def _extract_bound_array(input_val, dims, bound_name):
        """
        Extracts the array from the input value, ensuring it matches the expected dimensions.
        """
        if isinstance(input_val, np.ndarray):
            return input_val.copy().astype(np.float64), dims
        elif isinstance(input_val, fd.FlodymArray):
            if dims is None:
                dims = input_val.dims
            elif input_val.dims != dims:
                raise ValueError(
                    f"{bound_name.capitalize()} bound dimensions {input_val.dims} do not match expected dims {dims}."
                )
            return input_val.values.copy().astype(np.float64), dims
        else:
            return np.array(input_val, dtype=np.float64), dims

    @model_validator(mode="after")
    def validate_bounds(self):
        lb = self.lower_bound.values
        ub = self.upper_bound.values

        if np.any(lb > ub):
            raise ValueError("Lower bounds must be smaller than upper bounds")

        # Check if lower bound equals upper bound and slightly adjust (required for scipy optimizer)
        equal_mask = lb == ub
        if np.any(equal_mask):
            lb[equal_mask] = np.nextafter(lb[equal_mask], -np.inf) * (1 + 1e-6)
            ub[equal_mask] = np.nextafter(ub[equal_mask], np.inf) * (1 + 1e-6)

        return self

    def extend_dims(self, target_dims: fd.DimensionSet):
        """
        Extend the bounds to a new set of dimensions.
        """
        self.lower_bound = self.lower_bound.cast_to(target_dims)
        self.upper_bound = self.upper_bound.cast_to(target_dims)
        self.dims = target_dims
        return self


class BoundList(RemindMFABaseModel):
    """
    Collection of Bound objects for (multiple) parameters.
    """

    bound_list: list[Bound] = Field(default_factory=list)
    """List of bounds for parameters."""
    target_dims: fd.DimensionSet = fd.DimensionSet(dim_list=[])
    """Dimension of the extrapolation to which the bounds are extended."""

    @model_validator(mode="after")
    def cast_bounds(self):
        for idx, bound in enumerate(self.bound_list):
            if set(bound.dims.letters).issubset(self.target_dims.letters):
                self.bound_list[idx] = bound.extend_dims(self.target_dims)
            else:
                raise ValueError(f"Bound {bound.var_name} has dimensions not in target_dims.")
        return self

    def to_np_array(self, all_prm_names: list[str]) -> np.ndarray:
        """
        Creates bounds array where each element is tuple of lower and upper bounds for each parameter.
        Useful if bounds should be passed to optimization algorthms like from scipy.
        Args:
            all_prm_names: List of all parameter names that ensure right order of bounds.
        Returns:
            np.ndarray: bound information for each parameter.
        """

        if self.bound_list == []:
            return None

        invalid_params = set(b.var_name for b in self.bound_list) - set(all_prm_names)
        if invalid_params:
            raise ValueError(f"Unknown parameters in bounds: {invalid_params}")

        bound_shape = self.bound_list[0].upper_bound.values.shape
        param_positions = {name: i for i, name in enumerate(all_prm_names)}

        lower_bounds = np.full(bound_shape + (len(all_prm_names),), -np.inf)
        upper_bounds = np.full(bound_shape + (len(all_prm_names),), np.inf)

        for bound in self.bound_list:
            pos = param_positions[bound.var_name]
            lower_bounds[..., pos] = bound.lower_bound.values
            upper_bounds[..., pos] = bound.upper_bound.values

        bounds = np.stack((lower_bounds, upper_bounds), axis=-2)
        return bounds
