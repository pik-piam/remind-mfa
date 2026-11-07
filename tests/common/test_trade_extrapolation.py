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


def test_single_region_factor_limits_global_trade_to_smaller_side():
    baseline = run_extrapolation(1.0)
    factor = make_factor(1.0)
    factor.values[H.len :, 0] = 0.5
    reduced = run_extrapolation(factor)
    future = slice(H.len, None)
    # region A is a net exporter, so the reduced exports are the smaller side and act exactly
    np.testing.assert_allclose(
        reduced.exports.values[future, 0], 0.5 * baseline.exports.values[future, 0]
    )
    np.testing.assert_allclose(
        reduced.exports.values[future, 1:], baseline.exports.values[future, 1:]
    )
    # all imports are scaled down proportionally to match the reduced global exports
    import_ratio = reduced.imports.values[future] / baseline.imports.values[future]
    np.testing.assert_allclose(
        import_ratio[:, 1:], np.repeat(import_ratio[:, [0]] / 0.5, 2, axis=1)
    )
    assert np.all(import_ratio < 1.0)
    np.testing.assert_allclose(
        reduced.imports.values.sum(axis=1), reduced.exports.values.sum(axis=1)
    )


def make_historical_trade(imports: np.ndarray, exports: np.ndarray) -> Trade:
    """Historical trade with constant per-region imports and exports."""
    historical_trade = Trade(
        imports=fd.FlodymArray(dims=DIMS["h", "r"]),
        exports=fd.FlodymArray(dims=DIMS["h", "r"]),
    )
    historical_trade.imports.values[...] = imports
    historical_trade.exports.values[...] = exports
    return historical_trade


def run_re_exporter_case(import_offset: float = 0.0) -> Trade:
    """Run a demand-driven extrapolation in which region C is a pure re-exporter.

    Region C has no domestic supply: its historical imports cover its demand plus the amount it
    re-exports, so its domestic supply derived from demand and trade is zero up to round-off.

    Args:
        import_offset: Added to C's historical imports, mimicking round-off of either sign in
            the derived zero domestic supply.

    Returns:
        The extrapolated future trade.
    """
    demand = fd.FlodymArray(dims=DIMS["t", "r"])
    growth = np.linspace(1.0, 1.5, T.len)[:, None]
    demand.values[...] = growth * np.array([10_000.0, 5_000.0, 2_000.0])
    historical_trade = make_historical_trade(
        imports=np.array([1_000.0, 2_000.0, 0.0]), exports=np.array([1_500.0, 500.0, 500.0])
    )
    historical_trade.imports.values[:, 2] = demand.values[: H.len, 2] + 500.0 + import_offset
    future_trade = Trade(
        imports=fd.FlodymArray(dims=DIMS["t", "r"]),
        exports=fd.FlodymArray(dims=DIMS["t", "r"]),
    )
    TradeExtrapolator(
        historical_trade=historical_trade,
        future_trade=future_trade,
        future_dom_demand=demand,
    ).run()
    return future_trade


@pytest.mark.parametrize("import_offset", [-1e-9, 1e-9])
def test_zero_domestic_supply_is_insensitive_to_round_off(import_offset: float):
    reference = run_re_exporter_case()
    perturbed = run_re_exporter_case(import_offset)
    for flow in ("imports", "exports"):
        reference_values = getattr(reference, flow).values
        np.testing.assert_allclose(
            getattr(perturbed, flow).values,
            reference_values,
            rtol=1e-6,
            atol=1e-9 * reference_values.max(),
        )


def test_scaling_applies_global_share_where_history_is_zero():
    demand = fd.FlodymArray(dims=DIMS["t", "r"])
    demand.values[...] = np.array([1_000.0, 500.0, 100.0])
    extrapolator = TradeExtrapolator(
        historical_trade=make_historical_trade(
            imports=np.array([300.0, 100.0, 0.0]), exports=np.zeros(R.len)
        ),
        future_trade=Trade(
            imports=fd.FlodymArray(dims=DIMS["t", "r"]),
            exports=fd.FlodymArray(dims=DIMS["t", "r"]),
        ),
        future_dom_demand=demand,
    )
    extrapolator.set_direction()
    extrapolator.extract_attributes()
    extrapolator.broadcast_scaler()
    trade_0 = fd.FlodymArray(dims=extrapolator.dims_out)
    driver_0 = fd.FlodymArray(dims=extrapolator.dims_out)
    global_share = (300.0 + 100.0) / (1_000.0 + 500.0)
    for round_off in (-1e-9, 0.0, 1e-9):
        # regions A and B keep their driver; region C grows from zero (up to round-off)
        driver_0.values[...] = np.array([1_000.0, 500.0, round_off])
        trade_0.values[...] = np.array([300.0, 100.0, round_off])
        trade = extrapolator.scaling(trd_0=trade_0, dom_0=driver_0, dom=demand)
        np.testing.assert_allclose(trade.values[:, 2], 100.0 * global_share, rtol=1e-6)
        np.testing.assert_allclose(
            trade.values[:, :2], np.broadcast_to([300.0, 100.0], (T.len, 2)), rtol=1e-4
        )
