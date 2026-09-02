import logging
import sys

import flodym as fd
import numpy as np
from pydantic import model_validator
from scipy.stats import gmean, hmean

from remind_mfa.common.helpers import RemindMFABaseModel


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

    def balance(self, to: str = "hmean"):
        global_imports = self.imports.sum_over("r")
        global_exports = self.exports.sum_over("r")

        reference_trade = self.get_reference_trade(global_imports, global_exports, to)
        reference_trade.apply(np.nan_to_num, inplace=True)

        import_factor = reference_trade / global_imports.maximum(sys.float_info.epsilon)
        export_factor = reference_trade / global_exports.maximum(sys.float_info.epsilon)

        new_imports = self.imports * import_factor
        new_exports = self.exports * export_factor

        self.imports[...] = new_imports
        self.exports[...] = new_exports

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
    def from_definitions(cls, definitions: list["TradeDefinition"], dims: fd.DimensionSet):
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


def set_trade_from_data(
    future_trade: Trade,
    imports: fd.FlodymArray,
    exports: fd.FlodymArray,
    historic_trade: Trade,
    balance_to: str | None = "hmean",
    market_name: str = "trade",
):
    """Set future trade from given data (e.g. the output of the ATLAS trade model) instead of
    extrapolating it from historic trade.

    Historic years are taken from ``historic_trade``, so the future MFA stays consistent with the
    historic one and does not jump at the transition (the same convention as
    :class:`TradeExtrapolator`). The data is only used for the future years.

    Args:
        future_trade: Future trade object to write into.
        imports: Import data over the full time dimension 't'.
        exports: Export data over the full time dimension 't'.
        historic_trade: Historic trade, used for the historic years.
        balance_to: Method to balance global imports and exports with, see
            :meth:`Trade.get_reference_trade`. None disables balancing.
        market_name: Name of the trade market.
    """
    future_trade.imports[...] = imports
    future_trade.exports[...] = exports

    historic_time = historic_trade.imports.dims["h"]
    _warn_uncovered_years(future_trade, historic_time, market_name)

    future_trade.imports[{"t": historic_time}] = historic_trade.imports
    future_trade.exports[{"t": historic_time}] = historic_trade.exports

    _warn_global_imbalance(future_trade, market_name)

    if balance_to is not None:
        future_trade.balance(to=balance_to)


def _warn_uncovered_years(future_trade: Trade, historic_time: fd.Dimension, market_name: str):
    """Warn about future years in which both imports and exports of the given data are zero.

    Might happen if the cs4r file as output by ATLAS does not cover all future years, in which case the reader will silently set the trade to zero in those years. This is usually not intended.
    """
    total = _global_values(future_trade.imports) + _global_values(future_trade.exports)
    uncovered = [
        year
        for year, value in zip(future_trade.imports.dims["t"].items, total)
        if year not in historic_time.items and value == 0.0
    ]
    if uncovered:
        logging.warning(
            f"'{market_name}': trade data is zero in {len(uncovered)} future year(s) "
            f"({uncovered[0]}-{uncovered[-1]}). These years are probably not covered by the data."
        )


def _warn_global_imbalance(future_trade: Trade, market_name: str, tolerance: float = 1e-3):
    """Warn if global imports and exports of the given trade data differ by more than `tolerance`
    (relative to the larger of the two).
    """
    global_imports = _global_values(future_trade.imports)
    global_exports = _global_values(future_trade.exports)
    scale = np.maximum(np.abs(global_imports), np.abs(global_exports))
    imbalance = np.abs(global_imports - global_exports) / np.maximum(scale, sys.float_info.epsilon)
    max_imbalance = np.max(imbalance)
    if max_imbalance > tolerance:
        year = future_trade.imports.dims["t"].items[int(np.argmax(imbalance))]
        logging.warning(
            f"'{market_name}': global imports and exports of the trade data differ by up to "
            f"{max_imbalance:.1%} (in {year}). They are balanced before use."
        )
    else:
        logging.info(
            f"'{market_name}': trade data is globally balanced within {max_imbalance:.2%}."
        )


def _global_values(array: fd.FlodymArray) -> np.ndarray:
    """Values of the given array summed over all dimensions but time, as a 1d numpy array."""
    return np.asarray(array.sum_to(("t",)).values, dtype=float)
