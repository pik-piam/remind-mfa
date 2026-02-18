import sys
import numpy as np
import flodym as fd
from pydantic import model_validator, ConfigDict

from remind_mfa.common.data_transformations import broadcast_trailing_dimensions
from remind_mfa.common.trade import Trade
from remind_mfa.common.helpers import RemindMFABaseModel


class TradeExtrapolator(RemindMFABaseModel):
    """Predict future trade values by extrapolating the trade data using a given scaler."""

    model_config = ConfigDict(extra="allow")

    historic_trade: Trade
    """historic_trade (Trade): Historic trade data."""
    future_trade: Trade
    """future_trade (Trade): Future trade data, which is written to."""
    future_supply: fd.FlodymArray = None
    """future_supply (FlodymArray): The supply values to scale the historic exports by.
    In this forward mode, the imports are scaled subsequently by supply + exports.
    """
    future_demand: fd.FlodymArray = None
    """future_demand (FlodymArray): The demand values to scale the historic imports by.
    In this backward mode, the exports are scaled subsequently by demand - imports.
    """
    alpha_rel: float = 2/3
    eps: float = 1e-6

    @model_validator(mode="after")
    def validate_inputs(self):
        if (self.future_supply is None) == (self.future_demand is None):
            raise ValueError("Exactly one of future_supply or future_demand must be set.")
        if "h" not in self.historic_trade.imports.dims:
            raise ValueError("Historic trade data must have a historic time dimension.")
        if "t" not in (self.future_demand or self.future_supply).dims.letters:
            raise ValueError("Future demand or supply must have a (full) time dimension.")
        return self

    def run(self):
        self.set_parameters()
        self.extract_attributes()
        self.broadcast_historic_trade()
        self.broadcast_scaler()
        self.get_recent_averages()
        self.calc_trade()

    def set_parameters(self):
        if self.future_supply is not None:
            self.scaler_first = self.future_supply
            self.scaled_first = "exports"
            self.scaled_second = "imports"
        else:
            self.scaler_first = self.future_demand
            self.scaled_first = "imports"
            self.scaled_second = "exports"

    def extract_attributes(self):
        self.historic_first = getattr(self.historic_trade, self.scaled_first)
        self.historic_second = getattr(self.historic_trade, self.scaled_second)
        self.future_first = getattr(self.future_trade, self.scaled_first)
        self.future_second = getattr(self.future_trade, self.scaled_second)

    def broadcast_historic_trade(self):
        missing_dims = self.scaler_first.dims.difference_with(self.historic_trade.imports.dims).letters[1:]

        if len(missing_dims) > 0:
            with np.errstate(divide="ignore"):
                self.historic_first[...] *= (
                    self.scaler_first[{"t": self.historic_first.dims["h"]}]
                    .get_shares_over(missing_dims)
                    .apply(np.nan_to_num)
                )
                self.historic_second[...] *= (
                    self.scaler_first[{"t": self.historic_second.dims["h"]}]
                    .get_shares_over(missing_dims)
                    .apply(np.nan_to_num)
                )

    def broadcast_scaler(self):
        self.dims_out = self.future_trade.exports.dims
        common_dims = self.scaler_first.dims.intersect_with(self.dims_out)
        self.scaler_first = self.scaler_first.sum_to(common_dims.letters).cast_to(self.dims_out)

        if self.future_first.dims - self.dims_out:
            raise ValueError("All future trade dimensions must be contained either in scaler or in historic trade.")

    def get_recent_averages(self):
        averager = RecentHistoricalAverage(dims=self.historic_first.dims)

        self.historic_first_0= averager.apply(self.historic_first).cast_to(self.dims_out) #* (1 - self.eps)
        self.historic_second_0= averager.apply(self.historic_second).cast_to(self.dims_out) #* (1 - self.eps)
        self.scaler_first_0 = averager.apply(self.scaler_first).cast_to(self.dims_out)
        scaler_second_hist = (
            self.scaler_first[{"t": self.historic_first.dims["h"]}]
            - self.historic_first
            + self.historic_second
        )
        self.scaler_second_0 = averager.apply(scaler_second_hist).cast_to(self.dims_out)

    def calc_trade(self):
        linear_scaling = self.scaler_first / self.scaler_first_0
        self.future_first_linear = self.historic_first_0 * linear_scaling
        self.future_second_linear = self.historic_second_0 * linear_scaling
        self.scaler_second_linear = self.scaler_second_0 * linear_scaling

        id_historic = {"t": self.historic_first.dims["h"]}
        scaling = self.scaling(
            d0=self.scaler_first_0,
            d=self.scaler_first,
            alpha=self.alpha_rel,
        )
        self.future_first[...] = self.historic_first_0 * scaling
        self.future_first[id_historic] = self.historic_first

        re_exports_0 = (self.historic_second_0 - self.scaler_second_0).maximum(0)
        self.historic_second_0[...] -= re_exports_0
        re_exports = re_exports_0 * scaling

        self.future_second[...] = self.historic_second_0 * scaling
        self.future_second[id_historic] = self.historic_second
        for _ in range(1):
            self.scaler_second = self.scaler_first - self.future_first + self.future_second + re_exports
            scaling = self.scaling(
                d0=self.scaler_second_0,
                d=self.scaler_second,
                alpha=self.alpha_rel,
            )
            self.future_second[...] = self.historic_second_0 * scaling
            self.future_second[id_historic] = self.historic_second

        self.future_second[...] += re_exports
        self.future_second[id_historic] = self.historic_second

        self.future_trade.balance(to="hmean")
        # demand - imports + exports = demand-net_imports
        # should be positive; else scale down imports
        for i in range(10):
            production = self.scaler_first - self.future_first + self.future_second
            excess_trade = - (production.minimum(0.))
            total_excess = excess_trade.sum_over("r")
            if np.max(total_excess.values) < 0.1:
                break
            self.future_first[...] -= excess_trade
            self.future_trade.balance(to="minimum")

        np.testing.assert_array_almost_equal(
            self.future_first.sum_over("r",).values,
            self.future_second.sum_over("r",).values,
            decimal=0
        )

    @staticmethod
    def scaling(
            d0: fd.FlodymArray,
            d: fd.FlodymArray,
            alpha: float,
        ) -> fd.FlodymArray:
        assert np.min(d.values) >= - 1e-6 * np.max(np.abs(d.values))
        assert np.min(d0.values) >= - 1e-6 * np.max(np.abs(d0.values))
        d = d.maximum(0)
        d0 = d0.maximum(1)
        return ((d / d0) ** alpha).minimum(d/d0)


class RecentHistoricalAverage(RemindMFABaseModel):
    """Extrapolates data by taking the average of the most recent historical years."""

    dims: fd.DimensionSet
    """Dimensions of historical data to take the average over"""
    n_years: int = 5
    """Number of most recent historical years to average over."""
    _weights: fd.FlodymArray = None
    """internal array to be filled with weights"""

    @model_validator(mode="after")
    def validate_dims(self):
        if self.dims.letters[0] != "h":
            raise ValueError("First dimension of dims must be historic time 'h'.")
        return self

    @property
    def weights(self) -> fd.FlodymArray:
        """Weights for the average calculation."""
        if self._weights is None:
            self.init_weights()
        return self._weights

    def init_weights(self):
        n_hist_points = self.dims.shape[0]
        weights_1d = np.maximum(0.0, np.arange(-n_hist_points, 0) + self.n_years + 1)
        weights_1d = weights_1d / weights_1d.sum()
        values = broadcast_trailing_dimensions(weights_1d, self.dims)
        self._weights = fd.FlodymArray(dims=self.dims, values=values)

    def apply(self, data: fd.FlodymArray) -> fd.FlodymArray:
        """Calculates the weighted average over the historical dimension.

        Args:
            data (FlodymArray): Data to average over last historical years. First dimension can be t or h. Must have same shape as self.dims otherwise.

        Returns:
            FlodymArray: Averaged data.
        """
        if "t" in data.dims:
            data = data[{"t": self.dims["h"]}]
        if data.shape != self.dims.shape:
            raise ValueError("Data shape must match the dimensions shape.")
        average = (data * self.weights).sum_over(("h",))
        if np.min(average.values) < -1e-6 * np.max(np.abs(average.values)):
            items = average.items_where(lambda x: x < -1e-6 * np.max(np.abs(x)))
            raise ValueError(f"Negative value in average: {items}")
        else:
            return average
