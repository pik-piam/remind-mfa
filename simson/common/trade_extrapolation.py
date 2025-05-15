import numpy as np
import flodym as fd

from simson.common.data_extrapolations import ProportionalExtrapolation
from simson.common.data_transformations import broadcast_trailing_dimensions
from simson.common.trade import Trade


def predict_by_extrapolation(
    historic_trade: Trade,
    future_trade: Trade,
    scaler: fd.FlodymArray,
    scale_first: str,
    balance_to: str = None,
):
    """
    Predict future trade values by extrapolating the trade data using a given scaler.
    :param trade: Trade object with historic trade data.
    :param scaler: NamedDimArray object with the scaler values.
    :param scale_first: str, either 'imports' or 'exports', indicating which trade values to scale first and
                        use as a scaler for the other trade values (scale_second).
    :param adopt_scaler_dims: bool, whether to adopt the dimensions of the scaler or use the ones of the trade data.
    :param balance_to: str, which method to use for balancing the future trade data. If None, no balancing is done.
    """

    # prepare prediction
    assert scale_first in ["imports", "exports"], "Scale by must be either 'imports' or 'exports'."
    assert (
        "h" in historic_trade.imports.dims.letters and "h" in historic_trade.exports.dims.letters
    ), "Trade data must have a historic time dimension."

    scale_second = "exports" if scale_first == "imports" else "imports"
    historic_first = getattr(historic_trade, scale_first)
    historic_second = getattr(historic_trade, scale_second)
    future_first = getattr(future_trade, scale_first)
    future_second = getattr(future_trade, scale_second)
    # TODO: make sure future_trade dims are a subset of the union of the dims of the scaler and the historic trade

    missing_dims = scaler.dims.difference_with(historic_trade.imports.dims).letters[1:]

    if len(missing_dims) > 0:
        with np.errstate(divide="ignore"):
            historic_first *= (
                scaler[{"t": historic_first.dims["h"]}]
                .get_shares_over(missing_dims)
                .apply(np.nan_to_num)
            )
            historic_second *= (
                scaler[{"t": historic_second.dims["h"]}]
                .get_shares_over(missing_dims)
                .apply(np.nan_to_num)
            )

    future_first[...] = extrapolate_to_future(historic=historic_first, scale_by=scaler)
    future_second[...] = 0.0

    # TODO: Ensure share < 1 already in extrapolation?
    scaler_second = (scaler + future_trade.net_imports).maximum(0)
    future_second[...] = extrapolate_to_future(historic=historic_second, scale_by=scaler_second)

    # balance
    if balance_to is not None:
        future_trade.balance(to=balance_to)


def extrapolate_to_future(historic: fd.FlodymArray, scale_by: fd.FlodymArray) -> fd.FlodymArray:
    """Uses the WeightedProportionalExtrapolation, basically a linear regression
    so that the share of the historic trade in the scaler is kept constant
    """
    if not historic.dims.letters[0] == "h":
        raise ValueError("First dimension of historic_parameter must be historic time.")
    if not scale_by.dims.letters[0] == "t":
        raise ValueError("First dimension of scaler must be time.")
    if not set(scale_by.dims.letters[1:]).issubset(historic.dims.letters[1:]):
        raise ValueError("Scaler dimensions must be subset of historic_parameter dimensions.")

    all_dims = historic.dims.union_with(scale_by.dims)
    dim_letters_out = ("t",) + historic.dims.letters[1:]
    dims_out = all_dims[dim_letters_out]

    scale_by = scale_by.cast_to(dims_out)

    # calculate weights
    n_hist_points = historic.dims.shape[0]
    n_last_points = 5
    weights_1d = np.maximum(0.0, np.arange(-n_hist_points, 0) + n_last_points + 1)
    weights_1d = weights_1d / weights_1d.sum()
    weights = broadcast_trailing_dimensions(weights_1d, historic.values)

    extrapolation = ProportionalExtrapolation(
        data_to_extrapolate=historic.values,
        target_range=scale_by.values,
        weights=weights,
        independent_dims=tuple(range(1, dims_out.ndim)),
    )
    extrapolated = fd.FlodymArray(dims=dims_out, values=extrapolation.extrapolate()).maximum(0.0)
    last_historic = historic[historic.dims["h"].items[-1]].maximum(0.0).cast_to(dims_out)
    alpha_rel = 0.5
    alpha_abs = 1 - alpha_rel
    projected = last_historic**alpha_abs * extrapolated**alpha_rel
    projected[{"t": historic.dims["h"]}] = historic

    return projected
