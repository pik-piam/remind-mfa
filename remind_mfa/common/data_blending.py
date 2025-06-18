from typing import Union, Any

import flodym as fd
import numpy as np


def blend(
    target_dims: fd.DimensionSet,
    y_lower: fd.FlodymArray,
    y_upper: fd.FlodymArray,
    x: Union[fd.FlodymArray, str],  # str: dimension letter
    x_lower: Union[fd.FlodymArray, int, float],
    x_upper: Union[fd.FlodymArray, int, float],
    type: str = "poly_mix",
) -> fd.FlodymArray:
    if isinstance(x, str):
        x = fd.FlodymArray(dims=target_dims[(x,)], values=np.array(target_dims[x].items))
    x = x.cast_to(target_dims)
    y_lower = prepare_array(y_lower, target_dims)
    y_upper = prepare_array(y_upper, target_dims)
    x_lower = prepare_array(x_lower, target_dims)
    x_upper = prepare_array(x_upper, target_dims)

    x = (x - x_lower) / (x_upper - x_lower)
    a = fd.FlodymArray(dims=x.dims, values=blending_factor(x.values, type))
    return a * y_upper + (1 - a) * y_lower


def blending_factor(x: np.ndarray, type: str) -> np.ndarray:

    def linear(x):
        x = np.clip(x, 0, 1)
        return x

    def sigmoid3(x):
        return 1.0 / (1.0 + np.exp(3 - 6 * x))

    def sigmoid4(x):
        return 1.0 / (1.0 + np.exp(4 - 8 * x))

    def extrapol_sigmoid3(x):
        return (sigmoid3(x) - sigmoid3(0)) / (sigmoid3(1) - sigmoid3(0))

    def extrapol_sigmoid4(x):
        return (sigmoid4(x) - sigmoid4(0)) / (sigmoid4(1) - sigmoid4(0))

    def clamped_sigmoid3(x):
        x = np.clip(x, 0, 1)
        return extrapol_sigmoid3(x)

    def clamped_sigmoid4(x):
        x = np.clip(x, 0, 1)
        return extrapol_sigmoid4(x)

    def hermite(x):
        x = np.clip(x, 0, 1)
        return 3 * x**2 - 2 * x**3

    def quintic(x):
        x = np.clip(x, 0, 1)
        return 6 * x**5 - 15 * x**4 + 10 * x**3

    def poly_mix(x):
        return 0.5 * hermite(x) + 0.5 * quintic(x)

    def converge_quadratic(x):
        x = np.clip(x, 0, 1)
        return 1 - (1 - x) ** 2

    function_map = {
        "linear": linear,
        "sigmoid3": sigmoid3,
        "sigmoid4": sigmoid4,
        "extrapol_sigmoid3": extrapol_sigmoid3,
        "extrapol_sigmoid4": extrapol_sigmoid4,
        "clamped_sigmoid3": clamped_sigmoid3,
        "clamped_sigmoid4": clamped_sigmoid4,
        "hermite": hermite,
        "quintic": quintic,
        "poly_mix": poly_mix,
        "converge_quadratic": converge_quadratic,
    }

    if type not in function_map:
        raise ValueError(
            f"Unknown blending function {type}. Must be one of {list(function_map.keys())}"
        )
    return function_map[type](x)


def prepare_array(value: Any, target_dims: fd.DimensionSet) -> fd.FlodymArray:
    if isinstance(value, (int, float)):
        array = fd.FlodymArray(dims=target_dims)
        array[...] = value
    elif isinstance(value, fd.FlodymArray):
        array = value.cast_to(target_dims)
    else:
        raise ValueError("value must be either a FlodymArray or a scalar.")
    return array
