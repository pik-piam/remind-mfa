import sys
import logging
from copy import deepcopy
import numpy as np
import flodym as fd
from pydantic import model_validator, ConfigDict

from remind_mfa.common.data_transformations import broadcast_trailing_dimensions
from remind_mfa.common.trade import Trade
from remind_mfa.common.helpers import RemindMFABaseModel
from remind_mfa.common.data_blending import (
    blend,
    critically_damped_blend,
    DEFAULT_APPROACHING_TIME,
)
from remind_mfa.common.assumptions_doc import add_assumption_doc


class TradeExtrapolator(RemindMFABaseModel):
    """Predict future trade values by extrapolating the trade data using a given scaler."""

    model_config = ConfigDict(extra="allow")

    historical_trade: Trade
    """historical_trade (Trade): Historical trade data."""
    future_trade: Trade
    """future_trade (Trade): Future trade data, which is written to."""
    future_dom_supply: fd.FlodymArray = None
    """future_dom_supply (FlodymArray): The domestic supply values to scale the historical exports by.
    Setting this means calculating trade in forward mode
    """
    future_dom_demand: fd.FlodymArray = None
    """future_dom_demand (FlodymArray): The domestic demand values to scale the historical imports by.
    Setting this means calculating trade in backward mode
    """
    trade_factor: fd.FlodymArray | float = 1.0
    """trade_factor (FlodymArray | float): Scenario factor on the extrapolated trade. Must only
    contain dimensions of the future trade. Defaults to no scaling.
    The factor multiplies both import and export flows (including stopover trade) after they have
    been extrapolated and balanced without it. See :meth:`apply_trade_factor` for how the global
    balance is restored for factors that differ between regions.
    """
    _eps: float = 1e-6
    """Small value to avoid division by zero and to check for near-zero values in the data."""

    @model_validator(mode="after")
    def validate_inputs(self):
        if (self.future_dom_supply is None) == (self.future_dom_demand is None):
            raise ValueError("Exactly one of future_dom_supply or future_dom_demand must be set.")
        if "t" not in (self.future_dom_demand or self.future_dom_supply).dims.letters:
            raise ValueError("Future domestic demand or supply must have a (full) time dimension.")
        if "h" not in self.historical_trade.imports.dims:
            raise ValueError("Historical trade data must have a historical time dimension.")
        if "t" not in self.future_trade.imports.dims:
            raise ValueError("Future trade data must have a time dimension.")
        # all other dims must be the same
        if self.historical_trade.imports.dims.drop("h") != self.future_trade.imports.dims.drop("t"):
            raise ValueError(
                "Apart from time, historical and future trade data must have the same dimensions."
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
        self.historical_first = getattr(self.historical_trade, self.scaled_first)
        self.historical_second = getattr(self.historical_trade, self.scaled_second)
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
                "All future trade dimensions must be contained either in scaler or in historical trade."
            )

    def get_recent_averages(self):
        """Calculate weighted average across last few historical years for both imports and exports,
        and for the scaler. These are used as starting points/reference for the extrapolation, to
        avoid extrapolating from a single year which might be an outlier.
        """
        averager = RecentHistoricalAverage(dims=self.historical_first.dims)

        self.historical_first_0 = averager.apply(self.historical_first).cast_to(
            self.dims_out
        )  # * (1 - self.eps)
        self.historical_second_0 = averager.apply(self.historical_second).cast_to(
            self.dims_out
        )  # * (1 - self.eps)
        self.scaler_first_0 = averager.apply(self.scaler_first).cast_to(self.dims_out)
        scaler_second_hist = (
            self.scaler_first[{"t": self.historical_first.dims["h"]}]
            - self.historical_first
            + self.historical_second
        )
        self.scaler_second_0 = averager.apply(scaler_second_hist).cast_to(self.dims_out)

    def calc_trade(self):
        """The actual trade calculations"""

        self.id_hist = {"t": self.historical_first.dims["h"]}
        self.remove_stopover()
        self.scale_first()
        stopover_trade = self.add_stopover()
        self.scale_second(stopover_trade)
        self.blend_transition()
        self.future_trade.balance(to="hmean")
        self.apply_trade_factor()
        self.clip_excess_trade()

    def scale_first(self):
        # scale "first" trade flow (imports in demand-driven mode)
        self.future_first[...] = self.scaling(
            trd_0=self.historical_first_0,
            dom_0=self.scaler_first_0,
            dom=self.scaler_first,
        )
        # make sure historical years equal historical data
        self.future_first[self.id_hist] = self.historical_first

    def remove_stopover(self):
        """Split off "stopover" (re-export) trade before scaling.

        Sometimes trade exceeds domestic supply and demand. For example, a country could have
        zero production (i.e. all supply through imports), but still have some exports, because
        we bundle together trade across several stages along the manufacturing process. So it
        imports semi-finished products and exports finished products. In this case, it makes no
        sense to scale that pass-through trade with domestic supply/demand, as it might grow from
        zero to a finite value, which is an infinite relative growth.
        There are two equal ways to calculate this stopover_trade (equal by the mass balance):
        max(0, exports-dom_supply) or max(0, imports-dom_demand).

        The stopover is both imported and directly re-exported again, so it is subtracted from
        **both** the import and export bases here; the separately scaled stopover is added back to
        **both** future flows (see :meth:`add_stopover` and :meth:`scale_second`). Removing it from
        only one side would leave the other flow's local ratio and the global trade share inflated,
        making it over-grow relative to its domestic driver (which drives domestic supply/demand
        negative for heavy importers/re-exporters).
        """
        self.stopover_0 = (self.historical_second_0 - self.scaler_second_0).maximum(0)
        self.historical_first_0[...] -= self.stopover_0
        self.historical_second_0[...] -= self.stopover_0

    def add_stopover(self) -> fd.FlodymArray:
        """Scale the stopover (re-export) trade and add it to the (already scaled) future first
        flow. Returns the scaled stopover so :meth:`scale_second` adds it to the second flow as
        well, keeping the re-export balanced across both flows.

        Stopover is pass-through trade, decoupled from the transit region's own domestic driver,
        so - unlike :meth:`scale_first` - it is scaled by *global* scaler growth (region-
        independent, per end use).
        """
        global_scaler = self.scaler_first.sum_over("r")
        global_scaler_0 = self.scaler_first_0.sum_over("r").maximum(self._eps)
        stopover_trade = self.stopover_0 * (global_scaler / global_scaler_0)
        self.future_first[...] += stopover_trade
        self.future_first[self.id_hist] = self.historical_first
        return stopover_trade

    def scale_second(self, stopover_trade: fd.FlodymArray):
        """Scale "second" trade flow (exports in demand-driven mode)
        Scaled with the other domestic quantity than the first
        (exports with dom_supply, imports with dom_demand).
        But this depends on the second trade itself, via the mass balance, which results in
        a 2x2 equation system. We solve it with a fixed-point iteration starting from
        historical_second_0.
        """
        self.future_second[...] = self.historical_second_0
        self.future_second[self.id_hist] = self.historical_second
        for _ in range(3):
            self.scaler_second = (
                self.scaler_first - self.future_first + self.future_second + stopover_trade
            )
            self.future_second[...] = self.scaling(
                trd_0=self.historical_second_0,
                dom_0=self.scaler_second_0,
                dom=self.scaler_second,
                reduced_linear=False,
            )
            self.future_second[self.id_hist] = self.historical_second

        self.future_second[...] += stopover_trade
        self.future_second[self.id_hist] = self.historical_second

    def blend_transition(self):
        """Smooth the transition of both trade flows from historical to future years with a
        critically damped blend, before balancing. Negative values are set to zero.
        """
        n_historical = self.historical_first.dims["h"].len
        for future_flow in (self.future_first, self.future_second):
            future_flow[...] = critically_damped_blend(
                future_flow,
                n_historical=n_historical,
                approaching_time=DEFAULT_APPROACHING_TIME,
            ).maximum(0)
        add_assumption_doc(
            type="model assumption",
            name="Critically damped blend of extrapolated trade",
            value=DEFAULT_APPROACHING_TIME,
            description=(
                "Extrapolated imports and exports are blended smoothly from historical trends to the "
                "extrapolated values with a critically damped blend, before they are balanced. "
                "The value is the approaching time in years."
            ),
        )

    def apply_trade_factor(self):
        """Multiply the balanced trade flows with the scenario trade factor and restore the global
        balance.

        A factor that is uniform across regions keeps imports and exports balanced, so it acts
        exactly. A factor that differs between regions generally leaves global imports and exports
        unequal. Since trade requires both a buyer and a seller, the global trade is then limited
        to the smaller of both, and all flows of the larger side are scaled down proportionally.
        The factor is thus exact on the smaller side and an upper bound on the larger side.
        """
        for future_flow in (self.future_trade.imports, self.future_trade.exports):
            future_flow[...] = future_flow * self.trade_factor
        self.future_trade.balance(to="minimum")
        add_assumption_doc(
            type="model assumption",
            name="Balancing of scenario trade factor",
            description=(
                "The scenario trade factor multiplies extrapolated and balanced imports and "
                "exports. If it differs between regions, global trade is limited to the smaller "
                "of global imports and exports, and the larger side is scaled down "
                "proportionally across all regions."
            ),
        )

    def clip_excess_trade(self):
        """Balancing might result in a situation where imports exceed total demand or exports
        exceed total supply, which would lead to a negative flow on one side of the trade
        market. If this is the case, we scale down the trade flow which is too big.
        We then balance trades again, which might lead to excess trade in further regions,
        which is why we repeat the process iteratively until the excess is sufficiently small.
        """
        max_value = self.scaler_first.values.max()
        epsilon = np.finfo(self.scaler_first.values.dtype).eps
        tolerance = epsilon * max_value * 10
        for i in range(50):
            scaler_second = self.scaler_first - self.future_first + self.future_second
            excess_trade = -(scaler_second.minimum(0.0))
            if excess_trade.values.max() < tolerance:
                break
            # Clamp such that future_first stays non-negative to avoid divergence.
            # Negative values here only occur if scaler_first or future_second are negative,
            # e.g. due to previous tolerances,
            excess_trade = excess_trade.minimum(self.future_first)
            self.future_first[...] = self.future_first - excess_trade

            # only scale the items without excess trade,
            # otherwise we would create new excess trade by scaling down the opposite flows
            scaled = excess_trade.cast_values_to(self.future_first.dims) == 0
            self.future_trade.balance(to="minimum", mask_scaled=scaled)

        assert np.allclose(
            self.future_first.sum_over(
                "r",
            ).values,
            self.future_second.sum_over(
                "r",
            ).values,
            rtol=epsilon * 10,
        )

    def scaling(
        self,
        trd_0: fd.FlodymArray,
        dom_0: fd.FlodymArray,
        dom: fd.FlodymArray,
        reduced_linear: bool = True,
    ) -> fd.FlodymArray:
        """Apply scaling depending on relative change of scaler:
        Base method:
        - linear scaling (exports with production, imports with demand), constant local trade shares
        Modifications:
        - for large relative increases of the scaler, global trade shares (e/p an i/d) slowly
          replace local ones, as such large changes diminish the predictive power of local
          historical trade patterns. Phase-in of global shares is governed by the alpha parameter
        - no scaling for decreasing scaler in future_second
          Rationale:
          - if domestic demand decreases, the standing production might export more
          - if domestic supply (e.g. of EOL material) decreases, more might be imported
        """
        assert np.min(dom.values) >= -1e-6 * np.max(np.abs(dom.values))
        assert np.min(dom_0.values) >= -1e-6 * np.max(np.abs(dom_0.values))
        trd_0 = trd_0.maximum(0)
        dom = dom.maximum(0)
        dom_0 = dom_0.maximum(1)
        dom_ratio = (dom / dom_0).maximum(1).apply(np.log) / np.log(50)
        alpha = blend(
            target_dims=self.dims_out,
            y_lower=0,
            y_upper=1,
            x=dom_ratio,
            x_lower=0,
            x_upper=1,
            type="quintic",
        )
        trd_share_glob_0 = (trd_0.sum_over(("r",)) / dom_0.sum_over(("r",))).cast_to(self.dims_out)
        trd = dom * (trd_0 / dom_0) ** (1 - alpha) * trd_share_glob_0**alpha

        if reduced_linear:
            return trd
        else:
            return trd.maximum(trd_0)


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
            raise ValueError("First dimension of dims must be historical time 'h'.")
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


class FixedSupplyTradeExtrapolator(RemindMFABaseModel):
    """Trade extrapolation for a scenario where one region's domestic supply is fixed to
    the baseline scenario (e.g. EUR supply locked to REMIND-MFA baseline).

    Any change in demand relative to baseline is absorbed by trade:
    - ``import_adjustment_share`` (alpha) fraction via increased/decreased imports
    - ``(1 - alpha)`` fraction via decreased/increased exports

    Mass balance for the fixed-supply region:
        supply_fixed + imports_new = demand_new + exports_new
    with delta = demand_new - demand_baseline:
        imports_new  = imports_baseline + alpha * delta
        exports_new  = exports_baseline - (1 - alpha) * delta

    All other regions keep their baseline future trade unchanged; global trade is
    re-balanced after the EUR adjustment.
    """

    historic_trade: Trade
    """Historic trade data, used to keep historic trade in historic years."""
    baseline_future_trade: Trade
    """Trade computed by the regular TradeExtrapolator using baseline (REMIND-MFA) demand."""
    default_future_trade: Trade
    """Trade computed by the regular TradeExtrapolator using the new (scenario) demand.
    Used wherever the fixed-supply region's demand exceeds the baseline, since fixing
    supply there is not defensible (the region would import demand it could produce)."""
    future_trade: Trade
    """Future trade object to write results into."""
    baseline_dom_demand: fd.FlodymArray
    """Baseline domestic demand for all regions (dims must include 't' and 'r')."""
    future_dom_demand: fd.FlodymArray
    """New domestic demand for all regions (EU-MFA for fixed-supply region, same as
    baseline for others). Must have the same dims as baseline_dom_demand."""
    import_adjustment_share: float = 0.5
    """Fraction of demand delta absorbed by imports. 0 = only exports adjust, 1 = only imports adjust."""
    fixed_supply_region: str = "EUR"
    """Label of the region whose supply is fixed to the baseline."""

    @model_validator(mode="after")
    def validate_inputs(self):
        if not 0.0 <= self.import_adjustment_share <= 1.0:
            raise ValueError("import_adjustment_share must be between 0 and 1.")
        if "t" not in self.baseline_dom_demand.dims.letters:
            raise ValueError("baseline_dom_demand must have a time dimension 't'.")
        if self.baseline_dom_demand.dims != self.future_dom_demand.dims:
            raise ValueError("baseline_dom_demand and future_dom_demand must have the same dims.")
        if self.default_future_trade.imports.dims != self.future_trade.imports.dims:
            raise ValueError("default_future_trade and future_trade must have the same dims.")
        if self.fixed_supply_region not in self.future_trade.imports.dims["r"].items:
            raise ValueError(
                f"fixed_supply_region '{self.fixed_supply_region}' not found in region dimension."
            )
        return self

    def run(self):
        """Compute future trade with fixed supply for the target region.

        Where the fixed-supply region's demand drops below baseline (delta <= 0), the
        region keeps its baseline supply and absorbs the demand change via trade.
        Where demand rises above baseline (delta > 0), fixing supply would force the
        region to import demand it could simply produce, which is hard to justify; there
        we fall back to the default extrapolation (supply grows with demand). At delta = 0
        both candidates equal the baseline trade, so a hard switch introduces no kink.
        Both candidate trades are globally balanced and the switch weight depends only on
        the fixed-region delta (constant over r), so the blended result stays balanced.
        """
        alpha = self.import_adjustment_share
        r = self.fixed_supply_region

        # start from baseline trade for all regions
        self.future_trade.imports[...] = self.baseline_future_trade.imports
        self.future_trade.exports[...] = self.baseline_future_trade.exports

        # demand delta for the fixed-supply region
        delta = self.future_dom_demand - self.baseline_dom_demand
        delta_r = delta[{"r": r}]

        # Step 1: apply trade adjustment for fixed-supply region
        self.future_trade.imports[{"r": r}] = (
            self.baseline_future_trade.imports[{"r": r}] + alpha * delta_r
        )
        self.future_trade.exports[{"r": r}] = (
            self.baseline_future_trade.exports[{"r": r}] - (1.0 - alpha) * delta_r
        )

        # Step 2: balance trade by adjusting only non-EUR regions
        #
        # eu_import_origin_shares: each non-EUR region's share of non-EUR exports.
        # Approximates where EUR imports originate (who exports to EUR).
        non_eur_exports = deepcopy(self.baseline_future_trade.exports)
        non_eur_exports[{"r": r}] = 0.0
        eu_import_origin_shares = non_eur_exports.get_shares_over("r")
        eu_import_origin_shares.values[np.isnan(eu_import_origin_shares.values)] = 0.0

        # eu_export_destination_shares: each non-EUR region's share of non-EUR imports.
        # Approximates where EUR exports are destined (who imports from EUR).
        non_eur_imports = deepcopy(self.baseline_future_trade.imports)
        non_eur_imports[{"r": r}] = 0.0
        eu_export_destination_shares = non_eur_imports.get_shares_over("r")
        eu_export_destination_shares.values[np.isnan(eu_export_destination_shares.values)] = 0.0

        # EUR imports increase by alpha*delta_r  → non-EUR regions export more (to supply EUR)
        # EUR exports decrease by (1-alpha)*delta_r → non-EUR regions import less (less supply from EUR)
        # The EUR slice has zero share in both share arrays, so only non-EUR is affected.
        self.future_trade.exports[...] += eu_import_origin_shares * alpha * delta_r
        self.future_trade.imports[...] -= eu_export_destination_shares * (1.0 - alpha) * delta_r

        # Step 3: where the fixed-supply region's demand exceeds baseline (delta > 0),
        # use the default extrapolation instead of the fixed-supply construction.
        # use_default is 1 where delta_r > 0 and 0 otherwise; it depends only on the
        # fixed-region delta (broadcast over r), so blending two globally-balanced trades
        # keeps the global balance intact.
        # The demand may carry dimensions the trade lacks (e.g. element 'e'); sum the delta
        # down to the net mass delta over the shared dims *before* taking the sign.
        common_letters = delta_r.dims.intersect_with(self.future_trade.imports.dims).letters
        delta_r_cast = delta_r.sum_to(common_letters).cast_to(self.future_trade.imports.dims)
        use_default = fd.FlodymArray(
            dims=self.future_trade.imports.dims,
            values=(delta_r_cast.values > 0.0).astype(float),
        )
        self.future_trade.imports[...] = (
            1.0 - use_default
        ) * self.future_trade.imports + use_default * self.default_future_trade.imports
        self.future_trade.exports[...] = (
            1.0 - use_default
        ) * self.future_trade.exports + use_default * self.default_future_trade.exports

        self.future_trade.exports[{"t": self.historic_trade.exports.dims["h"]}] = (
            self.historic_trade.exports
        )
        self.future_trade.imports[{"t": self.historic_trade.imports.dims["h"]}] = (
            self.historic_trade.imports
        )

        logging.info(
            f"FixedSupplyTradeExtrapolator: supply of '{r}' fixed to baseline. "
            f"import_adjustment_share={alpha}. "
            f"Mean demand delta for '{r}': {delta_r.values.mean():.2f}"
        )


class OpenGemTradeAligner(RemindMFABaseModel):
    """Align the future trade of one region to the relative change of trade ratios from OPEN-GEM.

    OPEN-GEM reports trade in monetary terms with a sector scope that does not match the goods of
    the MFA 1:1, and the material intensity of the economic value can change. Therefore, the
    monetary trade is not converted into tonnes. Instead, the region's trade ratios (imports and
    exports over the driver of the trade, i.e. domestic demand or domestic supply) follow the
    relative change of the OPEN-GEM ratios from the base year t0 on:

        I(t) = D(t) * I_0 / D_0 * rho_I(t) / rho_I(t0)
        E(t) = D(t) * E_0 / D_0 * rho_E(t) / rho_E(t0)

    where I_0, E_0 and D_0 are the region's trade and driver in t0 as given in ``trade`` (e.g. as
    extrapolated) and rho are the OPEN-GEM ratios. The other regions absorb the change of the
    region's trade, proportionally to their exports (for a change of the region's imports) and
    their imports (for a change of its exports), which keeps the global trade balanced.
    Years before t0 are not changed.
    """

    trade: Trade
    """Trade to align. Must be globally balanced. Overwritten in place."""
    imports_ratio: fd.FlodymArray
    """OPEN-GEM ratio of imports to the trade driver. Only its relative change is used."""
    exports_ratio: fd.FlodymArray
    """OPEN-GEM ratio of exports to the trade driver. Only its relative change is used."""
    dom_demand: fd.FlodymArray | None = None
    """Domestic demand, the driver of demand-driven trade (e.g. manufactured products)."""
    dom_supply: fd.FlodymArray | None = None
    """Domestic supply, the driver of supply-driven trade (e.g. collected scrap)."""
    base_year: int
    """Year t0 from which on the trade ratios follow OPEN-GEM."""
    region: str = "EUR"
    """Label of the region whose trade is aligned."""
    _eps: float = 1e-9
    """Threshold below which drivers and trade sums are treated as zero."""

    @model_validator(mode="after")
    def validate_inputs(self):
        if (self.dom_supply is None) == (self.dom_demand is None):
            raise ValueError("Exactly one of dom_supply or dom_demand must be set.")
        dims = self.trade.imports.dims
        if self.region not in dims["r"].items:
            raise ValueError(f"Region '{self.region}' not found in region dimension.")
        if self.base_year not in dims["t"].items:
            raise ValueError(f"Base year {self.base_year} not found in time dimension.")
        return self

    def run(self):
        region = {"r": self.region}
        demand_driven = self.dom_demand is not None
        driver = self._cast(self.dom_demand if demand_driven else self.dom_supply)
        future = self._future_mask()

        imports_old = self.trade.imports[region].copy()
        exports_old = self.trade.exports[region].copy()
        driver_r = driver[region]

        # trade ratios of the region in the base year, following the change of the OPEN-GEM ratios
        driver_0 = driver_r[{"t": self.base_year}].maximum(self._eps)
        a = self._index(self.imports_ratio) * (imports_old[{"t": self.base_year}] / driver_0)
        b = self._index(self.exports_ratio) * (exports_old[{"t": self.base_year}] / driver_0)
        if demand_driven:
            # net imports must not exceed demand, otherwise domestic production would be negative
            a = a.minimum(b + 1.0)
        else:
            # net exports must not exceed supply, otherwise domestic use would be negative
            b = b.minimum(a + 1.0)

        delta_imports_target = (a * driver_r - imports_old) * future
        delta_exports_target = (b * driver_r - exports_old) * future

        # the other regions absorb the change proportionally to their trade: a change of the
        # region's imports by their exports, a change of its exports by their imports
        exports_others = self.trade.exports.sum_over("r") - exports_old
        imports_others = self.trade.imports.sum_over("r") - imports_old
        delta_imports = delta_imports_target * self._positive(exports_others)
        delta_exports = delta_exports_target * self._positive(imports_others)
        self._warn_not_absorbable(delta_imports, delta_imports_target)
        self._warn_not_absorbable(delta_exports, delta_exports_target)
        factor_exports = delta_imports / exports_others.maximum(self._eps) + 1.0
        factor_imports = delta_exports / imports_others.maximum(self._eps) + 1.0
        n_clipped = np.sum(factor_exports.values < 0.0) + np.sum(factor_imports.values < 0.0)

        self.trade.exports[...] = self.trade.exports * factor_exports.maximum(0.0)
        self.trade.imports[...] = self.trade.imports * factor_imports.maximum(0.0)
        self.trade.imports[region] = imports_old + delta_imports
        self.trade.exports[region] = exports_old + delta_exports

        # only the other regions' future trade is adjusted from here on
        others = fd.FlodymArray(dims=self.trade.imports.dims["r",])
        others[...] = 1.0
        others[region] = 0.0
        scalable = future * others
        if n_clipped:
            logging.warning(
                f"OPEN-GEM trade alignment of '{self.trade.name}': the decrease of the other "
                f"regions' trade exceeds their trade in {n_clipped} entries. Their trade is set to "
                "zero there and the other regions are rebalanced."
            )
            self.trade.balance(to="minimum", mask_scaled=self._mask(scalable))
        self._clip_excess_trade(driver, demand_driven, scalable)

        self._log_change(imports_old, exports_old)
        add_assumption_doc(
            type="model assumption",
            name="Alignment of EU trade to OPEN-GEM",
            value=str(self.base_year),
            description=(
                f"From the given year on, the ratios of {self.region} imports and exports of "
                "manufactured products to domestic demand, and of steel scrap to domestic "
                "supply, follow the relative change of the corresponding ratios of the OPEN-GEM "
                "model. The other regions absorb the change proportionally to their trade."
            ),
        )

    def _clip_excess_trade(
        self, driver: fd.FlodymArray, demand_driven: bool, scalable: fd.FlodymArray
    ):
        """Reduce trade that makes the other regions' domestic production (demand-driven trade)
        or domestic use (supply-driven trade) negative, and rebalance with the remaining other
        regions, as in :meth:`TradeExtrapolator.clip_excess_trade`.

        The other regions' imports (demand-driven) or exports (supply-driven) can grow beyond
        what their driver allows when they absorb the region's trade change. The aligned region
        and years before t0 are not changed.

        Args:
            driver: Driver of the trade, with the trade dimensions.
            demand_driven: Whether the trade is demand-driven.
            scalable: 1 for the (time, region) entries that may be changed, 0 otherwise.
        """
        if demand_driven:
            first, second = self.trade.imports, self.trade.exports
        else:
            first, second = self.trade.exports, self.trade.imports
        tolerance = 10 * np.finfo(float).eps * max(driver.abs().values.max(), 1.0)
        for _ in range(50):
            excess = (first - second - driver).maximum(0.0) * scalable
            if excess.values.max() < tolerance:
                break
            excess = excess.minimum(first)
            first[...] = first - excess
            no_excess = excess.cast_values_to(first.dims) == 0.0
            self.trade.balance(to="minimum", mask_scaled=self._mask(scalable) & no_excess)
        else:
            logging.warning(
                f"OPEN-GEM trade alignment of '{self.trade.name}': clipping excess trade of the "
                "other regions did not converge after 50 iterations."
            )

    def _cast(self, array: fd.FlodymArray) -> fd.FlodymArray:
        """Sum over dims not in the trade, broadcast to the trade dims."""
        dims_out = self.trade.imports.dims
        common_dims = array.dims.intersect_with(dims_out)
        return array.sum_to(common_dims.letters).cast_to(dims_out)

    def _future_mask(self) -> fd.FlodymArray:
        """1 from the base year on, 0 before."""
        time = self.trade.imports.dims["t"]
        return fd.FlodymArray(
            dims=self.trade.imports.dims["t",],
            values=(np.array(time.items) >= self.base_year).astype(float),
        )

    def _index(self, ratio: fd.FlodymArray) -> fd.FlodymArray:
        """Change of the region's ratio relative to the base year; 1 where the ratio is zero or
        not finite in the base year."""
        ratio_r = self._cast(ratio)[{"r": self.region}].apply(np.nan_to_num)
        ratio_0 = ratio_r[{"t": self.base_year}]
        valid = self._positive(ratio_0)
        # cast before adding, since + reduces both operands to their common dims
        return ratio_r / ratio_0.maximum(self._eps) * valid + (1.0 - valid).cast_to(ratio_r.dims)

    def _positive(self, array: fd.FlodymArray) -> fd.FlodymArray:
        """1 where the array exceeds the zero threshold, 0 otherwise."""
        return array.apply(lambda values: (values > self._eps).astype(float))

    def _mask(self, array: fd.FlodymArray) -> np.ndarray:
        """Boolean mask with the trade dims where the array is non-zero, for `Trade.balance`."""
        return array.cast_values_to(self.trade.imports.dims) != 0.0

    def _warn_not_absorbable(self, delta: fd.FlodymArray, delta_target: fd.FlodymArray):
        n_lost = np.sum(delta.values != delta_target.values)
        if n_lost:
            logging.warning(
                f"OPEN-GEM trade alignment of '{self.trade.name}': {n_lost} entries cannot be "
                "absorbed by the other regions, since they have no trade there. Trade is not "
                "aligned in these entries."
            )

    def _log_change(self, imports_old: fd.FlodymArray, exports_old: fd.FlodymArray):
        last = {"t": self.trade.imports.dims["t"].items[-1]}
        region = {"r": self.region}
        logging.info(
            f"OPEN-GEM trade alignment of '{self.trade.name}' in {last['t']}: {self.region} "
            f"imports {imports_old[last].values.sum():.4g} -> "
            f"{self.trade.imports[region][last].values.sum():.4g}, "
            f"exports {exports_old[last].values.sum():.4g} -> "
            f"{self.trade.exports[region][last].values.sum():.4g}"
        )
