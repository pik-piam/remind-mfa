import numpy as np
import flodym as fd
from pydantic import ConfigDict, model_validator

from remind_mfa.common.helper import RemindMFABaseModel


class PriceDrivenTrade(RemindMFABaseModel):

    model_config = ConfigDict(extra="allow")

    eta_demand: float = -0.3
    eta_supply: float = 1.2
    mu: float = 0.012
    """OOM: 1/price; Higher mu means more price-elastic"""
    learning_rate: float = 0.2
    convergence_tol: float = 0.01
    max_iter: int = 1000
    dims: fd.DimensionSet

    @model_validator(mode="after")
    def add_prms(self):
        self.n_regi = self.dims["r"].len
        self.source_region = fd.Dimension(letter="R", name="region2", items=self.dims["r"].items)
        self.all_dims = self.dims.expand_by([self.source_region])
        self.domestic_preference = None
        self.export_penalty = None
        return self

    def compute_price_driven_trade(
        self,
        price_0: fd.FlodymArray,
        demand_0: fd.FlodymArray,
        supply_0: fd.FlodymArray,
    ):

        # scalar parameters:

        if self.domestic_preference is None:
            raise RuntimeError("Domestic preference not set. Call calibrate first.")

        # init values: multiplication makes a copy
        price = 1.0 * price_0
        supply = 1.0 * supply_0
        demand = 1.0 * demand_0

        for i in range(self.max_iter):

            # demand and supply
            demand = demand_0 * (price / price_0) ** self.eta_demand
            supply = supply_0 * (price / price_0) ** self.eta_supply

            imports, exports = self.get_trade(price, demand)

            # adjust price
            supply_target = demand + exports - imports
            price_factor = (supply_target / supply) ** (1 / self.eta_supply)
            price *= price_factor**self.learning_rate

            # check convergence
            excess = supply - supply_target
            max_error = np.max(np.abs(excess.values)) / np.max(np.abs(supply_target.values))
            if max_error < self.convergence_tol:
                return price, demand, supply, imports, exports

        raise RuntimeError("Could not converge to a solution for the price driven trade.")

    def calibrate(
        self,
        demand: fd.FlodymArray,
        price: fd.FlodymArray,
        imports_target: fd.FlodymArray,
        exports_target: fd.FlodymArray,
    ):

        self.export_penalty = fd.FlodymArray(dims=self.all_dims["r",])
        self.export_penalty[...] = 1.0
        self.domestic_preference = fd.FlodymArray(dims=self.all_dims["r",])
        self.domestic_preference[...] = 1.0

        export_shares_target = exports_target.get_shares_over("r")
        domestic_share_target = (demand - imports_target) / demand

        for i in range(self.max_iter):

            # update trade
            imports, exports = self.get_trade(price, demand)

            # update export penalty
            export_shares = exports.get_shares_over("r")
            export_penalty_diff = (export_shares / export_shares_target).apply(np.log) / (
                self.mu * price * self.domestic_preference
            )
            self.export_penalty += self.learning_rate * export_penalty_diff
            # normalize to avoid run-off
            self.export_penalty += 1.0 - self.export_penalty.values.min()

            # update domestic preference
            domestic_share = (demand - imports) / demand
            domestic_preference_diff = (domestic_share / domestic_share_target).apply(np.log) / (
                self.mu * price * self.export_penalty
            )
            self.domestic_preference += self.learning_rate * domestic_preference_diff

            if self.almost_zero(export_penalty_diff) and self.almost_zero(domestic_preference_diff):
                return

        raise RuntimeError(
            "Could not converge to a solution for the export penalty and domestic preference."
        )

    def almost_zero(self, array: fd.FlodymArray) -> bool:
        return max(abs(array.values)) < self.convergence_tol

    def get_trade(
        self, price: fd.FlodymArray, demand: fd.FlodymArray
    ) -> tuple[fd.FlodymArray, fd.FlodymArray]:
        dims = self.all_dims[
            (
                "R",
                "r",
            )
            + tuple(l for l in price.dims.letters if l != "r")
        ]
        trade = fd.FlodymArray(dims=dims)
        trade[...] = self.origin_shares(price) * demand
        diag_indices = np.diag_indices(self.n_regi) + (slice(None),) * (trade.dims.ndim - 2)
        trade.values[diag_indices] = 0.0
        imports = trade.sum_over("R")
        exports = trade.sum_over("r")[{"R": self.dims["r"]}]
        return imports, exports

    def origin_shares(self, price: fd.FlodymArray) -> fd.FlodymArray:
        local_price = (
            self.price_cast(price) * self.export_penalty_cast() * self.domestic_preference_cast()
        )
        return (-self.mu * local_price).apply(np.exp).get_shares_over("R")

    def price_cast(self, price: fd.FlodymArray) -> fd.FlodymArray:
        dims = self.all_dims[("R", "r") + tuple(l for l in price.dims.letters if l != "r")]
        return price[{"r": self.source_region}].cast_to(dims)

    def export_penalty_cast(self) -> fd.FlodymArray:
        cast_out = self.export_penalty[{"r": self.source_region}].cast_to(self.all_dims["R", "r"])
        cast_out.values[np.diag_indices(self.n_regi)] = 1.0
        return cast_out

    def domestic_preference_cast(self) -> fd.FlodymArray:
        cast_out = fd.FlodymArray(dims=self.all_dims["R", "r"])
        cast_out[...] = 1.0
        cast_out.values[np.diag_indices(self.n_regi)] = self.domestic_preference.values
        return cast_out
