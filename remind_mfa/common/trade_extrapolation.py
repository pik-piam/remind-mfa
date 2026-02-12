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
    alpha_rel: float = 0.5
    eps: float = 1e-6
    prevent_negative_domestic: bool = False


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
        self.balance()

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
                self.historic_first *= (
                    self.scaler_first[{"t": self.historic_first.dims["h"]}]
                    .get_shares_over(missing_dims)
                    .apply(np.nan_to_num)
                )
                self.historic_second *= (
                    self.scaler_first[{"t": self.historic_second.dims["h"]}]
                    .get_shares_over(missing_dims)
                    .apply(np.nan_to_num)
                )

    def broadcast_scaler(self):
        all_dims = self.historic_first.dims.union_with(self.scaler_first.dims)
        dim_letters_out = ("t",) + self.historic_first.dims.letters[1:]
        self.dims_out = all_dims[dim_letters_out]

        self.scaler_first = self.scaler_first.cast_to(self.dims_out)

        if self.future_first.dims - self.dims_out:
            raise ValueError("All future trade dimensions must be contained either in scaler or in historic trade.")

    def get_recent_averages(self):
        averager = RecentHistoricalAverage(dims=self.historic_first.dims)

        self.historic_first_0= averager.apply(self.historic_first).cast_to(self.dims_out) * (1 - self.eps)
        self.historic_second_0= averager.apply(self.historic_second).cast_to(self.dims_out) * (1 - self.eps)
        self.scaler_first_0 = averager.apply(self.scaler_first).cast_to(self.dims_out)
        scaler_second_hist = (
            self.scaler_first[{"t": self.historic_first.dims["h"]}]
            - self.historic_first
            + self.historic_second
        )
        self.scaler_second_0 = averager.apply(scaler_second_hist).cast_to(self.dims_out)

    def calc_trade(self):
        self.future_first[...] = self.calc_first(
            i0=self.historic_first_0,
            d0=self.scaler_first_0,
            d=self.scaler_first,
            alpha=self.alpha_rel,
        )
        self.future_first[{"t": self.historic_first.dims["h"]}] = self.historic_first
        if self.prevent_negative_domestic:
            self.future_first[...] = self.future_first.minimum(self.scaler_first * (1 - self.eps))

        self.future_second[...], self.scaler_second = self.calc_second(
            p0=self.scaler_second_0,
            e0=self.historic_second_0,
            dd=self.scaler_first-self.future_first,
            alpha=self.alpha_rel,
        )
        self.future_second[{"t": self.historic_second.dims["h"]}] = self.historic_second
        if self.prevent_negative_domestic:
            self.future_second[...] = self.future_second.minimum(self.scaler_second * (1 - self.eps))

    @staticmethod
    def calc_first(
            i0: fd.FlodymArray,
            d0: fd.FlodymArray,
            d: fd.FlodymArray,
            alpha: float,
        ) -> fd.FlodymArray:
        i = (i0 * d / d0) ** alpha * i0 ** (1 - alpha)
        return i

    @staticmethod
    def calc_second(
            p0: fd.FlodymArray,
            e0: fd.FlodymArray,
            dd: fd.FlodymArray,
            alpha: float,
            eps: float = 1e-6,
        ) -> tuple[fd.FlodymArray, fd.FlodymArray]:
        """
        i - imports, e - exports, d - demand, p - production, dd - domestic demand = d - i
        Variable names assume known demand for simplicity, but the equations are the same for known supply
        (try switching e and i, as well as p and d).
        Subscripts 0 indicate recent historic average value

        Equations:
        (1) i(t) = i0 * (d(t)/d0)^alpha  # imports extrapolation
        (2) e(t) = e0 * (p(t)/p0)^alpha  # exports extrapolation
        (3) d(t) = p(t) - e(t) + i(t)    # mass balance

        known: d(t), p0, e0, d0, i0
        - (1) can be solved directly for i(t) (calc_first routine)
        - unknown: p(t), e(t)
        - insert (2) in (3):
          d(t) = p(t) - e0 * (p(t)/p0)^alpha + i(t)
        - solve Newton-Raphson for p(t) with
          f(p) = 0 = p - e0 * (p/p0)^alpha - (d(t) - i(t))
          we rename (d(t) - i(t)) to dd(t) (domestic demand), which gives:
          f(p) = 0 = p - e0 * (p/p0)^alpha - dd(t)

          How do we find a reliable starting value?
          This function is convex (only the second term e has a second derivative).
          We want the biggest root, so we start with a value bigger than the root
          We derive a lower bound for p via an upper bound for e:
          with P = p/p0, eq (2) gives e(P) = e0 * P^alpha, with the derivative e'(P) = e0 * alpha * P^(alpha-1)
          From the concavity of e, we know that it is smaller than its linearization: e(p) <= eL(p)
          The linearization around P=1 is: eL(P) = e(P=1) + e'(P=1)*(P-1) = e0 + e0 * alpha * (P - 1)
          and thus eL(p) = e0 + e0 * alpha * (p/p0 - 1)

          Inserting s into (3) gives:
          p - e - dd = 0
          p - eL(p) - dd <= 0
          p - e0 - e0 * alpha * (p/p0 - 1) - dd <= 0
          p (1 - e0 * alpha / p0) <= e0 - e0 * alpha + dd
          p <= (e0 - e0 * alpha + dd)) / (1 - e0 * alpha / p0)
        """

        def f(p):
            assert np.min(p.values) > 0
            return p - e0 * (p / p0) ** alpha - dd

        def f_prime(p):
            return 1 - alpha * e0 * (p / p0) ** (alpha - 1) / p0

        def assert_positive(x, name):
            if np.min(x.values) <= -1.e-6:
                raise ValueError(f"All values of {name} must be positive for Newton-Raphson method.")

        # assert_positive(dd, "domestic demand")  # TODO: may not be needed?
        # Somehow needed, but not in this form, because we divide by (1-alpha*e0/p0), which has to be bigger than 1, else the inequality changes sign
        assert_positive((1 - e0 * alpha / p0), "denominator")
        # initial guess (bigger than root)
        p = (e0 - e0 * alpha + dd) / (1 - e0 * alpha / p0)

        # Newton-Raphson method
        for _ in range(100):
            fi = f(p)
            if np.max(np.abs(fi.values)) < eps:
                break
            p -= fi / f_prime(p)
        e = e0 * (p / p0) ** alpha

        return e, p

    def balance(self):
        self.future_trade.balance(to="hmean")

        if self.prevent_negative_domestic:
            self.future_first[...] = self.future_first.minimum(self.scaler_first)
            self.future_second[...] = self.future_second.minimum(self.scaler_second)
            self.future_trade.balance(to="minimum")


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
        return (data * self.weights).sum_over(("h",))
