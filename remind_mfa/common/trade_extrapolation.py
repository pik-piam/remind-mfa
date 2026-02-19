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
    future_dom_supply: fd.FlodymArray = None
    """future_dom_supply (FlodymArray): The domestic supply values to scale the historic exports by.
    Setting this means calculating trade in forward mode
    """
    future_dom_demand: fd.FlodymArray = None
    """future_demand (FlodymArray): The domestic demand values to scale the historic imports by.
    Setting this means calculating trade in backward mode
    """
    alpha_rel: float = 2 / 3
    """Exponent with which increases in the scaler are applied to the trade.
    (reductions are always applied linearly)
    1 means linear scaling, <1 means sub-linear scaling, 0 means temporally constant trade.
    """
    _eps: float = 1e-6
    """Small value to avoid division by zero and to check for near-zero values in the data."""

    @model_validator(mode="after")
    def validate_inputs(self):
        if (self.future_dom_supply is None) == (self.future_dom_demand is None):
            raise ValueError("Exactly one of future_dom_supply or future_dom_demand must be set.")
        if "t" not in (self.future_dom_demand or self.future_dom_supply).dims.letters:
            raise ValueError("Future domestic demand or supply must have a (full) time dimension.")
        if "h" not in self.historic_trade.imports.dims:
            raise ValueError("Historic trade data must have a historic time dimension.")
        if "t" not in self.future_trade.imports.dims:
            raise ValueError("Historic trade data must have a historic time dimension.")
        # all other dims must be the same
        if self.historic_trade.imports.dims.drop("h") != self.future_trade.imports.dims.drop("t"):
            raise ValueError(
                "Apart from time, historic and future trade data must have the same dimensions."
            )
        return self

    def run(self):
        self.set_direction()
        self.extract_attributes()
        self.broadcast_scaler()
        self.get_recent_averages()
        self.calc_trade()

    def set_direction(self):
        """Either future domestic supply or future domestic demand are known.
        The other is calculated together with trade and depends on trade.
        We scale imports with dom. demand and exports with dom. supply, using the same function f:
        imports = f(dom_demand), exports = f(dom_supply)
        The mass balance reads
        total_supply = total demand
        where
        total_supply = dom_supply + imports
        and
        total_demand = dom_demand + exports
        so
        dom_supply + imports = dom_demand + exports
        So the algorithm stays the same if we switch dom_supply with dom_demand AND imports with
        exports. We use this symmetry to use the same code for both cases.
        If we know dom_demand, imports are scaled first, then exports & dom_supply are calculated together.
        If we know dom_supply, exports are scaled first, then imports & dom_demand are calculated together.
        """
        if self.future_dom_supply is not None:
            self.scaler_first = self.future_dom_supply
            self.scaled_first = "exports"
            self.scaled_second = "imports"
        else:
            self.scaler_first = self.future_dom_demand
            self.scaled_first = "imports"
            self.scaled_second = "exports"

    def extract_attributes(self):
        """Get flodym arrays for imports and exports depending on the direction set in
        set_direction.
        """
        self.historic_first = getattr(self.historic_trade, self.scaled_first)
        self.historic_second = getattr(self.historic_trade, self.scaled_second)
        self.future_first = getattr(self.future_trade, self.scaled_first)
        self.future_second = getattr(self.future_trade, self.scaled_second)

    def broadcast_scaler(self):
        """Sum over excess dims of scaler, broadcast across missing dims.
        Makes sure scaler has same dims as trade data.
        """
        self.dims_out = self.future_trade.exports.dims
        common_dims = self.scaler_first.dims.intersect_with(self.dims_out)
        self.scaler_first = self.scaler_first.sum_to(common_dims.letters).cast_to(self.dims_out)

        if self.future_first.dims - self.dims_out:
            raise ValueError(
                "All future trade dimensions must be contained either in scaler or in historic trade."
            )

    def get_recent_averages(self):
        """Calculate weighted average across las few historical years for both imports and exports,
        and for the scaler. These are used as starting points/reference for the extrapolation, to
        avoid extrapolating from a single year which might be an outlier.
        """
        averager = RecentHistoricalAverage(dims=self.historic_first.dims)

        self.historic_first_0 = averager.apply(self.historic_first).cast_to(
            self.dims_out
        )  # * (1 - self.eps)
        self.historic_second_0 = averager.apply(self.historic_second).cast_to(
            self.dims_out
        )  # * (1 - self.eps)
        self.scaler_first_0 = averager.apply(self.scaler_first).cast_to(self.dims_out)
        scaler_second_hist = (
            self.scaler_first[{"t": self.historic_first.dims["h"]}]
            - self.historic_first
            + self.historic_second
        )
        self.scaler_second_0 = averager.apply(scaler_second_hist).cast_to(self.dims_out)

    def calc_trade(self):
        """The actual trade calculations"""

        self.id_hist = {"t": self.historic_first.dims["h"]}
        first_scaling = self.scale_first()
        stopover_trade = self.scale_stopover(first_scaling)
        self.scale_second(first_scaling, stopover_trade)
        self.balance()

    def scale_first(self) -> fd.FlodymArray:
        # 1) scale "first" trade flow (imports in demand-driven mode)
        scaling = self.scaling(
            d0=self.scaler_first_0,
            d=self.scaler_first,
            alpha=self.alpha_rel,
        )
        self.future_first[...] = self.historic_first_0 * scaling
        # make sure historical years equal historical data
        self.future_first[self.id_hist] = self.historic_first
        return scaling

    def scale_stopover(self, first_scaling: fd.FlodymArray) -> fd.FlodymArray:
        """Sometimes trade exceeds domestic supply and demand.
        For example, a country could have zero production (i.e. all supply through imports),
        but still have some exports, because we bundle together trade across several stages
        along the fabrication process. So it imports semi-finished products and exports
        finished products. In this case, it makes no sense to scale exports with domestic supply,
        as it might grow from zero to a finite value, which is an infinite relative
        growth. So we scale by the (hopefully non-zero) value which is given to the trade
        extrapolation (dom_demand in backwards mode).
        We call this trade which (due to a lack of domestic supply/demand) must be im- and
        directly exported again, "stopover_trade".
        There are two equal ways to calculate this stopover_trade:
        max(0, exports-dom_supply) or max(0, imports-dom_demand).
        (Their equality results from the mass balance)
        Since we treat this stopover_trade differently, we subtract it from the rest for
        future calculations, and add the separately scaled stopover_trade at the end again.
        """
        stopover_trade_0 = (self.historic_second_0 - self.scaler_second_0).maximum(0)
        self.historic_second_0[...] -= stopover_trade_0
        return stopover_trade_0 * first_scaling

    def scale_second(self, first_scaling: fd.FlodymArray, stopover_trade: fd.FlodymArray):
        """Scale "second" trade flow (exports in demand-driven mode)
        Scaled with the other domestic quantity than the first
        (exports with dom_supply, imports with dom_demand).
        But this depends on the second trade itself, via the mass balance, which results in
        a 2x2 equation system. We solve it with a fixed-point iteration.
        We start off by scaling it with the first scaler, calculate the second from the mass
        balance, and then re-calculate the scaler for the second trade flow, and so on.
        """
        self.future_second[...] = self.historic_second_0 * first_scaling
        self.future_second[self.id_hist] = self.historic_second
        for _ in range(1):
            self.scaler_second = (
                self.scaler_first - self.future_first + self.future_second + stopover_trade
            )
            updated_scaling = self.scaling(
                d0=self.scaler_second_0,
                d=self.scaler_second,
                alpha=self.alpha_rel,
            )
            self.future_second[...] = self.historic_second_0 * updated_scaling
            self.future_second[self.id_hist] = self.historic_second

        self.future_second[...] += stopover_trade
        self.future_second[self.id_hist] = self.historic_second

    def balance(self):
        """We balance global imports and exports to their hmean
        Balancing might result in a situation where imports exceed total demand or exports
        exceed total supply, which would lead to a negative flow on one side of the trade
        market. If this is the case, we scale down the trade flow which is too big.
        We then balance trades again, which might lead to the situation described above again,
        which is why we repeat the process iteratively until the excess is sufficiently small.
        """
        self.future_trade.balance(to="hmean")
        for i in range(10):
            scaler_second = self.scaler_first - self.future_first + self.future_second
            excess_trade = -(scaler_second.minimum(0.0))
            total_excess = excess_trade.sum_over("r")
            if np.max(total_excess.values) < 0.1:
                break
            self.future_first[...] -= excess_trade
            self.future_trade.balance(to="minimum")

        np.testing.assert_array_almost_equal(
            self.future_first.sum_over(
                "r",
            ).values,
            self.future_second.sum_over(
                "r",
            ).values,
            decimal=0,
        )

    @staticmethod
    def scaling(
        d0: fd.FlodymArray,
        d: fd.FlodymArray,
        alpha: float,
    ) -> fd.FlodymArray:
        """Apply scaling depending on relative change of scaler:
        - sub-linear scaling for _increasing_ scaler (i.e. increasing dom_demand or dom_supply)
          Rationale: for increasing dom_demand/dom_supply, we expect trade to increase less than
          proportionally, as there may be some inertia in historical trade patterns.
          Also low-gDP regions currently heavily relying on imports might increase their domestic
          supply share in the future.
        - linear scaling for _decreasing_ scaler
          (i.e. decreasing dom_demand or dom_supply)
          Rationale: for decreasing dom_demand/dom_supply, we expect trade to decrease at least
          proportionally, as there is less need/opportunity for trade. For increasing demand/dom_supply,
          we expect trade to increase less than proportionally, to protect domestic production.
          TODO: we could only apply linear scaling to future_first:
          - if domestic demand decreases, the standing production might export more
          - if domestic supply (e.g. of EOL material) decreases, more might be imported
        """
        assert np.min(d.values) >= -1e-6 * np.max(np.abs(d.values))
        assert np.min(d0.values) >= -1e-6 * np.max(np.abs(d0.values))
        d = d.maximum(0)
        d0 = d0.maximum(1)
        return ((d / d0) ** alpha).minimum(d / d0)


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
