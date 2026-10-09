"""Tests for the scenario trade factor in `remind_mfa.common.trade_extrapolation`."""

import numpy as np
import flodym as fd
import pytest

from remind_mfa.common.trade import Trade
from remind_mfa.common.trade_extrapolation import TradeExtrapolator

H = fd.Dimension(name="Historic Time", letter="h", items=list(range(2000, 2006)))
T = fd.Dimension(name="Time", letter="t", items=list(range(2000, 2011)))
R = fd.Dimension(name="Region", letter="r", items=["A", "B", "C"])
DIMS = fd.DimensionSet(dim_list=[H, T, R])


def run_extrapolation(trade_factor: fd.FlodymArray | float) -> Trade:
    """Run a demand-driven trade extrapolation on a small synthetic case.

    Args:
        trade_factor: Scenario trade factor passed to the extrapolator.

    Returns:
        The extrapolated future trade.
    """
    demand = fd.FlodymArray(dims=DIMS["t", "r"])
    growth = np.linspace(1.0, 1.5, T.len)[:, None]
    demand.values[...] = growth * np.array([100.0, 50.0, 80.0])
    historic_trade = Trade(
        imports=fd.FlodymArray(dims=DIMS["h", "r"]),
        exports=fd.FlodymArray(dims=DIMS["h", "r"]),
    )
    historic_trade.imports.values[...] = np.array([10.0, 20.0, 5.0])
    historic_trade.exports.values[...] = np.array([15.0, 5.0, 15.0])
    future_trade = Trade(
        imports=fd.FlodymArray(dims=DIMS["t", "r"]),
        exports=fd.FlodymArray(dims=DIMS["t", "r"]),
    )
    TradeExtrapolator(
        historic_trade=historic_trade,
        future_trade=future_trade,
        future_dom_demand=demand,
        trade_factor=trade_factor,
    ).run()
    return future_trade


def make_factor(future_value: float) -> fd.FlodymArray:
    """Trade factor of 1 in historic years and `future_value` afterwards."""
    factor = fd.FlodymArray(dims=DIMS["t", "r"])
    factor[...] = 1.0
    factor.values[H.len :] = future_value
    return factor


def test_unit_factor_array_equals_default():
    baseline = run_extrapolation(1.0)
    unit = run_extrapolation(make_factor(1.0))
    np.testing.assert_allclose(unit.imports.values, baseline.imports.values)
    np.testing.assert_allclose(unit.exports.values, baseline.exports.values)


def test_trade_factor_halves_future_trade():
    baseline = run_extrapolation(1.0)
    reduced = run_extrapolation(make_factor(0.5))
    n_hist = H.len
    for flow in ("imports", "exports"):
        base_values = getattr(baseline, flow).values
        reduced_values = getattr(reduced, flow).values
        # historic years are untouched
        np.testing.assert_allclose(reduced_values[:n_hist], base_values[:n_hist])
        # future global trade is halved
        np.testing.assert_allclose(
            reduced_values[n_hist:].sum(axis=1),
            0.5 * base_values[n_hist:].sum(axis=1),
            rtol=0.05,
        )
    # global market stays balanced
    np.testing.assert_allclose(
        reduced.imports.values.sum(axis=1), reduced.exports.values.sum(axis=1)
    )
