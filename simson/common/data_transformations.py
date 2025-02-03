import numpy as np
import flodym as fd
from typing import Union

from .data_extrapolations import (
    SigmoidalExtrapolation,
    ExponentialExtrapolation,
    WeightedProportionalExtrapolation,
)


def extrapolate_stock(
    historic_stocks: fd.StockArray,
    dims: fd.DimensionSet,
    parameters: dict[str, fd.Parameter],
    curve_strategy: str,
    target_dim_letters=None,
):
    """Performs the per-capita transformation and the extrapolation."""

    if target_dim_letters is None:
        historic_dim_letters = historic_stocks.dims.letters
        target_dim_letters = ("t",) + historic_dim_letters[1:]
    else:
        historic_dim_letters = ("h",) + target_dim_letters[1:]

    # transform to per capita
    pop = parameters["population"]
    historic_pop = fd.FlodymArray(dims=dims[("h", "r")])
    historic_gdppc = fd.FlodymArray(dims=dims[("h", "r")])
    historic_stocks_pc = fd.FlodymArray(dims=dims[historic_dim_letters])
    stocks_pc = fd.FlodymArray(dims=dims[target_dim_letters])
    stocks = fd.FlodymArray(dims=dims[target_dim_letters])

    historic_pop[...] = pop[{"t": dims["h"]}]
    historic_gdppc[...] = parameters["gdppc"][{"t": dims["h"]}]
    historic_stocks_pc[...] = historic_stocks / historic_pop

    if curve_strategy == "GDP_regression":
        gdp_regression(historic_stocks_pc.values, parameters["gdppc"].values, stocks_pc.values)
    elif curve_strategy == "Exponential_GDP_regression":
        gdp_regression(
            historic_stocks_pc.values,
            parameters["gdppc"].values,
            stocks_pc.values,
            fitting_function_type="exponential",
        )
    else:
        raise RuntimeError(
            f"Extrapolation strategy {curve_strategy} is not defined. "
            f"It needs to be 'GDP_regression'."
        )

    # transform back to total stocks
    stocks[...] = stocks_pc * pop

    # visualize_stock(self, self.parameters['gdppc'], historic_gdppc, stocks, historic_stocks, stocks_pc, historic_stocks_pc)
    return fd.StockArray(**dict(stocks))


def extrapolate_to_future(
    historic_values: fd.FlodymArray, scale_by: fd.FlodymArray
) -> fd.FlodymArray:
    if not historic_values.dims.letters[0] == "h":
        raise ValueError("First dimension of historic_parameter must be historic time.")
    if not scale_by.dims.letters[0] == "t":
        raise ValueError("First dimension of scaler must be time.")
    if not set(scale_by.dims.letters[1:]).issubset(historic_values.dims.letters[1:]):
        raise ValueError("Scaler dimensions must be subset of historic_parameter dimensions.")

    all_dims = historic_values.dims.union_with(scale_by.dims)

    dim_letters_out = ("t",) + historic_values.dims.letters[1:]
    extrapolated_values = fd.FlodymArray.from_dims_superset(
        dims_superset=all_dims, dim_letters=dim_letters_out
    )

    scale_by = scale_by.cast_to(extrapolated_values.dims)

    extrapolation = WeightedProportionalExtrapolation(
        data_to_extrapolate=historic_values.values, target_range=scale_by.values
    )
    extrapolated_values.set_values(extrapolation.extrapolate())

    return extrapolated_values


def gdp_regression(historic_stocks_pc, gdppc, prediction_out, fitting_function_type="sigmoid"):
    shape_out = prediction_out.shape
    pure_prediction = np.zeros_like(prediction_out)
    n_historic = historic_stocks_pc.shape[0]

    if fitting_function_type == "sigmoid":
        extrapolation_class = SigmoidalExtrapolation
    elif fitting_function_type == "exponential":
        extrapolation_class = ExponentialExtrapolation
    else:
        raise ValueError('fitting_function_type must be either "sigmoid" or "exponential".')

    for idx in np.ndindex(shape_out[1:]):
        # idx is a tuple of indices for all dimensions except the time dimension
        index = (slice(None),) + idx
        current_hist_stock_pc = historic_stocks_pc[index]
        current_gdppc = gdppc[index[:2]]
        extrapolation = extrapolation_class(
            data_to_extrapolate=current_hist_stock_pc, target_range=current_gdppc
        )
        pure_prediction[index] = extrapolation.regress()

    prediction_out[...] = pure_prediction - (
        pure_prediction[n_historic - 1, :] - historic_stocks_pc[n_historic - 1, :]
    )
    prediction_out[:n_historic, ...] = historic_stocks_pc
