import numpy as np
import flodym as fd
from typing import Callable

from .data_extrapolations import (
    OneDimensionalExtrapolation,
    WeightedProportionalExtrapolation,
)


class StockExtrapolation:

    def __init__(
        self,
        historic_stocks: fd.StockArray,
        dims: fd.DimensionSet,
        parameters: dict[str, fd.Parameter],
        stock_extrapolation_class: OneDimensionalExtrapolation,
        target_dim_letters=None,
        saturation_level=None,
    ):
        self.historic_stocks = historic_stocks
        self.dims = dims
        self.parameters = parameters
        self.stock_extrapolation_class = stock_extrapolation_class
        self.target_dim_letters = target_dim_letters
        self.regression_strategy = self.find_regression_strategy()
        self.n_fit_prms = self.stock_extrapolation_class.n_prms
        self.saturation_level = saturation_level
        self.extrapolate()

    def find_regression_strategy(self) -> Callable:
        """For now, only a regression based on GDP is implemented."""
        return self.gdp_regression

    def extrapolate(self):
        self.per_capita_transformation()
        self.regression_strategy()

    def per_capita_transformation(self):
        if self.target_dim_letters is None:
            self.historic_dim_letters = self.historic_stocks.dims.letters
            self.target_dim_letters = ("t",) + self.historic_dim_letters[1:]
        else:
            self.historic_dim_letters = ("h",) + self.target_dim_letters[1:]

        # transform to per capita
        self.pop = self.parameters["population"]
        self.gdppc = self.parameters["gdppc"]
        self.historic_pop = fd.FlodymArray(dims=self.dims[("h", "r")])
        self.historic_gdppc = fd.FlodymArray(dims=self.dims[("h", "r")])
        self.historic_stocks_pc = fd.FlodymArray(dims=self.dims[self.historic_dim_letters])
        self.stocks_pc = fd.FlodymArray(dims=self.dims[self.target_dim_letters])
        self.stocks = fd.FlodymArray(dims=self.dims[self.target_dim_letters])

        self.historic_pop[...] = self.pop[{"t": self.dims["h"]}]
        self.historic_gdppc[...] = self.gdppc[{"t": self.dims["h"]}]
        self.historic_stocks_pc[...] = self.historic_stocks / self.historic_pop

    def gdp_regression(self):
        """Updates per capita stock to future by extrapolation."""
        prediction_out = self.stocks_pc.values
        historic_in = self.historic_stocks_pc.values
        shape_out = prediction_out.shape
        pure_prediction = np.zeros_like(prediction_out)
        n_historic = historic_in.shape[0]
        self.fit_prms = np.zeros(shape_out[1:] + (self.n_fit_prms,))

        for idx in np.ndindex(shape_out[1:]):
            # idx is a tuple of indices for all dimensions except the time dimension
            index = (slice(None),) + idx
            current_hist_stock_pc = historic_in[index]
            current_gdppc = self.gdppc.values[index[:2]]
            kwargs = {}
            if self.saturation_level is not None:
                kwargs["saturation_level"] = self.saturation_level[idx]
            extrapolation = self.stock_extrapolation_class(
                data_to_extrapolate=current_hist_stock_pc, target_range=current_gdppc, **kwargs
            )
            pure_prediction[index] = extrapolation.regress()
            self.fit_prms[idx] = extrapolation.fit_prms

        prediction_out[...] = pure_prediction - (
            pure_prediction[n_historic - 1, :] - historic_in[n_historic - 1, :]
        )
        prediction_out[:n_historic, ...] = historic_in

        # transform back to total stocks
        self.stocks[...] = self.stocks_pc * self.pop
        self.transform_to_fd_stock_array()

    def transform_to_fd_stock_array(self):
        self.stocks = fd.StockArray(**dict(self.stocks))
        self.stocks_pc = fd.StockArray(**dict(self.stocks_pc))


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
