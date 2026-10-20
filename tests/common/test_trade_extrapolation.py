"""Tests for the scenario trade factor in `remind_mfa.common.trade_extrapolation`."""

import numpy as np
import flodym as fd
import pytest

from remind_mfa.common.trade import Trade
from remind_mfa.common.trade_extrapolation import TradeExtrapolator

H = fd.Dimension(name="Historical Time", letter="h", items=list(range(2000, 2006)))
# long future horizon, so that the critically damped blend of the trade has converged at its end
T = fd.Dimension(name="Time", letter="t", items=list(range(2000, 2201)))
N_CONVERGED_YEARS = 10
"""Number of final years in which the blended trade is compared to the converged value."""
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
    historical_trade = Trade(
        imports=fd.FlodymArray(dims=DIMS["h", "r"]),
        exports=fd.FlodymArray(dims=DIMS["h", "r"]),
    )
    historical_trade.imports.values[...] = np.array([10.0, 20.0, 5.0])
    historical_trade.exports.values[...] = np.array([15.0, 5.0, 15.0])
    future_trade = Trade(
        imports=fd.FlodymArray(dims=DIMS["t", "r"]),
        exports=fd.FlodymArray(dims=DIMS["t", "r"]),
    )
    TradeExtrapolator(
        historical_trade=historical_trade,
        future_trade=future_trade,
        future_dom_demand=demand,
        n_trend_years=fd.FlodymArray(dims=DIMS["r",], values=np.full(R.len, 3.0)),
        trade_factor=trade_factor,
    ).run()
    return future_trade


def make_factor(future_value: float) -> fd.FlodymArray:
    """Trade factor of 1 in historical years and `future_value` afterwards."""
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
        # historical years are untouched
        np.testing.assert_allclose(reduced_values[:n_hist], base_values[:n_hist])
        # future global trade is halved, once the blend from historical trends has converged
        np.testing.assert_allclose(
            reduced_values[-N_CONVERGED_YEARS:].sum(axis=1),
            0.5 * base_values[-N_CONVERGED_YEARS:].sum(axis=1),
            rtol=0.02,
        )
        # the reduction already acts during the transition
        assert np.all(reduced_values[n_hist:].sum(axis=1) < base_values[n_hist:].sum(axis=1))
    # global market stays balanced
    np.testing.assert_allclose(
        reduced.imports.values.sum(axis=1), reduced.exports.values.sum(axis=1)
    )
