from pydantic import model_validator
from remind_mfa.common.helpers import RemindMFABaseModel
from typing import List
from types import EllipsisType
import numpy as np
from scipy.stats import gmean, hmean
import sys
import flodym as fd


class Trade(RemindMFABaseModel):
    """A TradeModule handles the storing and calculation of trade data for a given MFASystem."""

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
    """A trade model for the steel sector storing the data and defining how trade is processed."""

    markets: dict[str, Trade]

    @classmethod
    def from_definitions(cls, definitions: List["TradeDefinition"], dims: fd.DimensionSet):
        markets = {}
        for d in definitions:
            markets[d.name] = Trade(
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
