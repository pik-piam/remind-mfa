from typing import Union

import flodym as fd
import numpy as np


def blend(
        target_dims: fd.DimensionSet,
        y_lower: fd.FlodymArray,
        y_upper: fd.FlodymArray,
        x: fd.FlodymArray,
        x_lower: Union[fd.FlodymArray, int, float],
        x_upper: Union[fd.FlodymArray, int, float],
        type: str = 'poly_mix',
    ) -> fd.FlodymArray:
    x_lower, x_upper = prepare_x_lower_upper(target_dims, x_lower, x_upper)
    x = x.cast_to(target_dims)
    y_lower = y_lower.cast_to(target_dims)
    y_upper = y_upper.cast_to(target_dims)
    x_lower = x_lower.cast_to(target_dims)
    x_upper = x_upper.cast_to(target_dims)

    x = (x - x_lower) / (x_upper - x_lower)
    a = fd.FlodymArray(dims=x.dims, values=blending_factor(x.values, type))
    return a*y_upper + (1-a)*y_lower


def blend_over_time(
        target_dims: fd.DimensionSet,
        y_lower: fd.FlodymArray,
        y_upper: fd.FlodymArray,
        t_lower: Union[fd.FlodymArray, int, float],
        t_upper: Union[fd.FlodymArray, int, float],
        type: str = 'poly_mix',
        time_letter: str = 't',
    ) -> fd.FlodymArray:
    t_lower, t_upper = prepare_x_lower_upper(target_dims, t_lower, t_upper)
    t = fd.FlodymArray(dims=target_dims[time_letter,], values=np.array(target_dims[time_letter].items))
    return blend(target_dims, y_lower, y_upper, t, t_lower, t_upper, type)


def blending_factor(x: np.ndarray, type: str) -> np.ndarray:

    def linear(x):
        x = np.clip(x, 0, 1)
        return x

    def sigmoid3(x):
        return 1. / (1. + np.exp(3-6*x))

    def sigmoid4(x):
        return 1. / (1. + np.exp(4-8*x))

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
        return 3*x**2 - 2*x**3

    def quintic(x):
        x = np.clip(x, 0, 1)
        return 6*x**5 - 15*x**4 + 10*x**3

    def poly_mix(x):
        return 0.5*hermite(x) + 0.5*quintic(x)

    function_map = {
        'linear': linear,
        'sigmoid3': sigmoid3,
        'sigmoid4': sigmoid4,
        'extrapol_sigmoid3': extrapol_sigmoid3,
        'extrapol_sigmoid4': extrapol_sigmoid4,
        'clamped_sigmoid3': clamped_sigmoid3,
        'clamped_sigmoid4': clamped_sigmoid4,
        'hermite': hermite,
        'quintic': quintic,
        'poly_mix': poly_mix
    }

    if type not in function_map:
        raise ValueError(f"Unknown blending function {type}. Must be one of {list(function_map.keys())}")
    return function_map[type](x)


def prepare_x_lower_upper(target_dims: fd.DimensionSet, x_lower, x_upper) -> tuple[fd.FlodymArray, fd.FlodymArray]:
    if isinstance(x_lower, (int, float)):
        x_lower = fd.FlodymArray(dims = target_dims[()], values=np.array(x_lower))
    elif not isinstance(x_lower, fd.FlodymArray):
        raise ValueError("x_lower must be either a FlodymArray or a scalar.")

    if isinstance(x_upper, (int, float)):
        x_upper = fd.FlodymArray(dims = target_dims[()], values=np.array(x_upper))
    elif not isinstance(x_upper, fd.FlodymArray):
        raise ValueError("x_upper must be either a FlodymArray or a scalar.")
    return x_lower, x_upper
