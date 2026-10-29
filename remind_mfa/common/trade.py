import logging
from pydantic import model_validator
from remind_mfa.common.helpers import RemindMFABaseModel
from typing import List, Literal
from types import EllipsisType
import numpy as np
from scipy.stats import gmean, hmean
import sys
import flodym as fd


class Trade(RemindMFABaseModel):
    """A TradeModule handles the storing and calculation of trade data for a given MFASystem."""

    name: str = ""
    imports: fd.FlodymArray
    exports: fd.FlodymArray

    @model_validator(mode="after")
    def validate_region_dimension(self):
        assert "r" in self.imports.dims.letters, "Imports must have a Region dimension."
        assert "r" in self.exports.dims.letters, "Exports must have a Region dimension."

        return self

    @model_validator(mode="after")
    def validate_trade_dimensions(self):
        assert (
            self.imports.dims.letters == self.exports.dims.letters
        ), "Imports and exports must have the same dimensions."
        return self

    @property
    def net_imports(self):
        return self.imports - self.exports

    @property
    def net_exports(self):
        return self.exports - self.imports

    def sum_over(self, dim_letters: str | tuple) -> "Trade":
        """Return a copy of this trade with the given dimension(s) summed away.

        Used to hand a trade over to a system that resolves fewer dimensions, e.g. the historical
        plastics trade (which carries the polymer type 'P') to the future MFA system (which does
        not, since 'P' is redundant with the polymer dimension 'p').
        """
        return Trade(
            name=self.name,
            imports=self.imports.sum_over(dim_letters),
            exports=self.exports.sum_over(dim_letters),
        )

    def balance(self, to: str = "hmean", mask_scaled: EllipsisType | np.ndarray = Ellipsis):
        """
        Balances the trade data to ensure that the global imports and exports are consistent.
        (Market clearing, i.e. global imports = global exports.)

        Args:
            to (str, optional): The method to use for calculating the reference trade from imports and exports. Defaults to "hmean".
            mask_scaled (np.ndarray, optional): A boolean mask indicating which elements to scale. Ellipsis (default) means all elements are scaled.
        """

        global_imports = self.imports.sum_over("r")
        global_exports = self.exports.sum_over("r")

        reference_trade = self.get_reference_trade(global_imports, global_exports, to)
        reference_trade.apply(np.nan_to_num, inplace=True)

        for flow in [self.imports, self.exports]:
            global_actual = flow.sum_over("r")
            global_target = reference_trade.copy()

            if mask_scaled is not Ellipsis:
                # subtract the value of some fixed items from both targets and actuals,
                # then scale the remaining items to meet the target

                fixed = flow.copy()
                fixed.values[mask_scaled] = 0.0
                global_fixed = fixed.sum_over("r")

                global_target = global_target - global_fixed
                global_actual = global_actual - global_fixed

            flow_factor = global_target / global_actual.maximum(sys.float_info.epsilon)

            new_flow = flow * flow_factor
            flow.values[mask_scaled] = new_flow.values[mask_scaled]

    def cap_net(
        self,
        limit: fd.FlodymArray,
        direction: Literal["imports", "exports"],
        tolerance: float,
    ) -> tuple[fd.FlodymArray, fd.FlodymArray]:
        """Cap the positive net flow in ``direction`` at ``limit`` and re-balance globally.

        Where the net flow exceeds the limit, the capped side is reduced, keeping the opposite
        side (same-good stop-over trade) untouched. Global imports and exports are then balanced
        to their minimum by scaling only the items without excess. This raises the net flow of
        some of them, which may now exceed their limit as well, so capping and balancing are
        iterated until no excess above ``tolerance`` remains.

        Net trade and limit are compared on the dimensions they share. The trade may be more
        granular than the limit (e.g. per-end use indirect exports vs. total manufacturing supply)
        or coarser (e.g. aggregate scrap exports vs. per-end use recovered scrap), so both are
        summed to their common dimensions before capping.

        Args:
            limit (fd.FlodymArray): Upper bound of the positive net flow.
            direction (Literal["imports", "exports"]): Trade side whose net flow is capped.
            tolerance (float): Absolute excess up to which the cap counts as satisfied.

        Returns:
            tuple[fd.FlodymArray, fd.FlodymArray]: Excess over the limit and positive net flow,
                both before capping and on the common dimensions.
        """
        eps = sys.float_info.epsilon
        if direction == "exports":
            capped_flow, opposite_flow = self.exports, self.imports
        else:
            capped_flow, opposite_flow = self.imports, self.exports
        common_dims = tuple(
            letter for letter in capped_flow.dims.letters if letter in limit.dims.letters
        )
        limit_total = limit.sum_to(common_dims).maximum(0)
        for iteration in range(50):
            net_flow = (capped_flow - opposite_flow).maximum(0)
            net_flow_total = net_flow.sum_to(common_dims)
            # sum of positive per-end use net trade may not exceed the limit
            net_flow_excess = (net_flow_total - limit_total).maximum(0)
            if iteration == 0:
                initial_excess, initial_net_flow_total = net_flow_excess, net_flow_total
            if not (net_flow_excess.values > tolerance).any():
                break
            # reduce the capped flow of net-trade goods to bring positive net trade down to the
            # limit; factor in [0, 1]
            factor = (net_flow_total - net_flow_excess) / net_flow_total.maximum(eps)
            capped_flow[...] = capped_flow - net_flow * (1 - factor)

            scaled = net_flow_excess.cast_values_to(capped_flow.dims) == 0
            self.balance(to="minimum", mask_scaled=scaled)
        else:
            logging.warning(
                f"'{self.name or 'trade'}': positive-net-{direction} cap did not converge after "
                "50 iterations."
            )
        return initial_excess, initial_net_flow_total

    @staticmethod
    def get_reference_trade(
        global_imports: fd.FlodymArray, global_exports: fd.FlodymArray, to: str = "hmean"
    ):
        if to == "maximum":
            return global_imports.maximum(global_exports)
        elif to == "minimum":
            return global_imports.minimum(global_exports)
        elif to == "imports":
            return global_imports
        elif to == "exports":
            return global_exports
        elif to == "hmean":
            # this is the same method as referenced in Michaja's paper
            return fd.FlodymArray(
                dims=global_exports.dims,
                values=hmean(np.stack([global_imports.values, global_exports.values])),
            )
        elif to == "gmean":
            return fd.FlodymArray(
                dims=global_exports.dims,
                values=gmean(np.stack([global_imports.values, global_exports.values])),
            )
        elif to == "amean":
            return (global_imports + global_exports) / 2
        else:
            raise ValueError(
                f"Can't balance to '{to}', method not recognized. Must be one of"
                "'maximum', 'minimum', 'imports', 'exports', 'hmean', 'gmean', 'amean'."
            )


class TradeSet(RemindMFABaseModel):
    """A trade model storing the data and defining how trade is processed."""

    markets: dict[str, Trade]

    @classmethod
    def from_definitions(cls, definitions: List["TradeDefinition"], dims: fd.DimensionSet):
        markets = {}
        for d in definitions:
            markets[d.name] = Trade(
                name=d.name,
                imports=fd.FlodymArray(dims=dims[d.dim_letters]),
                exports=fd.FlodymArray(dims=dims[d.dim_letters]),
            )
        return cls(markets=markets)

    def __getitem__(self, item):
        return self.markets[item]

    def __setitem__(self, key: str, value: Trade):
        if not isinstance(value, Trade):
            raise ValueError("TradeSet can only store Trade objects.")
        if key not in self.markets:
            raise ValueError(
                f"TradeSet does not have a trade named {key}. You can add new trades using trade.markets[key] = value."
            )
        if self.markets[key].imports.dims.letters != value.imports.dims.letters:
            raise ValueError(
                f"Trade dimensions do not match. Expected {self.markets[key].imports.dims.letters}, got {value.imports.dims.letters}."
            )
        self.markets[key] = value

    def balance(self, to: str = None):
        for trade in self.markets.values():
            trade.balance(to=to) if to is not None else trade.balance()


class TradeDefinition(fd.ParameterDefinition):
    pass
